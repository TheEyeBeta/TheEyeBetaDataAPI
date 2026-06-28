"""SQLAlchemy repository for fixed-income regimes."""

from __future__ import annotations

import logging
from datetime import date
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import DatabaseUnavailableError
from app.domain.models import (
    FixedIncomeCurveMetric,
    FixedIncomeETFProxyPrice,
    FixedIncomeSignal,
)

logger = logging.getLogger("dataapi.repository")

_METRICS_TABLE = "theeyebeta.fixed_income_curve_metrics"
_SIGNALS_TABLE = "theeyebeta.fixed_income_signals"
_METRIC_COLUMNS = (
    "date",
    "country",
    "currency",
    "y_1mo",
    "y_3mo",
    "y_6mo",
    "y_1y",
    "y_2y",
    "y_5y",
    "y_10y",
    "y_20y",
    "y_30y",
    "spread_10y_2y",
    "spread_10y_3m",
    "spread_30y_5y",
    "real_yield_10y",
    "high_yield_spread",
    "ig_corp_spread",
    "y_2y_change_5d",
    "y_10y_change_5d",
    "y_30y_change_5d",
    "y_2y_change_20d",
    "y_10y_change_20d",
    "y_30y_change_20d",
    "y_10y_volatility_20d",
    "curve_regime",
    "rate_regime",
    "credit_regime",
    "bond_environment_score",
    "bond_environment_label",
    "source",
    "computed_at",
)
_METRIC_NUMERIC = {
    "y_1mo",
    "y_3mo",
    "y_6mo",
    "y_1y",
    "y_2y",
    "y_5y",
    "y_10y",
    "y_20y",
    "y_30y",
    "spread_10y_2y",
    "spread_10y_3m",
    "spread_30y_5y",
    "real_yield_10y",
    "high_yield_spread",
    "ig_corp_spread",
    "y_2y_change_5d",
    "y_10y_change_5d",
    "y_30y_change_5d",
    "y_2y_change_20d",
    "y_10y_change_20d",
    "y_30y_change_20d",
    "y_10y_volatility_20d",
}


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


