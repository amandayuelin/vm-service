from __future__ import annotations

import json
from datetime import UTC, datetime

from app.domain.models import MetricSampleMessage, MetricType, utc_now
from app.repositories.in_memory import InMemoryMetricRepository
from app.services.processing import ProcessingService
from app.workers.metrics_worker import process_kafka_payload


def test_process_kafka_payload_processes_message(settings):
    repository = InMemoryMetricRepository()
    service = ProcessingService(repository, settings)
    batch, _ = repository.create_or_get_batch(idempotency_key=None, request_id="req", submitted_count=1)
    message = MetricSampleMessage(
        message_id="msg-1",
        batch_id=batch.id,
        sample_id="sample-1",
        vm_id="vm-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        value=91.0,
        observed_at=datetime(2026, 6, 21, 21, 0, tzinfo=UTC),
        received_at=utc_now(),
        request_id="req",
    )

    result = process_kafka_payload(json.dumps(message.to_kafka_payload()).encode("utf-8"), service)

    assert result.inserted is True
    assert repository.get_batch(batch.id).processed_count == 1
