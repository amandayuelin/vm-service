from __future__ import annotations

from uuid import uuid4

from app.api.schemas import IngestMetricSamplesRequest, IngestMetricSamplesResponse
from app.core.config import Settings
from app.core.errors import ApiError
from app.domain.models import MetricSampleMessage, is_too_far_in_future, utc_now
from app.messaging.publisher import MetricPublisher
from app.repositories.base import MetricRepository


class IngestionService:
    def __init__(self, repository: MetricRepository, publisher: MetricPublisher, settings: Settings) -> None:
        self._repository = repository
        self._publisher = publisher
        self._settings = settings

    def ingest(
        self,
        request: IngestMetricSamplesRequest,
        *,
        idempotency_key: str | None,
        request_id: str,
    ) -> IngestMetricSamplesResponse:
        if len(request.samples) > self._settings.max_ingest_batch_size:
            raise ApiError(
                400,
                "bad_request",
                "Batch exceeds maximum allowed size.",
                {"max_ingest_batch_size": self._settings.max_ingest_batch_size},
            )

        for sample in request.samples:
            if is_too_far_in_future(sample.observed_at, self._settings.max_future_skew_seconds):
                raise ApiError(
                    400,
                    "bad_request",
                    "Metric sample timestamp is too far in the future.",
                    {"sample_id": sample.sample_id},
                )

        batch, replay = self._repository.create_or_get_batch(
            idempotency_key=idempotency_key,
            request_id=request_id,
            submitted_count=len(request.samples),
        )

        if replay:
            return IngestMetricSamplesResponse(
                batch_id=batch.id,
                accepted_count=batch.submitted_count,
                idempotent_replay=True,
                status_url=f"/ingestion-batches/{batch.id}",
            )

        received_at = utc_now()
        messages = [
            MetricSampleMessage(
                message_id=f"msg-{uuid4()}",
                batch_id=batch.id,
                sample_id=sample.sample_id,
                vm_id=sample.vm_id,
                metric_type=sample.metric_type,
                value=sample.value,
                observed_at=sample.observed_at,
                received_at=received_at,
                request_id=request_id,
            )
            for sample in request.samples
        ]

        try:
            self._publisher.publish_samples(messages)
        except ApiError as exc:
            self._repository.mark_batch_failed(batch.id, exc.message)
            raise
        except Exception as exc:
            self._repository.mark_batch_failed(batch.id, "Kafka publish failed.")
            raise ApiError(503, "dependency_unavailable", "Failed to publish metric samples to Kafka.") from exc

        self._repository.mark_batch_processing(batch.id)
        return IngestMetricSamplesResponse(
            batch_id=batch.id,
            accepted_count=len(request.samples),
            idempotent_replay=False,
            status_url=f"/ingestion-batches/{batch.id}",
        )

