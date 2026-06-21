from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local end-to-end smoke test.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    client = httpx.Client(base_url=base_url, timeout=5)

    assert_ok(client.get("/healthz"), 200)
    assert_ok(client.get("/readyz"), 200)

    suffix = uuid4().hex[:8]
    vm_id = f"vm-smoke-{suffix}"
    observed_at = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=60)
    samples = [
        {
            "sample_id": f"smoke-{suffix}-{index}",
            "vm_id": vm_id,
            "metric_type": "cpu_usage_percent",
            "value": 91.0 + index,
            "observed_at": (observed_at + timedelta(seconds=index * 10)).isoformat().replace("+00:00", "Z"),
        }
        for index in range(3)
    ]

    ingest_response = assert_ok(
        client.post(
            "/metric-samples",
            headers={"Idempotency-Key": f"smoke-{suffix}"},
            json={"samples": samples},
        ),
        202,
    ).json()
    batch_id = ingest_response["batch_id"]

    replay_response = assert_ok(
        client.post(
            "/metric-samples",
            headers={"Idempotency-Key": f"smoke-{suffix}"},
            json={"samples": samples},
        ),
        200,
    ).json()
    if replay_response["batch_id"] != batch_id or not replay_response["idempotent_replay"]:
        raise AssertionError(f"expected idempotent replay for duplicate batch: {replay_response}")

    deadline = time.time() + args.timeout_seconds
    batch = None
    while time.time() < deadline:
        batch = assert_ok(client.get(f"/ingestion-batches/{batch_id}"), 200).json()
        if batch["status"] == "PROCESSED":
            break
        time.sleep(1)

    if not batch or batch["status"] != "PROCESSED":
        raise AssertionError(f"batch did not process before timeout: {batch}")

    health = assert_ok(client.get(f"/vms/{vm_id}/health"), 200).json()
    if health["status"] != "ALERTING":
        raise AssertionError(f"expected VM to be alerting: {health}")
    if health["metrics"]["cpu_usage_percent"]["consecutive_breaches"] != 3:
        raise AssertionError(f"expected 3 CPU breaches: {health}")

    alerts = assert_ok(client.get("/alerts/active", params={"vm_id": vm_id}), 200).json()
    if len(alerts["items"]) != 1:
        raise AssertionError(f"expected one active alert: {alerts}")

    resolve_sample = {
        "sample_id": f"smoke-{suffix}-resolve",
        "vm_id": vm_id,
        "metric_type": "cpu_usage_percent",
        "value": 50.0,
        "observed_at": (observed_at + timedelta(seconds=40)).isoformat().replace("+00:00", "Z"),
    }
    resolve_batch = assert_ok(
        client.post(
            "/metric-samples",
            headers={"Idempotency-Key": f"smoke-{suffix}-resolve"},
            json={"samples": [resolve_sample]},
        ),
        202,
    ).json()
    wait_for_batch(client, resolve_batch["batch_id"], args.timeout_seconds)

    resolved_health = assert_ok(client.get(f"/vms/{vm_id}/health"), 200).json()
    if resolved_health["status"] != "OK":
        raise AssertionError(f"expected alert to resolve: {resolved_health}")

    resolved_alerts = assert_ok(client.get("/alerts/active", params={"vm_id": vm_id}), 200).json()
    if resolved_alerts["items"]:
        raise AssertionError(f"expected no active alerts after resolution: {resolved_alerts}")

    metrics = assert_ok(
        client.get(
            f"/vms/{vm_id}/metrics",
            params={
                "start": (observed_at - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "end": (observed_at + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "metric_type": "cpu_usage_percent",
            },
        ),
        200,
    ).json()
    if len(metrics["items"]) != 4:
        raise AssertionError(f"expected 4 stored metrics: {metrics}")

    print(
        {
            "status": "ok",
            "batch_id": batch_id,
            "vm_id": vm_id,
            "processed_count": batch["processed_count"],
            "idempotent_replay": replay_response["idempotent_replay"],
            "active_alerts_after_breach": len(alerts["items"]),
            "active_alerts_after_resolution": len(resolved_alerts["items"]),
            "metrics_returned": len(metrics["items"]),
        }
    )


def assert_ok(response: httpx.Response, expected_status: int) -> httpx.Response:
    if response.status_code != expected_status:
        raise AssertionError(
            f"expected {expected_status}, got {response.status_code}: {response.text}"
        )
    return response


def wait_for_batch(client: httpx.Client, batch_id: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    batch = None
    while time.time() < deadline:
        batch = assert_ok(client.get(f"/ingestion-batches/{batch_id}"), 200).json()
        if batch["status"] == "PROCESSED":
            return batch
        time.sleep(1)
    raise AssertionError(f"batch did not process before timeout: {batch}")


if __name__ == "__main__":
    main()
