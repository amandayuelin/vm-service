from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class MetricType(StrEnum):
    CPU_USAGE_PERCENT = "cpu_usage_percent"
    MEMORY_USAGE_PERCENT = "memory_usage_percent"
    DISK_USAGE_PERCENT = "disk_usage_percent"
    NETWORK_IN_BYTES = "network_in_bytes"
    NETWORK_OUT_BYTES = "network_out_bytes"


PERCENT_METRICS = {
    MetricType.CPU_USAGE_PERCENT,
    MetricType.MEMORY_USAGE_PERCENT,
    MetricType.DISK_USAGE_PERCENT,
}

ALERTABLE_METRICS = {
    MetricType.CPU_USAGE_PERCENT,
    MetricType.MEMORY_USAGE_PERCENT,
}


class BatchStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    PARTIAL_FAILED = "PARTIAL_FAILED"
    FAILED = "FAILED"


class AlertStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class VmStatus(StrEnum):
    OK = "OK"
    ALERTING = "ALERTING"


@dataclass(frozen=True)
class BatchRecord:
    id: str
    idempotency_key: str | None
    request_id: str | None
    status: BatchStatus
    submitted_count: int
    processed_count: int
    duplicate_count: int
    failed_count: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MetricSampleMessage:
    message_id: str
    batch_id: str
    sample_id: str
    vm_id: str
    metric_type: MetricType
    value: float
    observed_at: datetime
    received_at: datetime
    request_id: str

    def to_kafka_payload(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "batch_id": self.batch_id,
            "sample_id": self.sample_id,
            "vm_id": self.vm_id,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "observed_at": self.observed_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "request_id": self.request_id,
        }

    @classmethod
    def from_kafka_payload(cls, payload: dict[str, Any]) -> "MetricSampleMessage":
        return cls(
            message_id=str(payload["message_id"]),
            batch_id=str(payload["batch_id"]),
            sample_id=str(payload["sample_id"]),
            vm_id=str(payload["vm_id"]),
            metric_type=MetricType(str(payload["metric_type"])),
            value=float(payload["value"]),
            observed_at=ensure_utc_datetime(parse_datetime(str(payload["observed_at"]))),
            received_at=ensure_utc_datetime(parse_datetime(str(payload["received_at"]))),
            request_id=str(payload["request_id"]),
        )


@dataclass(frozen=True)
class MetricSampleRecord:
    id: int | None
    sample_id: str
    batch_id: str | None
    vm_id: str
    metric_type: MetricType
    value: float
    observed_at: datetime
    received_at: datetime
    processed_at: datetime | None


@dataclass(frozen=True)
class MetricHealthRecord:
    vm_id: str
    metric_type: MetricType
    latest_value: float
    latest_sample_id: str
    latest_observed_at: datetime
    threshold: float
    consecutive_breaches: int
    alerting: bool
    updated_at: datetime


@dataclass(frozen=True)
class AlertRecord:
    id: str
    vm_id: str
    metric_type: MetricType
    threshold: float
    latest_value: float
    consecutive_breaches: int
    status: AlertStatus
    started_at: datetime
    resolved_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class ProcessSampleResult:
    sample_id: str
    inserted: bool
    duplicate: bool
    alert_transition: str | None = None


@dataclass(frozen=True)
class Page:
    items: list[Any]
    next_cursor: str | None


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def floor_to_hour(value: datetime) -> datetime:
    value = ensure_utc_datetime(value)
    return value.replace(minute=0, second=0, microsecond=0)


def is_too_far_in_future(value: datetime, max_skew_seconds: int, now: datetime | None = None) -> bool:
    reference = now or utc_now()
    return ensure_utc_datetime(value) > reference + timedelta(seconds=max_skew_seconds)


def encode_cursor(observed_at: datetime, row_id: int | None) -> str:
    payload = {"observed_at": ensure_utc_datetime(observed_at).isoformat(), "id": row_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, int | None]:
    raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
    payload = json.loads(raw.decode("utf-8"))
    return ensure_utc_datetime(parse_datetime(str(payload["observed_at"]))), payload.get("id")

