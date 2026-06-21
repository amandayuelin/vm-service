from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.models import MetricSampleMessage, MetricType, utc_now
from app.services.processing import ProcessingService


def sample_payload(sample_id: str = "sample-1", value: float = 91.0, metric_type: str = "cpu_usage_percent"):
    return {
        "sample_id": sample_id,
        "vm_id": "vm-1",
        "metric_type": metric_type,
        "value": value,
        "observed_at": "2026-06-21T21:00:00Z",
    }


def test_healthz(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_readyz(client):
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["dependencies"] == {"database": "ok", "kafka": "ok"}


def test_readyz_dependency_unavailable(client, repository):
    repository.available = False

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"


def test_ingest_valid_batch_returns_accepted_and_publishes(client, publisher):
    response = client.post(
        "/metric-samples",
        headers={"Idempotency-Key": "batch-1", "X-Request-ID": "req-test"},
        json={"samples": [sample_payload()]},
    )

    body = response.json()
    assert response.status_code == 202
    assert body["accepted_count"] == 1
    assert body["idempotent_replay"] is False
    assert body["status_url"] == f"/ingestion-batches/{body['batch_id']}"
    assert response.headers["X-Request-ID"] == "req-test"
    assert len(publisher.published) == 1
    assert publisher.published[0].sample_id == "sample-1"


def test_duplicate_idempotency_key_returns_existing_batch(client, publisher):
    first = client.post(
        "/metric-samples",
        headers={"Idempotency-Key": "same-key"},
        json={"samples": [sample_payload("sample-1")]},
    )
    second = client.post(
        "/metric-samples",
        headers={"Idempotency-Key": "same-key"},
        json={"samples": [sample_payload("sample-1")]},
    )

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["batch_id"] == first.json()["batch_id"]
    assert second.json()["idempotent_replay"] is True
    assert len(publisher.published) == 1


def test_ingest_rejects_empty_batch(client):
    response = client.post("/metric-samples", json={"samples": []})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_ingest_rejects_batch_over_limit(client):
    response = client.post(
        "/metric-samples",
        json={
            "samples": [
                sample_payload("sample-1"),
                sample_payload("sample-2"),
                sample_payload("sample-3"),
                sample_payload("sample-4"),
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_ingest_rejects_invalid_metric_value(client):
    response = client.post(
        "/metric-samples",
        json={"samples": [sample_payload(value=101.0)]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_get_ingestion_batch(client, publisher, repository):
    ingest = client.post(
        "/metric-samples",
        headers={"Idempotency-Key": "batch-status"},
        json={"samples": [sample_payload()]},
    )
    batch_id = ingest.json()["batch_id"]
    service = ProcessingService(repository, client.app.state.settings)
    service.process_message(publisher.published[0])

    response = client.get(f"/ingestion-batches/{batch_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSED"
    assert response.json()["processed_count"] == 1


def test_get_ingestion_batch_not_found(client):
    response = client.get("/ingestion-batches/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_metric_query_returns_samples(client, repository, publisher):
    client.post("/metric-samples", json={"samples": [sample_payload("sample-1")]})
    service = ProcessingService(repository, client.app.state.settings)
    service.process_message(publisher.published[0])

    response = client.get(
        "/vms/vm-1/metrics",
        params={
            "start": "2026-06-21T20:00:00Z",
            "end": "2026-06-21T22:00:00Z",
            "metric_type": "cpu_usage_percent",
        },
    )

    assert response.status_code == 200
    assert response.json()["vm_id"] == "vm-1"
    assert response.json()["items"][0]["sample_id"] == "sample-1"


def test_metric_query_rejects_invalid_range(client):
    response = client.get(
        "/vms/vm-1/metrics",
        params={"start": "2026-06-21T22:00:00Z", "end": "2026-06-21T20:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_health_not_found(client):
    response = client.get("/vms/missing/health")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_alert_status_after_three_consecutive_breaches(client, repository, publisher):
    observed_at = datetime(2026, 6, 21, 21, 0, tzinfo=UTC)
    service = ProcessingService(repository, client.app.state.settings)
    batch = client.post(
        "/metric-samples",
        json={
            "samples": [
                sample_payload("sample-1", value=91),
                {**sample_payload("sample-2", value=92), "observed_at": "2026-06-21T21:00:10Z"},
                {**sample_payload("sample-3", value=93), "observed_at": "2026-06-21T21:00:20Z"},
            ]
        },
    )
    assert batch.status_code == 202
    for message in publisher.published:
        service.process_message(message)

    health = client.get("/vms/vm-1/health")
    alerts = client.get("/alerts/active")

    assert health.status_code == 200
    assert health.json()["status"] == "ALERTING"
    assert health.json()["metrics"]["cpu_usage_percent"]["consecutive_breaches"] == 3
    assert alerts.status_code == 200
    assert alerts.json()["items"][0]["vm_id"] == "vm-1"
    assert alerts.json()["items"][0]["metric_type"] == "cpu_usage_percent"

    batch_id = batch.json()["batch_id"]
    assert repository.get_batch(batch_id).processed_count == 3
    assert observed_at.isoformat().startswith("2026-06-21T21:00:00")


def test_below_threshold_sample_resolves_alert(client, repository):
    service = ProcessingService(repository, client.app.state.settings)
    batch, _ = repository.create_or_get_batch(idempotency_key=None, request_id="req", submitted_count=4)
    base = datetime(2026, 6, 21, 21, 0, tzinfo=UTC)

    for index, value in enumerate([91.0, 92.0, 93.0, 50.0]):
        service.process_message(
            MetricSampleMessage(
                message_id=f"msg-{index}",
                batch_id=batch.id,
                sample_id=f"sample-{index}",
                vm_id="vm-1",
                metric_type=MetricType.CPU_USAGE_PERCENT,
                value=value,
                observed_at=base + timedelta(seconds=index * 10),
                received_at=utc_now(),
                request_id="req",
            )
        )

    health = client.get("/vms/vm-1/health")
    alerts = client.get("/alerts/active")

    assert health.json()["status"] == "OK"
    assert health.json()["metrics"]["cpu_usage_percent"]["consecutive_breaches"] == 0
    assert alerts.json()["items"] == []


def test_duplicate_sample_is_not_double_counted(client, repository):
    service = ProcessingService(repository, client.app.state.settings)
    batch, _ = repository.create_or_get_batch(idempotency_key=None, request_id="req", submitted_count=2)
    message = MetricSampleMessage(
        message_id="msg-1",
        batch_id=batch.id,
        sample_id="dup-sample",
        vm_id="vm-1",
        metric_type=MetricType.CPU_USAGE_PERCENT,
        value=95.0,
        observed_at=datetime(2026, 6, 21, 21, 0, tzinfo=UTC),
        received_at=utc_now(),
        request_id="req",
    )

    first = service.process_message(message)
    second = service.process_message(message)

    assert first.inserted is True
    assert second.duplicate is True
    assert len(repository.samples_by_id) == 1
    assert repository.get_batch(batch.id).processed_count == 1
    assert repository.get_batch(batch.id).duplicate_count == 1
