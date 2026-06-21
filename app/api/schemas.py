from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models import ALERTABLE_METRICS, MetricType, PERCENT_METRICS, ensure_utc_datetime


class MetricSamplePayload(BaseModel):
    sample_id: str = Field(min_length=1, max_length=128)
    vm_id: str = Field(min_length=1, max_length=128)
    metric_type: MetricType
    value: float
    observed_at: datetime

    @field_validator("sample_id", "vm_id")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return ensure_utc_datetime(value)

    @model_validator(mode="after")
    def validate_value_for_metric(self) -> "MetricSamplePayload":
        if self.metric_type in PERCENT_METRICS and not 0 <= self.value <= 100:
            raise ValueError("percentage metric values must be between 0 and 100")
        if self.metric_type not in PERCENT_METRICS and self.value < 0:
            raise ValueError("byte metric values must be non-negative")
        return self


class IngestMetricSamplesRequest(BaseModel):
    samples: list[MetricSamplePayload] = Field(min_length=1)


class IngestMetricSamplesResponse(BaseModel):
    batch_id: str
    accepted_count: int
    idempotent_replay: bool
    status_url: str


class IngestionBatchResponse(BaseModel):
    batch_id: str
    status: str
    submitted_count: int
    processed_count: int
    duplicate_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None


class MetricSampleResponse(BaseModel):
    sample_id: str
    metric_type: MetricType
    value: float
    observed_at: datetime


class MetricSamplesPageResponse(BaseModel):
    vm_id: str
    items: list[MetricSampleResponse]
    next_cursor: str | None = None


class MetricHealthEntryResponse(BaseModel):
    latest_value: float
    threshold: float
    consecutive_breaches: int
    alerting: bool


class VmHealthResponse(BaseModel):
    vm_id: str
    status: str
    last_observed_at: datetime
    metrics: dict[str, MetricHealthEntryResponse]


class AlertResponse(BaseModel):
    alert_id: str
    vm_id: str
    metric_type: MetricType
    threshold: float
    latest_value: float
    consecutive_breaches: int
    status: str
    started_at: datetime
    updated_at: datetime


class ActiveAlertsResponse(BaseModel):
    items: list[AlertResponse]
    next_cursor: str | None = None


class HealthzResponse(BaseModel):
    status: str


class ReadyzResponse(BaseModel):
    status: str
    dependencies: dict[str, str]


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    error: dict[str, Any]


def is_alertable_metric(metric_type: MetricType | None) -> bool:
    return metric_type is None or metric_type in ALERTABLE_METRICS
