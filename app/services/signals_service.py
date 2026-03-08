"""Signals use-cases."""

from __future__ import annotations

from app.repositories.interfaces import MarketDataRepository
from app.schemas.market import SignalRecordResponse, SignalsLatestResponse


class SignalsService:
    """Read-focused signals capability service."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_latest(self, *, ticker: str | None, limit: int) -> SignalsLatestResponse:
        rows = self._repository.get_latest_signals(limit=limit, ticker=ticker)
        return SignalsLatestResponse(
            signals=[
                SignalRecordResponse(
                    ticker=row.ticker,
                    strategy_name=row.strategy_name,
                    signal=row.signal,
                    confidence=row.confidence,
                    entry_price=row.entry_price,
                    target_price=row.target_price,
                    stop_loss=row.stop_loss,
                    timestamp=row.timestamp,
                )
                for row in rows
            ]
        )
