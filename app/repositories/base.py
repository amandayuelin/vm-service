from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.models import (
    AlertRecord,
    BatchRecord,
    MetricHealthRecord,
    MetricSampleMessage,
    MetricSampleRecord,
    MetricType,
    Page,
    ProcessSampleResult,
)


class MetricRepository(Protocol):
    def initialize(self) -> None:
        ...

    def health_check(self) -> bool:
        ...

    def create_or_get_batch(
        self,
        *,
        idempotency_key: str | None,
        request_id: str,
        submitted_count: int,
    ) -> tuple[BatchRecord, bool]:
        ...

    def mark_batch_processing(self, batch_id: str) -> None:
        ...

    def mark_batch_failed(self, batch_id: str, error: str) -> None:
        ...

    def get_batch(self, batch_id: str) -> BatchRecord | None:
        ...

    def process_sample(
        self,
        message: MetricSampleMessage,
        *,
        cpu_threshold: float,
        memory_threshold: float,
    ) -> ProcessSampleResult:
        ...

    def list_metric_samples(
        self,
        *,
        vm_id: str,
        start: datetime,
        end: datetime,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        ...

    def get_vm_health(self, vm_id: str) -> list[MetricHealthRecord]:
        ...

    def list_active_alerts(
        self,
        *,
        vm_id: str | None,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        ...
