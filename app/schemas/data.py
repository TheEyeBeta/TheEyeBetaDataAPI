"""Read-only generic data table contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DataTableInfo(BaseModel):
    """One readable table or view in the theeyebeta schema."""

    name: str
    table_type: str
    row_count_estimate: int | None = None
    basic_access: bool = False


class DataTablesResponse(BaseModel):
    """Readable table list."""

    tables: list[DataTableInfo]


class DataColumnInfo(BaseModel):
    """Column metadata for one table."""

    name: str
    data_type: str
    nullable: bool
    ordinal_position: int


class DataColumnsResponse(BaseModel):
    """Column list for one table."""

    table: str
    columns: list[DataColumnInfo]


class DataRowsResponse(BaseModel):
    """Paged rows from a read-only table query."""

    table: str
    limit: int
    offset: int
    row_count: int
    rows: list[dict[str, Any]] = Field(default_factory=list)
