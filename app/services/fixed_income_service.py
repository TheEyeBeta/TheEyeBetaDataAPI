"""Fixed-income regime use-cases."""

from __future__ import annotations

from datetime import date

from app.domain.models import (
    FixedIncomeCurveMetric,
    FixedIncomeETFProxyPrice,
    FixedIncomeSignal,
)
from app.repositories.interfaces import FixedIncomeRepository
from app.schemas.fixed_income import (
    FixedIncomeCurveMetricResponse,
    FixedIncomeETFProxyPriceResponse,
    FixedIncomeHistoryResponse,
    FixedIncomeRegimeResponse,
    FixedIncomeSignalResponse,
    FixedIncomeSignalsResponse,
)


class FixedIncomeService:
    """Read-focused fixed-income regime service."""

    def __init__(self, repository: FixedIncomeRepository) -> None:
        self._repository = repository

    def get_regime(self) -> FixedIncomeRegimeResponse | None:
        latest = self._repository.get_latest_metric(country="US")
        if latest is None:
            return None
        return FixedIncomeRegimeResponse(
            latest=self._to_metric_response(latest),
            signals=[
                self._to_signal_response(signal)
                for signal in self._repository.get_signals(
                    country=latest.country,
                    as_of_date=latest.date,
                    limit=50,
                )
            ],
            etf_proxies=[
                self._to_proxy_response(proxy)
                for proxy in self._repository.get_etf_proxy_prices()
            ],
        )

    def get_history(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int = 252,
    ) -> FixedIncomeHistoryResponse:
        metrics = self._repository.get_history(country="US", start=start, end=end, limit=limit)
        return FixedIncomeHistoryResponse(
            count=len(metrics),
            metrics=[self._to_metric_response(metric) for metric in metrics],
        )

    def get_signals(self, *, limit: int = 50) -> FixedIncomeSignalsResponse:
        signals = self._repository.get_signals(country="US", limit=limit)
        return FixedIncomeSignalsResponse(
            count=len(signals),
            signals=[self._to_signal_response(signal) for signal in signals],
        )

    @staticmethod
    def _to_metric_response(metric: FixedIncomeCurveMetric) -> FixedIncomeCurveMetricResponse:
        return FixedIncomeCurveMetricResponse(**vars(metric))

    @staticmethod
    def _to_signal_response(signal: FixedIncomeSignal) -> FixedIncomeSignalResponse:
        return FixedIncomeSignalResponse(**vars(signal))

    @staticmethod
    def _to_proxy_response(proxy: FixedIncomeETFProxyPrice) -> FixedIncomeETFProxyPriceResponse:
        return FixedIncomeETFProxyPriceResponse(**vars(proxy))
