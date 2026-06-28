"""Fixed-income regime API contracts."""

from __future__ import annotations

import datetime

from pydantic import BaseModel


class FixedIncomeCurveMetricResponse(BaseModel):
    """Derived fixed-income curve metrics for one date."""

    date: datetime.date
    country: str = "US"
    currency: str | None = None
    y_1mo: float | None = None
    y_3mo: float | None = None
    y_6mo: float | None = None
    y_1y: float | None = None
    y_2y: float | None = None
    y_5y: float | None = None
    y_10y: float | None = None
    y_20y: float | None = None
    y_30y: float | None = None
    spread_10y_2y: float | None = None
    spread_10y_3m: float | None = None
    spread_30y_5y: float | None = None
    real_yield_10y: float | None = None
    high_yield_spread: float | None = None
    ig_corp_spread: float | None = None
    y_2y_change_5d: float | None = None
    y_10y_change_5d: float | None = None
    y_30y_change_5d: float | None = None
    y_2y_change_20d: float | None = None
    y_10y_change_20d: float | None = None
    y_30y_change_20d: float | None = None
    y_10y_volatility_20d: float | None = None
    curve_regime: str | None = None
    rate_regime: str | None = None
    credit_regime: str | None = None
    bond_environment_score: int | None = None
    bond_environment_label: str | None = None
    source: str | None = None
    computed_at: datetime.datetime | None = None


class FixedIncomeSignalResponse(BaseModel):
    """One fixed-income signal."""

    date: datetime.date
    country: str = "US"
    signal_name: str
    value: float | None = None
    strength: str
    direction: str
    interpretation: str
    created_at: datetime.datetime | None = None


class FixedIncomeETFProxyPriceResponse(BaseModel):
    """Latest ETF proxy price row."""

    symbol: str
    name: str | None = None
    date: datetime.date
    close: float | None = None
    change_1d_pct: float | None = None
    source: str | None = None


class FixedIncomeRegimeResponse(BaseModel):
    """Latest fixed-income regime, signals, and ETF proxy context."""

    latest: FixedIncomeCurveMetricResponse
    signals: list[FixedIncomeSignalResponse]
    etf_proxies: list[FixedIncomeETFProxyPriceResponse]


class FixedIncomeHistoryResponse(BaseModel):
    """Fixed-income metric history."""

    count: int
    metrics: list[FixedIncomeCurveMetricResponse]


class FixedIncomeSignalsResponse(BaseModel):
    """Fixed-income signal history."""

    count: int
    signals: list[FixedIncomeSignalResponse]
