from __future__ import annotations

from threading import RLock
from uuid import uuid4

from app.domain.models import (
    AlertRecord,
    AlertStatus,
    BatchRecord,
    BatchStatus,
    MetricHealthRecord,
    MetricSampleMessage,
    MetricSampleRecord,
    MetricType,
    Page,
    ProcessSampleResult,
    decode_cursor,
    encode_cursor,
    floor_to_hour,
    utc_now,
)


class InMemoryMetricRepository:
    """Test double for the repository contract. The product repository is PostgreSQL."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.batches: dict[str, BatchRecord] = {}
        self.idempotency_keys: dict[str, str] = {}
        self.samples_by_id: dict[str, MetricSampleRecord] = {}
        self.aggregates: dict[tuple[str, MetricType, object], dict[str, float | int | object]] = {}
        self.health: dict[tuple[str, MetricType], MetricHealthRecord] = {}
        self.alerts: dict[str, AlertRecord] = {}
        self._next_sample_row_id = 1
        self.available = True

    def initialize(self) -> None:
        return None

    def health_check(self) -> bool:
        return self.available

    def create_or_get_batch(
        self,
        *,
        idempotency_key: str | None,
        request_id: str,
        submitted_count: int,
    ) -> tuple[BatchRecord, bool]:
        with self._lock:
            if idempotency_key and idempotency_key in self.idempotency_keys:
                return self.batches[self.idempotency_keys[idempotency_key]], True

            now = utc_now()
            batch = BatchRecord(
                id=f"batch-{uuid4()}",
                idempotency_key=idempotency_key,
                request_id=request_id,
                status=BatchStatus.ACCEPTED,
                submitted_count=submitted_count,
                processed_count=0,
                duplicate_count=0,
                failed_count=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            self.batches[batch.id] = batch
            if idempotency_key:
                self.idempotency_keys[idempotency_key] = batch.id
            return batch, False

    def mark_batch_processing(self, batch_id: str) -> None:
        with self._lock:
            batch = self.batches.get(batch_id)
            if batch and batch.status == BatchStatus.ACCEPTED:
                self.batches[batch_id] = _copy_batch(batch, status=BatchStatus.PROCESSING)

    def mark_batch_failed(self, batch_id: str, error: str) -> None:
        with self._lock:
            batch = self.batches.get(batch_id)
            if batch:
                self.batches[batch_id] = _copy_batch(
                    batch,
                    status=BatchStatus.FAILED,
                    failed_count=batch.submitted_count,
                    last_error=error,
                )

    def get_batch(self, batch_id: str) -> BatchRecord | None:
        return self.batches.get(batch_id)

    def process_sample(
        self,
        message: MetricSampleMessage,
        *,
        cpu_threshold: float,
        memory_threshold: float,
    ) -> ProcessSampleResult:
        with self._lock:
            if message.sample_id in self.samples_by_id:
                self._increment_batch(message.batch_id, duplicate_delta=1)
                return ProcessSampleResult(sample_id=message.sample_id, inserted=False, duplicate=True)

            record = MetricSampleRecord(
                id=self._next_sample_row_id,
                sample_id=message.sample_id,
                batch_id=message.batch_id,
                vm_id=message.vm_id,
                metric_type=message.metric_type,
                value=message.value,
                observed_at=message.observed_at,
                received_at=message.received_at,
                processed_at=utc_now(),
            )
            self._next_sample_row_id += 1
            self.samples_by_id[message.sample_id] = record
            self._upsert_aggregate(message)
            transition = self._update_health_and_alerts(message, cpu_threshold, memory_threshold)
            self._increment_batch(message.batch_id, processed_delta=1)
            return ProcessSampleResult(
                sample_id=message.sample_id,
                inserted=True,
                duplicate=False,
                alert_transition=transition,
            )

    def _upsert_aggregate(self, message: MetricSampleMessage) -> None:
        key = (message.vm_id, message.metric_type, floor_to_hour(message.observed_at))
        aggregate = self.aggregates.get(key)
        if aggregate is None:
            self.aggregates[key] = {
                "sample_count": 1,
                "sum_value": message.value,
                "min_value": message.value,
                "max_value": message.value,
            }
            return
        aggregate["sample_count"] = int(aggregate["sample_count"]) + 1
        aggregate["sum_value"] = float(aggregate["sum_value"]) + message.value
        aggregate["min_value"] = min(float(aggregate["min_value"]), message.value)
        aggregate["max_value"] = max(float(aggregate["max_value"]), message.value)

    def _update_health_and_alerts(
        self,
        message: MetricSampleMessage,
        cpu_threshold: float,
        memory_threshold: float,
    ) -> str | None:
        if message.metric_type == MetricType.CPU_USAGE_PERCENT:
            threshold = cpu_threshold
        elif message.metric_type == MetricType.MEMORY_USAGE_PERCENT:
            threshold = memory_threshold
        else:
            return None

        key = (message.vm_id, message.metric_type)
        current = self.health.get(key)
        if current and current.latest_observed_at > message.observed_at:
            return None

        breached = message.value > threshold
        consecutive_breaches = (current.consecutive_breaches + 1) if breached and current else (1 if breached else 0)
        alerting = consecutive_breaches >= 3
        now = utc_now()
        self.health[key] = MetricHealthRecord(
            vm_id=message.vm_id,
            metric_type=message.metric_type,
            latest_value=message.value,
            latest_sample_id=message.sample_id,
            latest_observed_at=message.observed_at,
            threshold=threshold,
            consecutive_breaches=consecutive_breaches,
            alerting=alerting,
            updated_at=now,
        )

        active = self._find_active_alert(message.vm_id, message.metric_type)
        if alerting:
            if active:
                updated = AlertRecord(
                    id=active.id,
                    vm_id=active.vm_id,
                    metric_type=active.metric_type,
                    threshold=threshold,
                    latest_value=message.value,
                    consecutive_breaches=consecutive_breaches,
                    status=AlertStatus.ACTIVE,
                    started_at=active.started_at,
                    resolved_at=None,
                    updated_at=now,
                )
                self.alerts[active.id] = updated
                return "updated"

            alert = AlertRecord(
                id=f"alert-{uuid4()}",
                vm_id=message.vm_id,
                metric_type=message.metric_type,
                threshold=threshold,
                latest_value=message.value,
                consecutive_breaches=consecutive_breaches,
                status=AlertStatus.ACTIVE,
                started_at=now,
                resolved_at=None,
                updated_at=now,
            )
            self.alerts[alert.id] = alert
            return "created"

        if active:
            self.alerts[active.id] = AlertRecord(
                id=active.id,
                vm_id=active.vm_id,
                metric_type=active.metric_type,
                threshold=active.threshold,
                latest_value=message.value,
                consecutive_breaches=0,
                status=AlertStatus.RESOLVED,
                started_at=active.started_at,
                resolved_at=now,
                updated_at=now,
            )
            return "resolved"
        return None

    def _find_active_alert(self, vm_id: str, metric_type: MetricType) -> AlertRecord | None:
        for alert in self.alerts.values():
            if alert.vm_id == vm_id and alert.metric_type == metric_type and alert.status == AlertStatus.ACTIVE:
                return alert
        return None

    def _increment_batch(
        self,
        batch_id: str,
        *,
        processed_delta: int = 0,
        duplicate_delta: int = 0,
        failed_delta: int = 0,
    ) -> None:
        batch = self.batches.get(batch_id)
        if not batch:
            return
        processed = batch.processed_count + processed_delta
        duplicate = batch.duplicate_count + duplicate_delta
        failed = batch.failed_count + failed_delta
        total_done = processed + duplicate + failed
        if total_done < batch.submitted_count:
            status = BatchStatus.PROCESSING
        elif failed == batch.submitted_count:
            status = BatchStatus.FAILED
        elif failed > 0:
            status = BatchStatus.PARTIAL_FAILED
        else:
            status = BatchStatus.PROCESSED
        self.batches[batch_id] = _copy_batch(
            batch,
            status=status,
            processed_count=processed,
            duplicate_count=duplicate,
            failed_count=failed,
        )

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
        cursor_observed_at = None
        cursor_id = None
        if cursor:
            cursor_observed_at, cursor_id = decode_cursor(cursor)

        rows = [
            sample
            for sample in self.samples_by_id.values()
            if sample.vm_id == vm_id
            and start <= sample.observed_at <= end
            and (metric_type is None or sample.metric_type == metric_type)
        ]
        rows.sort(key=lambda sample: (sample.observed_at, sample.id or 0), reverse=True)
        if cursor_observed_at is not None:
            rows = [
                sample
                for sample in rows
                if (sample.observed_at, sample.id or 0) < (cursor_observed_at, int(cursor_id or 0))
            ]

        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last.observed_at, last.id)
            rows = rows[:limit]
        return Page(items=rows, next_cursor=next_cursor)

    def get_vm_health(self, vm_id: str) -> list[MetricHealthRecord]:
        rows = [row for (stored_vm_id, _), row in self.health.items() if stored_vm_id == vm_id]
        rows.sort(key=lambda row: row.metric_type.value)
        return rows

    def list_active_alerts(
        self,
        *,
        vm_id: str | None,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        cursor_updated_at = None
        cursor_id = None
        if cursor:
            cursor_updated_at, cursor_id = decode_cursor(cursor)

        rows = [
            alert
            for alert in self.alerts.values()
            if alert.status == AlertStatus.ACTIVE
            and (vm_id is None or alert.vm_id == vm_id)
            and (metric_type is None or alert.metric_type == metric_type)
        ]
        rows.sort(key=lambda alert: (alert.updated_at, alert.id), reverse=True)
        if cursor_updated_at is not None:
            rows = [alert for alert in rows if (alert.updated_at, alert.id) < (cursor_updated_at, str(cursor_id))]

        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last.updated_at, last.id)
            rows = rows[:limit]
        return Page(items=rows, next_cursor=next_cursor)


def _copy_batch(batch: BatchRecord, **changes) -> BatchRecord:
    values = {
        "id": batch.id,
        "idempotency_key": batch.idempotency_key,
        "request_id": batch.request_id,
        "status": batch.status,
        "submitted_count": batch.submitted_count,
        "processed_count": batch.processed_count,
        "duplicate_count": batch.duplicate_count,
        "failed_count": batch.failed_count,
        "last_error": batch.last_error,
        "created_at": batch.created_at,
        "updated_at": utc_now(),
    }
    values.update(changes)
    return BatchRecord(**values)
