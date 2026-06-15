"""Macro indicator / regime API contracts."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel


class MacroSeriesSummary(BaseModel):
    """One macro series with metadata and its latest observation."""

    code: str
    name: str | None = None
    category: str | None = None
    frequency: str | None = None
    units: str | None = None
    source: str | None = None
    seasonal_adj: bool | None = None
    latest_value: float | None = None
    latest_date: datetime.date | None = None
    observation_count: int = 0
    in_registry: bool = False


class MacroSeriesListResponse(BaseModel):
    """List of macro series with metadata."""

    count: int
    series: list[MacroSeriesSummary]


class MacroObservationPoint(BaseModel):
    """A single observation in a macro series."""

    date: datetime.date
    value: float | None = None


class MacroSeriesDetailResponse(BaseModel):
    """Metadata plus an observation window for one macro series."""

    code: str
    name: str | None = None
    category: str | None = None
    frequency: str | None = None
    units: str | None = None
    source: str | None = None
    seasonal_adj: bool | None = None
    in_registry: bool = False
    observation_count: int = 0
    start: datetime.date | None = None
    end: datetime.date | None = None
    observations: list[MacroObservationPoint]


class MacroLatestItem(BaseModel):
    """Most recent observation for a macro series."""

    code: str
    name: str | None = None
    category: str | None = None
    units: str | None = None
    date: datetime.date | None = None
    value: float | None = None
    source: str | None = None


class MacroLatestResponse(BaseModel):
    """Latest observation across macro series."""

    count: int
    observations: list[MacroLatestItem]


class MacroRegimeResponse(BaseModel):
    """Latest macro regime snapshot with all derived columns."""

    as_of_date: datetime.date | None = None
    fed_funds_rate: float | None = None
    yield_10y: float | None = None
    yield_2y: float | None = None
    spread_2s10s: float | None = None
    vix: float | None = None
    dxy: float | None = None
    hy_oas_bps: float | None = None
    rate_environment: str | None = None
    yield_curve: str | None = None
    credit_environment: str | None = None
    volatility_regime: str | None = None
    dollar_regime: str | None = None
    style_tilts: Any | None = None
    data_source: str | None = None
    computed_at: datetime.datetime | None = None
    sp500_level: float | None = None
    sp500_change_pct: float | None = None
    nasdaq_level: float | None = None
    nasdaq_change_pct: float | None = None
    cpi: float | None = None
    gdp: float | None = None
    fed_funds_change_30d: float | None = None
    yield_10y_change_30d: float | None = None
    yield_2y_change_30d: float | None = None
    spread_2s10s_change_30d: float | None = None
    dxy_change_5d: float | None = None
    dxy_change_30d: float | None = None
    vix_change_5d: float | None = None
    vix_pct_rank_1y: float | None = None
    hy_oas_change_30d: float | None = None
    sp500_change_5d_pct: float | None = None
    sp500_change_30d_pct: float | None = None
    nasdaq_change_5d_pct: float | None = None
    nasdaq_change_30d_pct: float | None = None
    cpi_surprise: float | None = None
    cpi_yoy_pct: float | None = None
    gdp_qoq_pct: float | None = None
