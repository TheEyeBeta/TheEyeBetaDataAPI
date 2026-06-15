"""Dependency providers for repositories and services."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.interfaces import MacroRepository, MarketDataRepository
from app.repositories.sql_macro import SQLMacroRepository
from app.repositories.sql_market_data import SQLMarketDataRepository
from app.services.admin_service import AdminService
from app.services.advisor_service import AdvisorService
from app.services.health_service import HealthService
from app.services.internal_service import InternalService
from app.services.macro_service import MacroService
from app.services.market_data_service import MarketDataService
from app.services.portfolio_service import PortfolioService
from app.services.signals_service import SignalsService
from app.services.trades_service import TradesService


def get_session() -> Iterator[Session]:
    """Provide request-scoped DB session."""
    session = get_db_session()
    try:
        yield session
    finally:
        session.close()


def get_market_data_repository(session: Session = Depends(get_session)) -> MarketDataRepository:
    """Provide request-scoped market data repository."""
    return SQLMarketDataRepository(session)


def get_macro_repository(session: Session = Depends(get_session)) -> MacroRepository:
    """Provide request-scoped macro repository."""
    return SQLMacroRepository(session)


def get_health_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> HealthService:
    """Provide health service."""
    return HealthService(repository=repository)


def get_advisor_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> AdvisorService:
    """Provide advisor service."""
    return AdvisorService(repository=repository)


def get_market_data_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> MarketDataService:
    """Provide market data service."""
    return MarketDataService(repository=repository)


def get_signals_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> SignalsService:
    """Provide signals service."""
    return SignalsService(repository=repository)


def get_portfolio_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> PortfolioService:
    """Provide portfolio service."""
    return PortfolioService(repository=repository)


def get_trades_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> TradesService:
    """Provide trades service."""
    return TradesService(repository=repository)


def get_admin_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> AdminService:
    """Provide admin service."""
    return AdminService(repository=repository)


def get_internal_service(repository: MarketDataRepository = Depends(get_market_data_repository)) -> InternalService:
    """Provide internal service."""
    return InternalService(repository=repository)


def get_macro_service(repository: MacroRepository = Depends(get_macro_repository)) -> MacroService:
    """Provide macro service."""
    return MacroService(repository=repository)
