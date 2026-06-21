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

The deployment uses a hybrid IaC model:

- Terraform in `infra/terraform` creates a VPC, one self-managed data Droplet, PostgreSQL, Kafka, and Kafka topics.
- DigitalOcean App Spec in `.do/app.yaml.tmpl` defines the App Platform API service, worker, env vars, health check, and ingress.
- GitHub Actions renders `.do/app.generated.yaml` from Terraform outputs and upserts the App Platform app with `doctl`.

Required DigitalOcean resources:

- VPC.
- Self-managed data Droplet running Dockerized PostgreSQL and Kafka.
- Kafka ingestion and DLQ topics.
- App Platform API service.
- App Platform worker component.
- Cloud Firewall allowing PostgreSQL/Kafka only from the VPC.

A standalone DigitalOcean Load Balancer is not required. App Platform ingress provides the public HTTP entrypoint, routing, TLS termination, and load balancing.

GitHub Actions workflows live in `.github/workflows`:

- `CI` runs tests and builds the Docker image on pushes and pull requests.
- `Terraform` validates Terraform, applies infrastructure, renders App Spec, and deploys the App Platform app through manual workflow dispatch.

For a greenfield DigitalOcean environment, see `infra/terraform/README.md`.

Fast deployment command:

```bash
export DIGITALOCEAN_TOKEN=<your-token>
scripts/deploy_digitalocean.sh
```

Production reference IaC for the managed PostgreSQL/Kafka version lives in `infra/production-reference`.

## Configuration

See `.env.example` for supported environment variables. Important values:

- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_SECURITY_PROTOCOL`
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
- Self-managed PostgreSQL and Kafka on one data Droplet for the interview deployment.
- App Platform ingress/load balancing.
- App Spec-managed `/healthz` health check.
- App Spec-managed runtime environment variables.

For the interview deployment, App Platform connects to PostgreSQL and Kafka through the VPC using private IPs:

```text
KAFKA_SECURITY_PROTOCOL=PLAINTEXT
KAFKA_BOOTSTRAP_SERVERS=<data-droplet-private-ip>:9092
DATABASE_URL=postgresql+psycopg://<user>:<password>@<data-droplet-private-ip>:5432/vm_metrics
```

Production evolution should move back to DigitalOcean Managed PostgreSQL and Managed Kafka with SASL/SSL, backups, metrics, and HA.

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
