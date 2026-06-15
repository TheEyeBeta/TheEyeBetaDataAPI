"""Macro indicator / regime use-cases."""

from __future__ import annotations

from datetime import date

from app.domain.macro_registry import MACRO_SERIES_METADATA
from app.domain.models import MacroRegimeSnapshot
from app.repositories.interfaces import MacroRepository
from app.schemas.macro import (
    MacroLatestItem,
    MacroLatestResponse,
    MacroObservationPoint,
    MacroRegimeResponse,
    MacroSeriesDetailResponse,
    MacroSeriesListResponse,
    MacroSeriesSummary,
)


class MacroService:
    """Read-focused macro capability service."""

    def __init__(self, repository: MacroRepository) -> None:
        self._repository = repository

    def list_series(self, *, category: str | None = None) -> MacroSeriesListResponse:
        """List every series that has data, enriched with registry metadata."""
        stats = self._repository.get_series_stats()
        series: list[MacroSeriesSummary] = []
        for stat in stats:
            meta = MACRO_SERIES_METADATA.get(stat.code)
            if category and (meta is None or meta.category != category.strip().lower()):
                continue
            series.append(
                MacroSeriesSummary(
                    code=stat.code,
                    name=meta.name if meta else None,
                    category=meta.category if meta else None,
                    frequency=meta.frequency if meta else None,
                    units=meta.units if meta else None,
                    source=stat.source or (meta.source if meta else None),
                    seasonal_adj=meta.seasonal_adj if meta else None,
                    latest_value=stat.latest_value,
                    latest_date=stat.latest_date,
                    observation_count=stat.observation_count,
                    in_registry=meta is not None,
                )
            )
        return MacroSeriesListResponse(count=len(series), series=series)

    def get_series(
        self,
        *,
        code: str,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
    ) -> MacroSeriesDetailResponse | None:
        """Return metadata plus observations for one series, or None if unknown."""
        if not self._repository.series_exists(code):
            return None
        observations = self._repository.get_observations(
            code=code, start=start, end=end, limit=limit
        )
        meta = MACRO_SERIES_METADATA.get(code)
        return MacroSeriesDetailResponse(
            code=code,
            name=meta.name if meta else None,
            category=meta.category if meta else None,
            frequency=meta.frequency if meta else None,
            units=meta.units if meta else None,
            source=meta.source if meta else None,
            seasonal_adj=meta.seasonal_adj if meta else None,
            in_registry=meta is not None,
            observation_count=len(observations),
            start=start,
            end=end,
            observations=[
                MacroObservationPoint(date=o.date, value=o.value) for o in observations
            ],
        )

    def get_latest(self, *, codes: list[str] | None = None) -> MacroLatestResponse:
        """Return the most recent observation for each (optionally filtered) series."""
        points = self._repository.get_latest_points(codes=codes)
        items: list[MacroLatestItem] = []
        for point in points:
            meta = MACRO_SERIES_METADATA.get(point.code)
            items.append(
                MacroLatestItem(
                    code=point.code,
                    name=meta.name if meta else None,
                    category=meta.category if meta else None,
                    units=meta.units if meta else None,
                    date=point.date,
                    value=point.value,
                    source=point.source or (meta.source if meta else None),
                )
            )
        return MacroLatestResponse(count=len(items), observations=items)

    def get_regime(self) -> MacroRegimeResponse | None:
        """Return the latest regime snapshot, or None when none exists."""
        snapshot = self._repository.get_latest_regime()
        if snapshot is None:
            return None
        return self._to_regime_response(snapshot)

    @staticmethod
    def _to_regime_response(snapshot: MacroRegimeSnapshot) -> MacroRegimeResponse:
        return MacroRegimeResponse(**vars(snapshot))
