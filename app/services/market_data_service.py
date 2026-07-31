"""Market and symbol use-cases."""

from __future__ import annotations

from datetime import date

from app.repositories.interfaces import MarketDataRepository
from app.schemas.context import TickerSnapshotResponse, TickerSummaryResponse
from app.schemas.market import (
    AnalyticsSnapshotResponse,
    BalanceSheetsResponse,
    BalanceSheetResponse,
    CapEventResponse,
    CapEventsResponse,
    CashFlowsResponse,
    CashFlowResponse,
    CompanyFundamentalsResponse,
    CorporateActionsResponse,
    CorporateActionResponse,
    CountriesResponse,
    CountryResponse,
    CurrenciesResponse,
    CurrencyResponse,
    EngineStatusEntryResponse,
    EngineStatusResponse,
    EtlJobStateResponse,
    EtlJobStatesResponse,
    ExchangeResponse,
    ExchangesResponse,
    IncomeStatementsResponse,
    IncomeStatementResponse,
    IndustriesResponse,
    IndustryResponse,
    MarketNewsItemResponse,
    MarketNewsResponse,
    MarketQuotesResponse,
    PriceDayResponse,
    PriceHistoryResponse,
    PriceTickResponse,
    PriceTicksResponse,
    QualityMetricResponse,
    QualityMetricsResponse,
    ReturnsDayResponse,
    ReturnsSnapshotResponse,
    RiskDayResponse,
    RiskIndicatorsResponse,
    SectorDailyEntryResponse,
    SectorDailyResponse,
    SectorResponse,
    SectorsResponse,
    SymbolSearchResponse,
    TechnicalDayResponse,
    TechnicalIndicatorsResponse,
    TickerDetailResponse,
    TickerIdentifierResponse,
    TickerNewsItemResponse,
    TickerNewsResponse,
    TradingCalendarDayResponse,
    TradingCalendarResponse,
    UniverseActiveResponse,
    UniverseCapEntryResponse,
    ValuationDayResponse,
    ValuationIndicatorsResponse,
    WorkerHeartbeatResponse,
    WorkerHeartbeatsResponse,
)


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


