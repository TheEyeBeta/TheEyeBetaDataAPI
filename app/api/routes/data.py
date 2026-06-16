"""Generic read-only data table routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Path, Query

from app.api.dependencies.services import get_data_service
from app.auth.dependencies import get_principal
from app.auth.models import Principal
from app.schemas.data import DataColumnsResponse, DataRowsResponse, DataTablesResponse
from app.services.data_service import DataService

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/tables", response_model=DataTablesResponse)
def list_tables(
    principal: Principal = Depends(get_principal),
    service: DataService = Depends(get_data_service),
) -> DataTablesResponse:
    """List readable theeyebeta tables."""
    return service.list_tables(principal)


@router.get("/tables/{table}/columns", response_model=DataColumnsResponse)
def list_columns(
    table: str = Path(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
    principal: Principal = Depends(get_principal),
    service: DataService = Depends(get_data_service),
) -> DataColumnsResponse:
    """List columns for one readable theeyebeta table."""
    return service.list_columns(principal, table)


@router.get("/tables/{table}/rows", response_model=DataRowsResponse)
def query_rows(
    table: str = Path(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    order_by: str | None = Query(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
    order_dir: str = Query(default="desc", pattern=r"^(asc|desc|ASC|DESC)$"),
    filters: list[str] = Query(default=[], alias="filter"),
    symbol: str | None = Query(default=None, min_length=1, max_length=32),
    date_column: str | None = Query(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    service: DataService = Depends(get_data_service),
) -> DataRowsResponse:
    """Return paged rows from one readable theeyebeta table."""
    return service.query_rows(
        principal=principal,
        table=table,
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
        filters=filters,
        symbol=symbol,
        date_column=date_column,
        start=start,
        end=end,
    )
