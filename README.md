# VM Metrics Ingestion and Alerting Service

FastAPI service for high-volume VM metric ingestion, asynchronous Kafka-backed processing, PostgreSQL persistence, recent metric queries, VM health, and active alert queries.

## Architecture

MVP runtime:

Client -> DigitalOcean App Platform ingress/load balancing -> FastAPI web service -> Managed Kafka -> App Platform worker -> Managed PostgreSQL

The API accepts metric batches quickly and publishes Kafka messages. Workers persist raw samples, update hourly aggregates, and maintain latest health and active alerts. PostgreSQL is the durable source of truth for query APIs.

## Application Structure

```text
app/
  main.py                 # app factory and dependency wiring
  api/                    # route registration and Pydantic schemas
  core/                   # config, error handling, request middleware
  domain/                 # domain enums, records, and helpers
  messaging/              # Kafka publisher integration
  repositories/           # repository contract plus PostgreSQL/test implementations
  services/               # ingestion, processing, and query use cases
  workers/                # Kafka consumer entrypoints
```

## Endpoints

- `GET /healthz`
- `GET /readyz`
- `POST /metric-samples`
- `GET /ingestion-batches/{batch_id}`
- `GET /vms/{vm_id}/metrics`
- `GET /vms/{vm_id}/health`
- `GET /alerts/active`

Example ingest:

```bash
curl -X POST http://localhost:8000/metric-samples \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-batch-1' \
  -d '{
    "samples": [
      {
        "sample_id": "sample-1",
        "vm_id": "vm-1",
        "metric_type": "cpu_usage_percent",
        "value": 91.5,
        "observed_at": "2026-06-21T21:00:00Z"
      }
    ]
  }'
```

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest
```

Run dependencies and services with Docker Compose:

```bash
docker compose up --build
```

Run only PostgreSQL and Kafka, then run API locally:

```bash
docker compose up -d db kafka
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.workers.metrics_worker
```

## Tests

```bash
pytest
```

The default test suite uses fakes for PostgreSQL and Kafka boundaries so tests are deterministic and do not require a live broker. The production repository targets PostgreSQL and the production publisher/worker target Kafka.

## Docker

```bash
docker build -t vm-metrics-service .
docker run --env-file .env.example -p 8000:8000 vm-metrics-service
```

For a full local stack:

```bash
docker compose up --build
```

## Infrastructure as Code and CI/CD

Terraform configuration lives in `infra/terraform` and can create:

- DigitalOcean App Platform API service.
- DigitalOcean App Platform worker component.
- DigitalOcean Managed PostgreSQL.
- DigitalOcean Managed Kafka.
- Kafka ingestion and DLQ topics.
- Trusted-source database firewall rules for the app.

GitHub Actions workflows live in `.github/workflows`:

- `CI` runs tests and builds the Docker image on pushes and pull requests.
- `Terraform` validates Terraform on infrastructure changes and supports manual plan/apply through workflow dispatch.

For a greenfield DigitalOcean environment, use the two-phase Terraform flow in `infra/terraform/README.md`: first create PostgreSQL/Kafka/topics, then create App Platform API/worker after the Kafka CA certificate is available.

## Configuration

See `.env.example` for supported environment variables. Important values:

- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_SECURITY_PROTOCOL`
- `KAFKA_SASL_MECHANISM`
- `KAFKA_USERNAME`
- `KAFKA_PASSWORD`
- `KAFKA_SSL_CA_LOCATION`
- `KAFKA_SSL_CA_PEM`
- `KAFKA_TOPIC`
- `KAFKA_CONSUMER_GROUP`
- `MAX_INGEST_BATCH_SIZE`
- `MAX_PAGE_SIZE`
- `CPU_ALERT_THRESHOLD_PERCENT`
- `MEMORY_ALERT_THRESHOLD_PERCENT`

## DigitalOcean Deployment Notes

Deployment target is DigitalOcean App Platform with:

- Dockerized FastAPI web service.
- Dockerized worker component running `python -m app.workers.metrics_worker`.
- DigitalOcean Managed PostgreSQL.
- DigitalOcean Managed Kafka.
- App Platform ingress/load balancing.
- `/healthz` as the health check path.
- Environment variables configured in App Platform.

For DigitalOcean Managed Kafka, use SASL/SSL connection details from the Kafka cluster Overview page:

```text
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
KAFKA_USERNAME=<managed-kafka-user>
KAFKA_PASSWORD=<managed-kafka-password>
KAFKA_SSL_CA_LOCATION=/app/certs/ca-certificate.crt
```

If App Platform cannot mount the CA file directly, set the downloaded CA certificate contents as encrypted `KAFKA_SSL_CA_PEM` instead. The app writes it to `/tmp/kafka-ca-certificate.crt` at startup and passes that path to the Kafka client.

Smoke tests after deployment:

```bash
python scripts/smoke_test.py --base-url http://localhost:8000
curl https://<app-url>/healthz
curl https://<app-url>/readyz
curl -X POST https://<app-url>/metric-samples \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: smoke-test-1' \
  -d '{"samples":[{"sample_id":"smoke-1","vm_id":"vm-smoke","metric_type":"cpu_usage_percent","value":91.2,"observed_at":"2026-06-21T21:00:00Z"}]}'
curl https://<app-url>/ingestion-batches/<batch_id>
curl https://<app-url>/vms/vm-smoke/health
```

## Trade-offs

- Kafka is included because the prompt requires asynchronous processing, retries, and 50k-100k samples/sec ingestion.
- API tests use fakes for speed; Docker Compose provides the local PostgreSQL/Kafka integration path.
- The MVP uses global CPU and memory thresholds.
- Schema creation is automatic for interview convenience; production should use explicit migrations.
- Worker retry is idempotent redelivery-based in the MVP. Production should add retry topics, backoff, DLQ replay tooling, and a transactional outbox if acceptance tracking and Kafka publish must be atomic.
