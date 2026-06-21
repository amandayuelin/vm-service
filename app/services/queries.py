from __future__ import annotations

from datetime import timedelta

from app.core.config import Settings
from app.core.errors import ApiError
from app.domain.models import ALERTABLE_METRICS, MetricType, Page, VmStatus
from app.repositories.base import MetricRepository


class QueryService:
    def __init__(self, repository: MetricRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def list_metric_samples(
        self,
        *,
        vm_id: str,
        start,
        end,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        if start >= end:
            raise ApiError(400, "bad_request", "start must be before end.")
        if end - start > timedelta(hours=self._settings.max_raw_query_hours):
            raise ApiError(
                400,
                "bad_request",
                "Raw metric query time range is too large.",
                {"max_raw_query_hours": self._settings.max_raw_query_hours},
            )
        bounded_limit = self._validate_limit(limit)
        return self._repository.list_metric_samples(
            vm_id=vm_id,
            start=start,
            end=end,
            metric_type=metric_type,
            limit=bounded_limit,
            cursor=cursor,
        )

    def get_vm_health(self, vm_id: str):
        health_rows = self._repository.get_vm_health(vm_id)
        if not health_rows:
            raise ApiError(404, "not_found", "VM health was not found.", {"vm_id": vm_id})
        alerting = any(row.alerting for row in health_rows if row.metric_type in ALERTABLE_METRICS)
        last_observed_at = max(row.latest_observed_at for row in health_rows)
        metrics = {
            row.metric_type.value: {
                "latest_value": row.latest_value,
                "threshold": row.threshold,
                "consecutive_breaches": row.consecutive_breaches,
                "alerting": row.alerting,
            }
            for row in health_rows
        }
        return {
            "vm_id": vm_id,
            "status": VmStatus.ALERTING.value if alerting else VmStatus.OK.value,
            "last_observed_at": last_observed_at,
            "metrics": metrics,
        }

    def list_active_alerts(
        self,
        *,
        vm_id: str | None,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        if metric_type is not None and metric_type not in ALERTABLE_METRICS:
            raise ApiError(400, "bad_request", "Only CPU and memory metrics can have active alerts.")
        return self._repository.list_active_alerts(
            vm_id=vm_id,
            metric_type=metric_type,
            limit=self._validate_limit(limit),
            cursor=cursor,
        )

    def _validate_limit(self, limit: int) -> int:
        if limit < 1:
            raise ApiError(400, "bad_request", "limit must be at least 1.")
        if limit > self._settings.max_page_size:
            raise ApiError(
                400,
                "bad_request",
                "limit exceeds maximum page size.",
                {"max_page_size": self._settings.max_page_size},
            )
        return limit

