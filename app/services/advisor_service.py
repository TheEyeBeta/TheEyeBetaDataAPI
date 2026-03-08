"""Advisor use-cases."""

from __future__ import annotations

from app.domain.models import AdvisorContext
from app.repositories.interfaces import MarketDataRepository
from app.schemas.chat import ChatResponse
from app.schemas.context import AdvisorContextResponse, NewsItemResponse, TickerSnapshotResponse, TickerSummaryResponse
from app.services.ai_service import answer_question


def _to_context_response(context: AdvisorContext) -> AdvisorContextResponse:
    snapshot = None
    if context.ticker_snapshot:
        snapshot = TickerSnapshotResponse(
            ticker=context.ticker_snapshot.ticker,
            company_name=context.ticker_snapshot.company_name,
            last_price=context.ticker_snapshot.last_price,
            price_change_pct=context.ticker_snapshot.price_change_pct,
            rsi_14=context.ticker_snapshot.rsi_14,
            sma_10=context.ticker_snapshot.sma_10,
            sma_50=context.ticker_snapshot.sma_50,
            sma_200=context.ticker_snapshot.sma_200,
            macd=context.ticker_snapshot.macd,
            macd_signal=context.ticker_snapshot.macd_signal,
            macd_hist=context.ticker_snapshot.macd_hist,
            updated_at=context.ticker_snapshot.updated_at,
        )
    return AdvisorContextResponse(
        tickers=[TickerSummaryResponse(ticker=t.ticker, company_name=t.company_name) for t in context.tickers],
        news=[
            NewsItemResponse(
                headline=news.headline,
                source=news.source,
                category=news.category,
                published_at=news.published_at,
            )
            for news in context.news
        ],
        ticker_snapshot=snapshot,
    )


class AdvisorService:
    """Advisor read/chat use-cases backed by market data repository."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def get_context(self, ticker: str | None, ticker_limit: int, news_limit: int) -> AdvisorContextResponse:
        context = AdvisorContext(
            tickers=self._repository.get_active_tickers(limit=ticker_limit),
            news=self._repository.get_recent_news(limit=news_limit),
            ticker_snapshot=self._repository.get_latest_snapshot(ticker=ticker) if ticker else None,
        )
        return _to_context_response(context)

    def chat(self, question: str, ticker: str | None) -> ChatResponse:
        context_response = self.get_context(ticker=ticker, ticker_limit=10, news_limit=8)
        context_payload = context_response.model_dump(mode="json")
        answer = answer_question(question=question, ticker=ticker, context=context_payload)
        context_rows = len(context_response.news) + (1 if context_response.ticker_snapshot else 0)
        return ChatResponse(answer=answer, used_ticker=ticker, context_rows=context_rows)
