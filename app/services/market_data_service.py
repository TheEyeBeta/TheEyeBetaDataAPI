"""Market and symbol use-cases."""

from __future__ import annotations

from app.repositories.interfaces import MarketDataRepository
from app.schemas.context import TickerSnapshotResponse, TickerSummaryResponse
from app.schemas.market import AnalyticsSnapshotResponse, MarketQuotesResponse, SymbolSearchResponse


def _snapshot_to_response(snapshot) -> TickerSnapshotResponse:
    return TickerSnapshotResponse(
        ticker=snapshot.ticker,
        company_name=snapshot.company_name,
        last_price=snapshot.last_price,
        price_change_pct=snapshot.price_change_pct,
        rsi_14=snapshot.rsi_14,
        sma_10=snapshot.sma_10,
        sma_50=snapshot.sma_50,
        sma_200=snapshot.sma_200,
        macd=snapshot.macd,
        macd_signal=snapshot.macd_signal,
        macd_hist=snapshot.macd_hist,
        updated_at=snapshot.updated_at,
    )


class MarketDataService:
    """Read-focused market and analytics use-cases."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_quotes(self, symbols: list[str]) -> MarketQuotesResponse:
        quotes = []
        for symbol in symbols:
            snapshot = self._repository.get_latest_snapshot(symbol)
            if snapshot:
                quotes.append(_snapshot_to_response(snapshot))
        return MarketQuotesResponse(quotes=quotes)

    def search_symbols(self, query: str, limit: int) -> SymbolSearchResponse:
        items = self._repository.search_symbols(query=query, limit=limit)
        return SymbolSearchResponse(
            results=[TickerSummaryResponse(ticker=item.ticker, company_name=item.company_name) for item in items]
        )

    def get_analytics_snapshot(self, ticker: str) -> AnalyticsSnapshotResponse:
        snapshot = self._repository.get_latest_snapshot(ticker=ticker)
        return AnalyticsSnapshotResponse(snapshot=_snapshot_to_response(snapshot) if snapshot else None)
