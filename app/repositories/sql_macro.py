"""SQLAlchemy repository implementation for macro indicators and regimes."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import DatabaseUnavailableError
from app.domain.models import (
    MacroLatestPoint,
    MacroObservation,
    MacroRegimeSnapshot,
    MacroSeriesStat,
)

logger = logging.getLogger("dataapi.repository")

_INDICATORS = "theeyebeta.macro_indicators"
_REGIME_TABLES = (("theeyebeta", "macro_regime_snapshots"),)

_REGIME_COLUMNS = (
    "as_of_date",
    "fed_funds_rate",
    "yield_10y",
    "yield_2y",
    "spread_2s10s",
    "vix",
    "dxy",
    "hy_oas_bps",
    "rate_environment",
    "yield_curve",
    "credit_environment",
    "volatility_regime",
    "dollar_regime",
    "style_tilts",
    "data_source",
    "computed_at",
    "sp500_level",
    "sp500_change_pct",
    "nasdaq_level",
    "nasdaq_change_pct",
    "cpi",
    "gdp",
    "fed_funds_change_30d",
    "yield_10y_change_30d",
    "yield_2y_change_30d",
    "spread_2s10s_change_30d",
    "dxy_change_5d",
    "dxy_change_30d",
    "vix_change_5d",
    "vix_pct_rank_1y",
    "hy_oas_change_30d",
    "sp500_change_5d_pct",
    "sp500_change_30d_pct",
    "nasdaq_change_5d_pct",
    "nasdaq_change_30d_pct",
    "cpi_surprise",
    "cpi_yoy_pct",
    "gdp_qoq_pct",
)

_REGIME_NUMERIC = {
    "fed_funds_rate", "yield_10y", "yield_2y", "spread_2s10s", "vix", "dxy",
    "hy_oas_bps", "sp500_level", "sp500_change_pct", "nasdaq_level",
    "nasdaq_change_pct", "cpi", "gdp", "fed_funds_change_30d",
    "yield_10y_change_30d", "yield_2y_change_30d", "spread_2s10s_change_30d",
    "dxy_change_5d", "dxy_change_30d", "vix_change_5d", "vix_pct_rank_1y",
    "hy_oas_change_30d", "sp500_change_5d_pct", "sp500_change_30d_pct",
    "nasdaq_change_5d_pct", "nasdaq_change_30d_pct", "cpi_surprise",
    "cpi_yoy_pct", "gdp_qoq_pct",
}


def _to_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _snapshot_sort_key(snapshot: MacroRegimeSnapshot) -> tuple[date, datetime]:
    computed_at = snapshot.computed_at
    if computed_at is None:
        normalized_computed_at = datetime.min.replace(tzinfo=UTC)
    elif computed_at.tzinfo is None:
        normalized_computed_at = computed_at.replace(tzinfo=UTC)
    else:
        normalized_computed_at = computed_at.astimezone(UTC)
    return snapshot.as_of_date or date.min, normalized_computed_at


class SQLMacroRepository:
    """SQLAlchemy-backed macro repository over the theeyebeta schema."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_series_stats(self) -> list[MacroSeriesStat]:
        try:
            rows = self._session.execute(
                text(
                    f"""
                    SELECT
                        series_code,
                        COUNT(*) AS observation_count,
                        MAX(ts)::date AS latest_date,
                        (ARRAY_AGG(value ORDER BY ts DESC))[1] AS latest_value,
                        (ARRAY_AGG(source ORDER BY ts DESC))[1] AS source
                    FROM {_INDICATORS}
                    GROUP BY series_code
                    ORDER BY series_code
                    """  # noqa: S608
                )
            ).mappings().all()
            return [
                MacroSeriesStat(
                    code=str(r["series_code"]),
                    latest_value=_to_float(r.get("latest_value")),
                    latest_date=r.get("latest_date"),
                    observation_count=int(r["observation_count"]),
                    source=str(r["source"]) if r.get("source") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_series_stats failed")
            raise DatabaseUnavailableError("Unable to fetch macro series") from exc

    def series_exists(self, code: str) -> bool:
        try:
            row = self._session.execute(
                text(f"SELECT 1 FROM {_INDICATORS} WHERE series_code = :code LIMIT 1"),  # noqa: S608
                {"code": code},
            ).first()
            return row is not None
        except SQLAlchemyError as exc:
            logger.exception("series_exists failed")
            raise DatabaseUnavailableError("Unable to check macro series") from exc

    def get_observations(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
    ) -> list[MacroObservation]:
        try:
            parts = ["series_code = :code"]
            params: dict[str, Any] = {"code": code, "limit": limit}
            if start:
                parts.append("ts::date >= :start")
                params["start"] = start
            if end:
                parts.append("ts::date <= :end")
                params["end"] = end
            where = " AND ".join(parts)
            rows = self._session.execute(
                text(
                    f"""
                    SELECT ts::date AS obs_date, value
                    FROM {_INDICATORS}
                    WHERE {where}
                    ORDER BY ts DESC
                    LIMIT :limit
                    """  # noqa: S608
                ),
                params,
            ).mappings().all()
            return [
                MacroObservation(date=r["obs_date"], value=_to_float(r.get("value")))
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_observations failed")
            raise DatabaseUnavailableError("Unable to fetch macro observations") from exc

    def get_latest_points(self, codes: list[str] | None = None) -> list[MacroLatestPoint]:
        try:
            where = ""
            params: dict[str, Any] = {}
            stmt_text = (
                f"""
                SELECT DISTINCT ON (series_code)
                    series_code, ts::date AS obs_date, value, source
                FROM {_INDICATORS}
                {{where}}
                ORDER BY series_code, ts DESC
                """  # noqa: S608
            )
            if codes:
                where = "WHERE series_code IN :codes"
                params["codes"] = codes
                stmt = text(stmt_text.format(where=where)).bindparams(
                    bindparam("codes", expanding=True)
                )
            else:
                stmt = text(stmt_text.format(where=where))
            rows = self._session.execute(stmt, params).mappings().all()
            return [
                MacroLatestPoint(
                    code=str(r["series_code"]),
                    date=r.get("obs_date"),
                    value=_to_float(r.get("value")),
                    source=str(r["source"]) if r.get("source") else None,
                )
                for r in rows
            ]
        except SQLAlchemyError as exc:
            logger.exception("get_latest_points failed")
            raise DatabaseUnavailableError("Unable to fetch latest macro values") from exc

    def get_latest_regime(self) -> MacroRegimeSnapshot | None:
        try:
            snapshots = [
                snapshot
                for schema, table in _REGIME_TABLES
                if (snapshot := self._get_latest_regime_from_table(schema, table)) is not None
            ]
            if not snapshots:
                return None
            return max(snapshots, key=_snapshot_sort_key)
        except SQLAlchemyError as exc:
            logger.exception("get_latest_regime failed")
            raise DatabaseUnavailableError("Unable to fetch macro regime") from exc

    def _get_latest_regime_from_table(self, schema: str, table: str) -> MacroRegimeSnapshot | None:
        columns = self._get_regime_columns(schema, table)
        selected_columns = [column for column in _REGIME_COLUMNS if column in columns]
        if "as_of_date" not in selected_columns:
            return None

        column_sql = ", ".join(selected_columns)
        order_sql = "as_of_date DESC"
        if "computed_at" in columns:
            order_sql += ", computed_at DESC"

        row = self._session.execute(
            text(
                f"""
                SELECT {column_sql}
                FROM {schema}.{table}
                ORDER BY {order_sql}
                LIMIT 1
                """  # noqa: S608
            )
        ).mappings().first()
        if not row:
            return None

        values: dict[str, Any] = {}
        for col in _REGIME_COLUMNS:
            raw = row.get(col)
            values[col] = _to_float(raw) if col in _REGIME_NUMERIC else raw
        return MacroRegimeSnapshot(**values)

    def _get_regime_columns(self, schema: str, table: str) -> set[str]:
        rows = self._session.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = :table
                """
            ),
            {"schema": schema, "table": table},
        ).all()
        return {str(row[0]) for row in rows}
