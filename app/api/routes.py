from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Header, Query, Request, Response, status

from app.api.schemas import (
    ActiveAlertsResponse,
    AlertResponse,
    HealthzResponse,
    IngestMetricSamplesRequest,
    IngestMetricSamplesResponse,
    IngestionBatchResponse,
    MetricSampleResponse,
    MetricSamplesPageResponse,
    ReadyzResponse,
    VmHealthResponse,
)
from app.core.errors import ApiError
from app.domain.models import AlertRecord, MetricSampleRecord, MetricType, ensure_utc_datetime
from app.messaging.publisher import MetricPublisher
from app.repositories.base import MetricRepository


def register_routes(app: FastAPI, repository: MetricRepository, publisher: MetricPublisher) -> None:
    @app.get("/healthz", response_model=HealthzResponse)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=ReadyzResponse)
    def readyz() -> dict[str, object]:
        database_ok = repository.health_check()
        kafka_ok = publisher.health_check()
        dependencies = {
            "database": "ok" if database_ok else "unavailable",
            "kafka": "ok" if kafka_ok else "unavailable",
        }
        if not database_ok or not kafka_ok:
            raise ApiError(503, "dependency_unavailable", "One or more dependencies are unavailable.", dependencies)
        return {"status": "ready", "dependencies": dependencies}

    @app.post(
        "/metric-samples",
        response_model=IngestMetricSamplesResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def ingest_metric_samples(
        body: IngestMetricSamplesRequest,
        request: Request,
        response: Response,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> IngestMetricSamplesResponse:
        service_response = app.state.ingestion_service.ingest(
            body,
            idempotency_key=idempotency_key,
            request_id=str(request.state.request_id),
        )
        if service_response.idempotent_replay:
            response.status_code = status.HTTP_200_OK
        return service_response

    @app.get("/ingestion-batches/{batch_id}", response_model=IngestionBatchResponse)
    def get_ingestion_batch(batch_id: str) -> IngestionBatchResponse:
        batch = repository.get_batch(batch_id)
        if batch is None:
            raise ApiError(404, "not_found", "Ingestion batch was not found.", {"batch_id": batch_id})
        return IngestionBatchResponse(
            batch_id=batch.id,
            status=batch.status.value,
            submitted_count=batch.submitted_count,
            processed_count=batch.processed_count,
            duplicate_count=batch.duplicate_count,
            failed_count=batch.failed_count,
            last_error=batch.last_error,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
        )

    @app.get("/vms/{vm_id}/metrics", response_model=MetricSamplesPageResponse)
    def list_metric_samples(
        vm_id: str,
        start: Annotated[datetime, Query()],
        end: Annotated[datetime, Query()],
        metric_type: Annotated[MetricType | None, Query()] = None,
        limit: Annotated[int, Query()] = 100,
        cursor: Annotated[str | None, Query()] = None,
    ) -> MetricSamplesPageResponse:
        page = app.state.query_service.list_metric_samples(
            vm_id=vm_id,
            start=ensure_utc_datetime(start),
            end=ensure_utc_datetime(end),
            metric_type=metric_type,
            limit=limit,
            cursor=cursor,
        )
        return MetricSamplesPageResponse(
            vm_id=vm_id,
            items=[_sample_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @app.get("/vms/{vm_id}/health", response_model=VmHealthResponse)
    def get_vm_health(vm_id: str) -> dict[str, object]:
        return app.state.query_service.get_vm_health(vm_id)

    @app.get("/alerts/active", response_model=ActiveAlertsResponse)
    def list_active_alerts(
        vm_id: Annotated[str | None, Query()] = None,
        metric_type: Annotated[MetricType | None, Query()] = None,
        limit: Annotated[int, Query()] = 100,
        cursor: Annotated[str | None, Query()] = None,
    ) -> ActiveAlertsResponse:
        page = app.state.query_service.list_active_alerts(
            vm_id=vm_id,
            metric_type=metric_type,
            limit=limit,
            cursor=cursor,
        )
        return ActiveAlertsResponse(
            items=[_alert_response(item) for item in page.items],
            next_cursor=page.next_cursor,
        )


def _sample_response(sample: MetricSampleRecord) -> MetricSampleResponse:
    return MetricSampleResponse(
        sample_id=sample.sample_id,
        metric_type=sample.metric_type,
        value=sample.value,
        observed_at=sample.observed_at,
    )


def _alert_response(alert: AlertRecord) -> AlertResponse:
    return AlertResponse(
        alert_id=alert.id,
        vm_id=alert.vm_id,
        metric_type=alert.metric_type,
        threshold=alert.threshold,
        latest_value=alert.latest_value,
        consecutive_breaches=alert.consecutive_breaches,
        status=alert.status.value,
        started_at=alert.started_at,
        updated_at=alert.updated_at,
    )

