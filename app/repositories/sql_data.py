"""Read-only generic table access for the canonical theeyebeta schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.errors import DatabaseUnavailableError, NotFoundAppError, ValidationAppError
from app.schemas.data import DataColumnInfo, DataTableInfo

_SCHEMA = "theeyebeta"
_IDENTIFIER_RE = r"^[A-Za-z_][A-Za-z0-9_]*$"
_ORDER_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}
_FILTER_OPS = {
    "eq": "=",
    "ne": "!=",
    "lt": "<",
    "lte": "<=",
    "gt": ">",
    "gte": ">=",
    "like": "LIKE",
    "ilike": "ILIKE",
}


def _quote_ident(identifier: str) -> str:
    import re

    if not re.match(_IDENTIFIER_RE, identifier):
        raise ValidationAppError(f"Invalid identifier: {identifier!r}")
    return f'"{identifier}"'


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


class SQLReadOnlyDataRepository:
    """Metadata-driven read access to the theeyebeta schema only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_tables(self) -> list[DataTableInfo]:
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT
                        t.table_name,
                        t.table_type,
                        s.n_live_tup AS row_count_estimate
                    FROM information_schema.tables t
                    LEFT JOIN pg_stat_user_tables s
                      ON s.schemaname = t.table_schema
                     AND s.relname = t.table_name
                    WHERE t.table_schema = :schema
                    ORDER BY t.table_name
                    """
                ),
                {"schema": _SCHEMA},
            ).mappings().all()
            return [
                DataTableInfo(
                    name=str(row["table_name"]),
                    table_type=str(row["table_type"]),
                    row_count_estimate=int(row["row_count_estimate"]) if row.get("row_count_estimate") is not None else None,
                )
                for row in rows
            ]
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError("Unable to list data tables") from exc

    def table_exists(self, table: str) -> bool:
        return self._table_type(table) is not None

    def list_columns(self, table: str) -> list[DataColumnInfo]:
        _quote_ident(table)
        try:
            rows = self._session.execute(
                text(
                    """
                    SELECT column_name, data_type, is_nullable, ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                      AND table_name = :table
                    ORDER BY ordinal_position
                    """
                ),
                {"schema": _SCHEMA, "table": table},
            ).mappings().all()
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError("Unable to list table columns") from exc
        if not rows and not self.table_exists(table):
            raise NotFoundAppError(f"Unknown theeyebeta table: {table}")
        return [
            DataColumnInfo(
                name=str(row["column_name"]),
                data_type=str(row["data_type"]),
                nullable=str(row["is_nullable"]).upper() == "YES",
                ordinal_position=int(row["ordinal_position"]),
            )
            for row in rows
        ]

    def query_rows(
        self,
        *,
        table: str,
        limit: int,
        offset: int,
        order_by: str | None,
        order_dir: str,
        filters: list[str],
        symbol: str | None,
        date_column: str | None,
        start: date | None,
        end: date | None,
    ) -> list[dict[str, Any]]:
        table_type = self._table_type(table)
        if table_type is None:
            raise NotFoundAppError(f"Unknown theeyebeta table: {table}")

        columns = {column.name for column in self.list_columns(table)}
        if not columns:
            raise ValidationAppError(f"Table has no readable columns: {table}")

        q_table = f"{_quote_ident(_SCHEMA)}.{_quote_ident(table)}"
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        clauses: list[str] = []

        for idx, raw_filter in enumerate(filters):
            column, op, value = self._parse_filter(raw_filter, columns)
            param = f"filter_{idx}"
            clauses.append(f"{_quote_ident(column)} {_FILTER_OPS[op]} :{param}")
            params[param] = value

        if symbol:
            params["symbol"] = symbol
            if "instrument_id" in columns:
                clauses.append(
                    "instrument_id = ("
                    "SELECT id FROM theeyebeta.instruments "
                    "WHERE UPPER(symbol) = UPPER(:symbol) LIMIT 1)"
                )
            elif "ticker_id" in columns:
                clauses.append(
                    "ticker_id IN ("
                    "SELECT public_ticker_id FROM theeyebeta.public_ticker_map "
                    "WHERE UPPER(symbol) = UPPER(:symbol))"
                )
            elif "symbol" in columns:
                clauses.append("UPPER(symbol) = UPPER(:symbol)")
            else:
                raise ValidationAppError(f"Table {table!r} cannot be filtered by symbol")

        if start or end:
            selected_date_column = date_column or self._default_date_column(columns)
            if selected_date_column is None:
                raise ValidationAppError(f"Table {table!r} has no date/timestamp column for range filtering")
            if selected_date_column not in columns:
                raise ValidationAppError(f"Unknown date column: {selected_date_column}")
            q_date = _quote_ident(selected_date_column)
            if start:
                clauses.append(f"{q_date} >= :start")
                params["start"] = start
            if end:
                clauses.append(f"{q_date} <= :end")
                params["end"] = end

        selected_order_by = order_by or self._default_order_column(columns)
        if selected_order_by not in columns:
            raise ValidationAppError(f"Unknown order column: {selected_order_by}")
        direction = _ORDER_DIRECTIONS.get(order_dir.lower())
        if direction is None:
            raise ValidationAppError("order_dir must be asc or desc")

        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM {q_table}"
            f"{where_sql}"
            f" ORDER BY {_quote_ident(selected_order_by)} {direction}"
            " LIMIT :limit OFFSET :offset"
        )
        try:
            rows = self._session.execute(text(sql), params).mappings().all()
            return [{key: _json_safe(value) for key, value in dict(row).items()} for row in rows]
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError("Unable to query table rows") from exc

    def _table_type(self, table: str) -> str | None:
        _quote_ident(table)
        try:
            row = self._session.execute(
                text(
                    """
                    SELECT table_type
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                      AND table_name = :table
                    """
                ),
                {"schema": _SCHEMA, "table": table},
            ).mappings().first()
        except SQLAlchemyError as exc:
            raise DatabaseUnavailableError("Unable to inspect table") from exc
        return str(row["table_type"]) if row else None

    @staticmethod
    def _parse_filter(raw_filter: str, columns: set[str]) -> tuple[str, str, str]:
        parts = raw_filter.split(":", 2)
        if len(parts) != 3:
            raise ValidationAppError("Filters must use column:op:value format")
        column, op, value = parts[0].strip(), parts[1].strip().lower(), parts[2]
        if column not in columns:
            raise ValidationAppError(f"Unknown filter column: {column}")
        if op not in _FILTER_OPS:
            raise ValidationAppError(f"Unsupported filter operator: {op}")
        return column, op, value

    @staticmethod
    def _default_date_column(columns: set[str]) -> str | None:
        for candidate in ("ts", "date", "calendar_date", "as_of_date", "published_at", "created_at", "updated_at"):
            if candidate in columns:
                return candidate
        return None

    @classmethod
    def _default_order_column(cls, columns: set[str]) -> str:
        date_column = cls._default_date_column(columns)
        if date_column:
            return date_column
        for candidate in ("id", "symbol", "instrument_id"):
            if candidate in columns:
                return candidate
        return sorted(columns)[0]