def _adjust_price_day(bar: PriceDayResponse) -> PriceDayResponse:
    """Rescale OHLC by adj_close/close so all four move together; volume is untouched."""
    if not bar.close or not bar.adj_close:
        return bar
    factor = bar.adj_close / bar.close
    return bar.model_copy(
        update={
            "open": bar.open * factor if bar.open is not None else None,
            "high": bar.high * factor if bar.high is not None else None,
            "low": bar.low * factor if bar.low is not None else None,
            "close": bar.adj_close,
        }
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

    # ── Reference ────────────────────────────────────────────────────────────

    def get_countries(self) -> CountriesResponse:
        items = self._repository.get_countries()
        return CountriesResponse(countries=[CountryResponse(country_code=c.country_code, country_name=c.country_name, default_timezone=c.default_timezone) for c in items])

    def get_currencies(self) -> CurrenciesResponse:
        items = self._repository.get_currencies()
        return CurrenciesResponse(currencies=[CurrencyResponse(currency_code=c.currency_code, currency_name=c.currency_name, symbol=c.symbol) for c in items])

    def get_exchanges(self) -> ExchangesResponse:
        items = self._repository.get_exchanges()
        return ExchangesResponse(exchanges=[ExchangeResponse(exchange_id=e.exchange_id, name=e.name, mic_code=e.mic_code, country_code=e.country_code, timezone=e.timezone) for e in items])

    def get_sectors(self) -> SectorsResponse:
        items = self._repository.get_sectors()
        return SectorsResponse(sectors=[SectorResponse(sector_id=s.sector_id, sector_name=s.sector_name) for s in items])

    def get_industries(self, sector_id: int | None = None) -> IndustriesResponse:
        items = self._repository.get_industries(sector_id=sector_id)
        return IndustriesResponse(industries=[IndustryResponse(industry_id=i.industry_id, sector_id=i.sector_id, industry_name=i.industry_name) for i in items])

    def get_trading_calendar(self, start: date | None, end: date | None, limit: int) -> TradingCalendarResponse:
        items = self._repository.get_trading_calendar(start=start, end=end, limit=limit)
        return TradingCalendarResponse(days=[TradingCalendarDayResponse(calendar_date=d.calendar_date, is_trading_day=d.is_trading_day, market_name=d.market_name, holiday_name=d.holiday_name, notes=d.notes) for d in items])

    # ── Ticker detail ─────────────────────────────────────────────────────────

    def get_ticker_detail(self, ticker: str) -> TickerDetailResponse | None:
        item = self._repository.get_ticker_detail(ticker=ticker)
        if not item:
            return None
        return TickerDetailResponse(
            ticker=item.ticker, company_name=item.company_name, asset_type=item.asset_type,
            country_code=item.country_code, timezone=item.timezone, currency_code=item.currency_code,
            is_active=item.is_active, sector_id=item.sector_id, industry_id=item.industry_id,
            website=item.website, description=item.description, founded_year=item.founded_year,
            employees=item.employees,
            identifiers=[TickerIdentifierResponse(id_type=i["id_type"], id_value=i["id_value"]) for i in item.identifiers],
        )

    def get_price_history(
        self,
        ticker: str,
        start: date | None,
        end: date | None,
        limit: int,
        adjust: str = "none",
    ) -> PriceHistoryResponse:
        """Return OHLCV history, optionally adjusted for splits and dividends.

        ``adjust="splits_dividends"`` rescales each bar's OHLC by the ratio of
        the already-stored ``adj_close`` to ``close`` (the combined
        split+dividend adjustment the ingestion pipeline computes) — volume is
        left as-is. There is no separate splits-only adjusted series stored,
        so a splits-only ``adjust`` value is intentionally not offered here
        rather than silently returning an incorrect series.
        """
        items = self._repository.get_price_history(ticker=ticker, start=start, end=end, limit=limit)
        prices = [
            PriceDayResponse(date=p.date, open=p.open, high=p.high, low=p.low, close=p.close, adj_close=p.adj_close, volume=p.volume, vwap=p.vwap)
            for p in items
        ]
        corporate_actions: list[CorporateActionResponse] = []
        if adjust == "splits_dividends":
            prices = [_adjust_price_day(p) for p in prices]
            actions = self._repository.get_corporate_actions(ticker=ticker, limit=500)
            corporate_actions = [
                CorporateActionResponse(action_id=a.action_id, action_date=a.action_date, action_type=a.action_type, split_ratio=a.split_ratio, dividend_amount=a.dividend_amount, notes=a.notes)
                for a in actions
            ]
        return PriceHistoryResponse(
            ticker=ticker.upper(),
            prices=prices,
            adjustment=adjust,
            corporate_actions=corporate_actions,
        )

    def get_corporate_actions(self, ticker: str, limit: int) -> CorporateActionsResponse:
        items = self._repository.get_corporate_actions(ticker=ticker, limit=limit)
        return CorporateActionsResponse(
            ticker=ticker.upper(),
            actions=[CorporateActionResponse(action_id=a.action_id, action_date=a.action_date, action_type=a.action_type, split_ratio=a.split_ratio, dividend_amount=a.dividend_amount, notes=a.notes) for a in items],
        )

    def get_company_fundamentals(self, ticker: str) -> CompanyFundamentalsResponse | None:
        item = self._repository.get_company_fundamentals(ticker=ticker)
        if not item:
            return None
        return CompanyFundamentalsResponse(
            ticker=ticker.upper(), sector=item.sector, industry=item.industry, sub_industry=item.sub_industry,
            ceo=item.ceo, full_time_employees=item.full_time_employees,
            headquarters_city=item.headquarters_city, headquarters_state=item.headquarters_state, headquarters_country=item.headquarters_country,
            market_cap=item.market_cap, enterprise_value=item.enterprise_value,
            shares_outstanding=item.shares_outstanding, float_shares=item.float_shares,
            pe_ratio=item.pe_ratio, pe_forward=item.pe_forward, peg_ratio=item.peg_ratio,
            price_to_book=item.price_to_book, price_to_sales=item.price_to_sales,
            ev_to_ebitda=item.ev_to_ebitda, ev_to_revenue=item.ev_to_revenue,
            dividend_rate=item.dividend_rate, dividend_yield=item.dividend_yield,
            ex_dividend_date=item.ex_dividend_date, payout_ratio=item.payout_ratio,
            currency=item.currency, source=item.source, last_updated=item.last_updated,
        )

    # ── Financial statements ──────────────────────────────────────────────────

    def get_income_statements(self, ticker: str, limit: int) -> IncomeStatementsResponse:
        items = self._repository.get_income_statements(ticker=ticker, limit=limit)
        return IncomeStatementsResponse(
            ticker=ticker.upper(),
            statements=[IncomeStatementResponse(period_end=i.period_end, fiscal_year=i.fiscal_year, fiscal_quarter=i.fiscal_quarter, revenue=i.revenue, gross_profit=i.gross_profit, ebit=i.ebit, ebitda=i.ebitda, interest_expense=i.interest_expense, net_income=i.net_income, eps_basic=i.eps_basic, eps_diluted=i.eps_diluted) for i in items],
        )

    def get_balance_sheets(self, ticker: str, limit: int) -> BalanceSheetsResponse:
        items = self._repository.get_balance_sheets(ticker=ticker, limit=limit)
        return BalanceSheetsResponse(
            ticker=ticker.upper(),
            statements=[BalanceSheetResponse(period_end=i.period_end, fiscal_year=i.fiscal_year, fiscal_quarter=i.fiscal_quarter, total_assets=i.total_assets, total_liabilities=i.total_liabilities, total_equity=i.total_equity, total_debt=i.total_debt, cash_and_equivalents=i.cash_and_equivalents, shares_outstanding=i.shares_outstanding) for i in items],
        )

    def get_cash_flows(self, ticker: str, limit: int) -> CashFlowsResponse:
        items = self._repository.get_cash_flows(ticker=ticker, limit=limit)
        return CashFlowsResponse(
            ticker=ticker.upper(),
            statements=[CashFlowResponse(period_end=i.period_end, fiscal_year=i.fiscal_year, fiscal_quarter=i.fiscal_quarter, ocf=i.ocf, capex=i.capex, fcf=i.fcf, working_cap_change=i.working_cap_change, stock_based_comp=i.stock_based_comp) for i in items],
        )

    def get_quality_metrics(self, ticker: str, limit: int) -> QualityMetricsResponse:
        items = self._repository.get_quality_metrics(ticker=ticker, limit=limit)
        return QualityMetricsResponse(
            ticker=ticker.upper(),
            metrics=[QualityMetricResponse(period_end=i.period_end, fiscal_year=i.fiscal_year, fiscal_quarter=i.fiscal_quarter, nopat=i.nopat, invested_capital=i.invested_capital, roic=i.roic, roe=i.roe, roa=i.roa, roce=i.roce, wacc=i.wacc, cost_of_equity=i.cost_of_equity, cost_of_debt=i.cost_of_debt, roic_wacc_spread=i.roic_wacc_spread, debt_equity=i.debt_equity, net_debt_ebitda=i.net_debt_ebitda, interest_coverage=i.interest_coverage, ocf=i.ocf, fcf=i.fcf) for i in items],
        )

    # ── Indicators ────────────────────────────────────────────────────────────

    def get_technical_indicators(self, ticker: str, start: date | None, end: date | None, limit: int) -> TechnicalIndicatorsResponse:
        items = self._repository.get_technical_indicators(ticker=ticker, start=start, end=end, limit=limit)
        return TechnicalIndicatorsResponse(
            ticker=ticker.upper(),
            indicators=[TechnicalDayResponse(date=i.date, sma_10=i.sma_10, sma_50=i.sma_50, sma_200=i.sma_200, ema_10=i.ema_10, ema_50=i.ema_50, ema_200=i.ema_200, ema_12=i.ema_12, ema_26=i.ema_26, rsi_14=i.rsi_14, macd=i.macd, macd_signal=i.macd_signal, macd_hist=i.macd_hist, roc_10=i.roc_10, roc_20=i.roc_20, golden_cross_sma=i.golden_cross_sma, death_cross_sma=i.death_cross_sma) for i in items],
        )

    def get_risk_indicators(self, ticker: str, start: date | None, end: date | None, limit: int) -> RiskIndicatorsResponse:
        items = self._repository.get_risk_indicators(ticker=ticker, start=start, end=end, limit=limit)
        return RiskIndicatorsResponse(
            ticker=ticker.upper(),
            indicators=[RiskDayResponse(date=i.date, atr_14=i.atr_14, hist_vol_20d=i.hist_vol_20d, hist_vol_60d=i.hist_vol_60d, beta_sp500_60d=i.beta_sp500_60d, worst_drop_1d=i.worst_drop_1d, worst_drop_5d=i.worst_drop_5d, worst_drop_10d=i.worst_drop_10d, max_drawdown_1y=i.max_drawdown_1y, max_drawdown_2y=i.max_drawdown_2y, sharpe_60d=i.sharpe_60d, sortino_60d=i.sortino_60d, calmar_1y=i.calmar_1y) for i in items],
        )

    def get_valuation_indicators(self, ticker: str, start: date | None, end: date | None, limit: int) -> ValuationIndicatorsResponse:
        items = self._repository.get_valuation_indicators(ticker=ticker, start=start, end=end, limit=limit)
        return ValuationIndicatorsResponse(
            ticker=ticker.upper(),
            indicators=[ValuationDayResponse(date=i.date, market_cap=i.market_cap, enterprise_value=i.enterprise_value, pe_ttm=i.pe_ttm, forward_pe=i.forward_pe, ps_ttm=i.ps_ttm, pb=i.pb, ev_ebitda=i.ev_ebitda, ev_ebit=i.ev_ebit, ev_fcf=i.ev_fcf, earnings_yield=i.earnings_yield, fcf_yield=i.fcf_yield, pct_chg_1w=i.pct_chg_1w, pct_chg_3m=i.pct_chg_3m, pct_chg_6m=i.pct_chg_6m, pct_chg_9m=i.pct_chg_9m, pct_chg_ytd=i.pct_chg_ytd, pct_chg_1y=i.pct_chg_1y) for i in items],
        )

    def get_returns_snapshot(self, ticker: str, start: date | None, end: date | None, limit: int) -> ReturnsSnapshotResponse:
        items = self._repository.get_returns_snapshot(ticker=ticker, start=start, end=end, limit=limit)
        return ReturnsSnapshotResponse(
            ticker=ticker.upper(),
            returns=[ReturnsDayResponse(date=i.date, ret_1w=i.ret_1w, ret_1m=i.ret_1m, ret_3m=i.ret_3m, ret_6m=i.ret_6m, ret_9m=i.ret_9m, ret_ytd=i.ret_ytd, ret_1y=i.ret_1y, price_field=i.price_field, computed_at=i.computed_at) for i in items],
        )

    # ── News ──────────────────────────────────────────────────────────────────

    def get_ticker_news(self, ticker: str, limit: int) -> TickerNewsResponse:
        items = self._repository.get_ticker_news(ticker=ticker, limit=limit)
        return TickerNewsResponse(
            ticker=ticker.upper(),
            news=[TickerNewsItemResponse(news_id=n.news_id, source=n.source, title=n.title, url=n.url, published_at=n.published_at, summary=n.summary, sentiment=n.sentiment, sentiment_score=n.sentiment_score) for n in items],
        )

    def get_market_news(self, limit: int) -> MarketNewsResponse:
        items = self._repository.get_recent_news(limit=limit)
        return MarketNewsResponse(
            news=[MarketNewsItemResponse(id=idx, headline=n.headline, source=n.source, category=n.category, published_at=n.published_at) for idx, n in enumerate(items, 1)]
        )

    # ── Admin-only ────────────────────────────────────────────────────────────

    def get_etl_job_states(self) -> EtlJobStatesResponse:
        items = self._repository.get_etl_job_states()
        return EtlJobStatesResponse(jobs=[EtlJobStateResponse(job_name=j.job_name, last_run_at=j.last_run_at, last_successful_date=j.last_successful_date, status=j.status, last_error=j.last_error) for j in items])

    def get_engine_status(self) -> EngineStatusResponse:
        items = self._repository.get_engine_status()
        return EngineStatusResponse(entries=[EngineStatusEntryResponse(key=e.key, value=e.value, updated_at=e.updated_at) for e in items])

    def get_price_ticks(self, ticker: str, limit: int) -> PriceTicksResponse:
        items = self._repository.get_price_ticks(ticker=ticker, limit=limit)
        return PriceTicksResponse(
            ticker=ticker.upper(),
            ticks=[PriceTickResponse(tick_id=t.tick_id, ts=t.ts, price=t.price, open=t.open, high=t.high, low=t.low, close=t.close, volume=t.volume, source=t.source) for t in items],
        )

    # ── Sector / universe ──────────────────────────────────────────────────────

    def get_sector_daily(self, sector: str | None, limit: int) -> SectorDailyResponse:
        items = self._repository.get_sector_daily(sector=sector, limit=limit)
        return SectorDailyResponse(
            sectors=[
                SectorDailyEntryResponse(
                    sector=s.sector,
                    as_of_date=s.as_of_date,
                    n_instruments=s.n_instruments,
                    avg_return_1d=s.avg_return_1d,
                    avg_return_5d=s.avg_return_5d,
                    avg_return_30d=s.avg_return_30d,
                    median_rsi_14=s.median_rsi_14,
                    pct_above_sma_50=s.pct_above_sma_50,
                    pct_above_sma_200=s.pct_above_sma_200,
                    rel_strength_spx_30d=s.rel_strength_spx_30d,
                    rotation_rank=s.rotation_rank,
                    volume_ratio_20d=s.volume_ratio_20d,
                    top_contributors=s.top_contributors,
                )
                for s in items
            ],
        )

    def get_universe_active(self, min_market_cap: float, limit: int) -> UniverseActiveResponse:
        items = self._repository.get_universe_active(min_market_cap=min_market_cap, limit=limit)
        return UniverseActiveResponse(
            as_of_date=items[0].as_of_date if items else None,
            entries=[
                UniverseCapEntryResponse(
                    symbol=u.symbol,
                    as_of_date=u.as_of_date,
                    market_cap=u.market_cap,
                    close_price=u.close_price,
                    shares_outstanding=u.shares_outstanding,
                    source=u.source,
                )
                for u in items
            ],
        )

    def get_cap_events(self, since: date | None, limit: int) -> CapEventsResponse:
        items = self._repository.get_cap_events(since=since, limit=limit)
        return CapEventsResponse(
            events=[
                CapEventResponse(
                    id=c.id,
                    trade_date=c.trade_date,
                    symbol=c.symbol,
                    event_type=c.event_type,
                    market_cap=c.market_cap,
                    prior_market_cap=c.prior_market_cap,
                    action_required=c.action_required,
                    universe_updated=c.universe_updated,
                )
                for c in items
            ],
        )

    def get_worker_heartbeats(self) -> WorkerHeartbeatsResponse:
        raw = self._repository.get_engine_worker_heartbeats()
        workers = [
            WorkerHeartbeatResponse(
                worker_id=w.get("worker_name", "unknown"),
                worker_type=None,
                status=w.get("status", "unknown"),
                last_heartbeat=w.get("last_heartbeat"),
                started_at=None,
                restart_count=None,
                last_error=None,
            )
            for w in raw
        ]
        return WorkerHeartbeatsResponse(workers=workers)
