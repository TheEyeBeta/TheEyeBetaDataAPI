"""Auth token issuance use-cases (service access + optional refresh)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.auth.service_clients import ServiceClient, get_service_client
from app.auth.tokens import create_service_access_token
from app.core.config import settings
from app.domain.errors import AuthenticationError
from app.repositories.sql_refresh_tokens import (
    RefreshTokenRepository,
    mint_refresh_token_value,
)
from app.schemas.auth import RefreshTokenResponse, ServiceTokenResponse


class AuthTokenService:
    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    def issue_service_token(
        self,
        client: ServiceClient,
        granted_scopes: list[str],
    ) -> ServiceTokenResponse:
        """Issue access token; attach refresh token only when client opted in."""
        if client.short_lived_tokens_enabled:
            expires_minutes = settings.short_lived_access_token_minutes
        else:
            expires_minutes = settings.service_token_expires_minutes

        access_token = create_service_access_token(
            subject=f"service:{client.client_id}",
            client_id=client.client_id,
            scopes=granted_scopes,
            expires_minutes=expires_minutes,
        )

        if not client.short_lived_tokens_enabled:
            return ServiceTokenResponse(
                access_token=access_token,
                expires_minutes=expires_minutes,
                scopes=granted_scopes,
            )

        if self._session is None:
            # Opt-in requires DB-backed refresh storage; fall back to access-only
            # rather than inventing an in-memory store (keeps non-DB clients safe).
            return ServiceTokenResponse(
                access_token=access_token,
                expires_minutes=expires_minutes,
                scopes=granted_scopes,
            )

        raw_refresh = mint_refresh_token_value()
        refresh_expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expires_days)
        RefreshTokenRepository(self._session).insert(
            subject=f"service:{client.client_id}",
            client_id=client.client_id,
            raw_token=raw_refresh,
            scopes=granted_scopes,
            expires_at=refresh_expires,
        )
        return ServiceTokenResponse(
            access_token=access_token,
            expires_minutes=expires_minutes,
            scopes=granted_scopes,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh_expires,
        )

    def refresh(self, presented_refresh_token: str) -> RefreshTokenResponse:
        if self._session is None:
            raise AuthenticationError("Refresh tokens require database-backed auth")

        repo = RefreshTokenRepository(self._session)
        presented = repo.lookup_active(presented_refresh_token)

        # Revalidate live client authorization before extending the refresh family.
        try:
            client = get_service_client(presented.client_id, session=self._session)
        except AuthenticationError:
            repo.revoke_active_for_client(presented.client_id)
            raise AuthenticationError("Service client is no longer authorized") from None

        if not client.short_lived_tokens_enabled:
            repo.revoke_active_for_client(presented.client_id)
            raise AuthenticationError("Refresh tokens are disabled for this client")

        live_scopes = sorted(set(presented.scopes).intersection(client.scopes))
        if not live_scopes:
            repo.revoke_active_for_client(presented.client_id)
            raise AuthenticationError("Refresh token scopes are no longer granted")

        new_raw = mint_refresh_token_value()
        new_expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expires_days)
        record = repo.rotate(
            presented_raw_token=presented_refresh_token,
            new_raw_token=new_raw,
            new_expires_at=new_expires,
            scopes=live_scopes,
        )
        access_expires = settings.short_lived_access_token_minutes
        access_token = create_service_access_token(
            subject=record.subject,
            client_id=record.client_id,
            scopes=live_scopes,
            expires_minutes=access_expires,
        )
        return RefreshTokenResponse(
            access_token=access_token,
            expires_minutes=access_expires,
            scopes=live_scopes,
            refresh_token=new_raw,
            refresh_expires_at=record.expires_at,
        )
