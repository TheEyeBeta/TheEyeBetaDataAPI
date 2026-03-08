"""Portfolio use-cases."""

from __future__ import annotations

from app.repositories.interfaces import MarketDataRepository
from app.schemas.market import PortfolioPositionResponse, PortfolioStateResponse, PortfolioValuationResponse


class PortfolioService:
    """Read-focused portfolio service."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_state(self, *, owner_subject: str, position_limit: int) -> PortfolioStateResponse:
        valuation = self._repository.get_portfolio_valuation()
        positions = self._repository.get_portfolio_positions(limit=position_limit)

        valuation_response = None
        if valuation:
            valuation_response = PortfolioValuationResponse(
                valuation_date=valuation.valuation_date,
                total_value=valuation.total_value,
                cash_balance=valuation.cash_balance,
                positions_value=valuation.positions_value,
                total_cost_basis=valuation.total_cost_basis,
                unrealized_pnl=valuation.unrealized_pnl,
                realized_pnl=valuation.realized_pnl,
                currency_code=valuation.currency_code,
                created_at=valuation.created_at,
            )

        return PortfolioStateResponse(
            owner_subject=owner_subject,
            valuation=valuation_response,
            positions=[
                PortfolioPositionResponse(
                    ticker=position.ticker,
                    company_name=position.company_name,
                    quantity=position.quantity,
                    average_cost=position.average_cost,
                    last_price=position.last_price,
                    market_value=position.market_value,
                    unrealized_pnl=position.unrealized_pnl,
                    last_updated=position.last_updated,
                )
                for position in positions
            ],
        )
