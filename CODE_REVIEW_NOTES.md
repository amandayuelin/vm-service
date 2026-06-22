# Code Review Notes

Use this as the interview walkthrough script. The goal is to show that the project is not just a toy API: it has a clear problem model, async processing, persistence, tests, deployment automation, and explicit production trade-offs.

## 1. Problem And Scale

This service ingests VM metric samples for a cloud platform. VMs report CPU, memory, disk, network ingress, and network egress metrics. The API accepts ingestion quickly, processing happens asynchronously, PostgreSQL stores durable state, and users can query recent metrics, VM health, and active alerts.

Scale from the prompt:

- 100,000 VMs.
- 5 metric types per VM.
- Metrics every 10 seconds.
- About 50,000 samples/sec steady state.
- Up to 100,000 samples/sec peak.
- p95 ingestion API latency target under 200ms.
- Processing can be eventually consistent within about 30 seconds.

## 2. Current Demo Architecture

Actual deployed architecture:

```text
Client
-> DigitalOcean App Platform ingress / built-in load balancing
-> FastAPI API service
-> Kafka on self-managed data Droplet
-> App Platform worker
-> PostgreSQL on self-managed data Droplet
```

The App Platform ingress is the public entrypoint and load balancing layer. No standalone DigitalOcean Load Balancer is required for this deployment.

For the interview deployment, PostgreSQL and Kafka run on one data Droplet through Docker Compose. This provisions quickly and keeps the demo within the interview time box. The production evolution is documented under `infra/production-reference` and replaces the Droplet with DigitalOcean Managed PostgreSQL and Managed Kafka.

## 3. Code Map

- `app/main.py`: FastAPI app construction and dependency wiring.
- `app/api/routes.py`: REST endpoints.
- `app/api/schemas.py`: Pydantic request/response models.
- `app/core/config.py`: environment-based configuration.
- `app/core/errors.py`: consistent JSON API errors.
- `app/core/middleware.py`: request ID middleware.
- `app/domain/models.py`: domain enums and records.
- `app/messaging/publisher.py`: Kafka producer integration.
- `app/repositories/postgres.py`: PostgreSQL repository and schema setup.
- `app/repositories/in_memory.py`: deterministic test repository.
- `app/services/ingestion.py`: ingestion use case.
- `app/services/processing.py`: worker-side processing and alert rules.
- `app/services/queries.py`: read/query use cases.
- `app/workers/metrics_worker.py`: Kafka consumer entrypoint.

## 4. Ingestion Flow

`POST /metric-samples` is intentionally lightweight:

1. FastAPI/Pydantic validates the request shape.
2. The ingestion service creates or replays an ingestion batch.
3. Samples are published to Kafka.
4. The API returns quickly with `202 Accepted`.

The API does not do heavy metric processing synchronously. That protects ingestion latency and keeps the request path stateless.

## 5. Worker Processing Flow

The worker consumes Kafka messages and performs the durable state changes:

1. Parse the Kafka payload into a domain message.
2. Insert the raw metric sample into PostgreSQL.
3. Update hourly aggregates.
4. Update latest VM health state.
5. Apply alerting rules.
6. Commit the Kafka offset only after successful processing.

Alert rule:

- CPU or memory above threshold for 3 consecutive samples marks the VM alerting.
- A healthy sample resolves the active alert.

## 6. Correctness And Idempotency

Correctness for this problem means duplicate submissions do not double-count metrics and query APIs reflect processed state.

The implementation uses:

- Client-provided `sample_id` as the natural deduplication key.
- Ingestion batch idempotency through `Idempotency-Key`.
- PostgreSQL uniqueness constraints to avoid duplicate raw samples.
- Worker processing that can safely retry because duplicate samples are detected by the repository.

For the interview, duplicate batch replay returns the existing batch result. This is simple to explain and friendlier than failing client retries with conflicts.

## 7. API Contract

Core endpoints:

- `GET /healthz`
- `GET /readyz`
- `POST /metric-samples`
- `GET /ingestion-batches/{batch_id}`
- `GET /vms/{vm_id}/metrics`
- `GET /vms/{vm_id}/health`
- `GET /alerts/active`

Operational checks:

- `/healthz` verifies the API process is alive.
- `/readyz` verifies PostgreSQL and Kafka connectivity.

The deployed service currently returns:

```json
{
  "status": "ready",
  "dependencies": {
    "database": "ok",
    "kafka": "ok"
  }
}
```

## 8. Testing Strategy

Tests are deterministic and fast:

- `tests/test_api.py`: endpoint behavior, validation, query paths, idempotency.
- `tests/test_worker.py`: worker processing logic.
- `tests/test_config.py`: configuration behavior, including Kafka CA support for managed Kafka evolution.
- `tests/test_render_app_spec.py`: App Spec rendering correctness.

Current result:

```text
pytest: 21 passed
```

Deployment smoke test covers the live API -> Kafka -> worker -> PostgreSQL path:

```bash
python scripts/smoke_test.py --base-url https://vm-service-a4gdd.ondigitalocean.app
```

## 9. Deployment And IaC

Actual deployment command:

```bash
export DIGITALOCEAN_TOKEN=<token>
scripts/deploy_digitalocean.sh
```

Deployment flow:

1. Terraform creates VPC, data Droplet, firewall, and generated PostgreSQL credentials.
2. Droplet cloud-init installs Docker and starts PostgreSQL/Kafka.
3. Kafka topics are created on the data Droplet.
4. The script renders `.do/app.generated.yaml` from Terraform outputs.
5. `doctl apps create --spec --upsert --update-sources --wait` creates or updates the App Platform app.
6. App Platform deploys the API and worker.

Important deployment files:

- `infra/terraform/main.tf`
- `infra/terraform/cloud-init-data.yaml.tftpl`
- `.do/app.yaml.tmpl`
- `scripts/deploy_digitalocean.sh`
- `infra/production-reference/managed-data.tf.example`

## 10. Production Trade-Offs

The current deployment intentionally uses self-managed PostgreSQL and Kafka on one Droplet for speed. That is acceptable for a time-boxed interview demo, but it is not HA.

Known limitations:

- Single data node.
- No managed backups.
- Single-node Kafka.
- Kafka uses `PLAINTEXT` inside the private VPC.
- Droplet operations are our responsibility.

Production evolution:

- DigitalOcean Managed PostgreSQL.
- DigitalOcean Managed Kafka.
- Retry topics and DLQ replay tooling.
- Schema migrations instead of automatic schema creation.
- Metrics, tracing, and alerting.
- Authentication and authorization.
- Rate limiting.
- Retention cleanup jobs.
- CI/CD with remote Terraform state.

## 11. Suggested Walkthrough Order

1. Start with the problem and scale.
2. Explain why async ingestion is used.
3. Draw the deployed architecture.
4. Walk through `POST /metric-samples`.
5. Walk through worker processing.
6. Explain idempotency and duplicate handling.
7. Show query endpoints and health endpoints.
8. Show tests and smoke test.
9. Show IaC and deployment automation.
10. Close with production trade-offs and evolution.

Suggested closing:

> The deployed service passes health, readiness, and live smoke tests. Samples are accepted by the API, published to Kafka, processed by the worker, persisted in PostgreSQL, and alerts trigger and resolve correctly.