class SQLFixedIncomeRepository:
    """SQLAlchemy-backed fixed-income repository over the theeyebeta schema."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_latest_metric(self, country: str = "US") -> FixedIncomeCurveMetric | None:
        try:
            if not self._table_exists("theeyebeta.fixed_income_curve_metrics"):
                return None
            row = self._session.execute(
                text(
                    f"""
                    SELECT {", ".join(_METRIC_COLUMNS)}
                      FROM {_METRICS_TABLE}
                     WHERE country = :country
                     ORDER BY date DESC, computed_at DESC
                     LIMIT 1
                    """  # noqa: S608
                ),
                {"country": country},
            ).mappings().first()
            return self._metric_from_row(row) if row else None
        except SQLAlchemyError as exc:
            logger.exception("get_latest_metric failed")
            raise DatabaseUnavailableError("Unable to fetch fixed-income regime") from exc

    def get_history(
        self,
        country: str = "US",
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> list[FixedIncomeCurveMetric]:
        try:
            if not self._table_exists("theeyebeta.fixed_income_curve_metrics"):
                return []
            parts = ["country = :country"]
            params: dict[str, Any] = {"country": country, "limit": limit}
            if start:
                parts.append("date >= :start")
                params["start"] = start
            if end:
                parts.append("date <= :end")
                params["end"] = end
            rows = self._session.execute(
                text(
                    f"""
                    SELECT {", ".join(_METRIC_COLUMNS)}
                      FROM {_METRICS_TABLE}
                     WHERE {" AND ".join(parts)}
                     ORDER BY date DESC
                     LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [self._metric_from_row(row) for row in rows]
        except SQLAlchemyError as exc:
            logger.exception("get_history failed")
            raise DatabaseUnavailableError("Unable to fetch fixed-income history") from exc

    def get_signals(
        self,
        country: str = "US",
        as_of_date: date | None = None,
        limit: int = 50,
    ) -> list[FixedIncomeSignal]:
        try:
            if not self._table_exists("theeyebeta.fixed_income_signals"):
                return []
            parts = ["country = :country"]
            params: dict[str, Any] = {"country": country, "limit": limit}
            if as_of_date:
                parts.append("date = :as_of_date")
                params["as_of_date"] = as_of_date
            rows = self._session.execute(
                text(
                    f"""
                    SELECT
                        date,
                        country,
                        signal_name,
                        signal_value,
                        signal_strength,
                        signal_direction,
                        interpretation,
                        created_at
                      FROM {_SIGNALS_TABLE}
                     WHERE {" AND ".join(parts)}
                     ORDER BY date DESC, signal_name
                     LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                FixedIncomeSignal(
                    date=row["date"],
                    country=str(row["country"]),
                    signal_name=str(row["signal_name"]),
                    value=_to_float(row.get("signal_value")),
                    strength=str(row["signal_strength"]),
                    direction=str(row["signal_direction"]),
                    interpretation=str(row["interpretation"]),
                    created_at=row.get("created_at"),
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_signals failed")
            raise DatabaseUnavailableError("Unable to fetch fixed-income signals") from exc

    def get_etf_proxy_prices(self) -> list[FixedIncomeETFProxyPrice]:
        try:
            rows = self._session.execute(
                text(
                    """
                    WITH ranked AS (
                        SELECT
                            i.symbol,
                            COALESCE(i.metadata->>'name', i.symbol) AS name,
                            COALESCE(
                                i.metadata->>'fixed_income_proxy_type',
                                CASE
                                    WHEN i.symbol = 'SHY' THEN 'short_treasury'
                                    WHEN i.symbol = 'IEF' THEN 'intermediate_treasury'
                                    WHEN i.symbol = 'TLT' THEN 'long_treasury'
                                    WHEN i.symbol = 'TIP' THEN 'inflation_linked'
                                    WHEN i.symbol IN ('BND', 'AGG') THEN 'aggregate_bond'
                                END
                            ) AS proxy_type,
                            COALESCE(
                                i.metadata->>'fixed_income_issuer_type',
                                CASE
                                    WHEN i.symbol IN ('SHY', 'IEF', 'TLT', 'TIP')
                                        THEN 'government'
                                    WHEN i.symbol IN ('BND', 'AGG') THEN 'aggregate'
                                END
                            ) AS issuer_type,
                            p.ts,
                            p.close,
                            p.source,
                            ROW_NUMBER() OVER (
                                PARTITION BY i.symbol ORDER BY p.ts DESC
                            ) AS rn
                          FROM theeyebeta.instruments i
                          JOIN theeyebeta.prices_daily p ON p.instrument_id = i.id
                         WHERE i.symbol IN ('SHY', 'IEF', 'TLT', 'TIP', 'BND', 'AGG')
                           AND i.asset_class = 'etf'
                           AND i.active
                    )
                    SELECT
                        latest.symbol,
                        latest.name,
                        latest.proxy_type,
                        latest.issuer_type,
                        latest.ts::date AS price_date,
                        latest.close,
                        latest.source,
                        CASE WHEN previous.close > 0
                            THEN ROUND(((latest.close / previous.close) - 1) * 100, 4)
                        END AS change_1d_pct
                      FROM ranked latest
                      LEFT JOIN ranked previous
                        ON previous.symbol = latest.symbol
                       AND previous.rn = 2
                     WHERE latest.rn = 1
                     ORDER BY latest.symbol
                    """
                )
            ).mappings().all()
            return [
                FixedIncomeETFProxyPrice(
                    symbol=str(row["symbol"]),
                    name=str(row["name"]) if row.get("name") else None,
                    proxy_type=str(row["proxy_type"]) if row.get("proxy_type") else None,
                    issuer_type=str(row["issuer_type"]) if row.get("issuer_type") else None,
                    date=row["price_date"],
                    close=_to_float(row.get("close")),
                    change_1d_pct=_to_float(row.get("change_1d_pct")),
                    source=str(row["source"]) if row.get("source") else None,
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_etf_proxy_prices failed")
            raise DatabaseUnavailableError("Unable to fetch fixed-income ETF proxies") from exc

    def _table_exists(self, regclass: str) -> bool:
        return bool(
            self._session.execute(
                text("SELECT to_regclass(:regclass)"),
                {"regclass": regclass},
            ).scalar()
        )

    @staticmethod
    def _metric_from_row(row: Mapping[str, Any]) -> FixedIncomeCurveMetric:
        values: dict[str, Any] = {}
        for column in _METRIC_COLUMNS:
            raw = row.get(column)
            values[column] = _to_float(raw) if column in _METRIC_NUMERIC else raw
        if values["bond_environment_score"] is not None:
            values["bond_environment_score"] = int(values["bond_environment_score"])
        return FixedIncomeCurveMetric(**values)
