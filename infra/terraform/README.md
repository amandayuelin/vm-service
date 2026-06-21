# DigitalOcean Infrastructure

This project uses a hybrid IaC model:

- Terraform owns durable data infrastructure.
- DigitalOcean App Spec owns App Platform configuration.
- GitHub Actions orchestrates both.

## Resources

Required resources:

- DigitalOcean Managed PostgreSQL.
- DigitalOcean Managed Kafka.
- Kafka topic `vm.metric-samples.v1`.
- Kafka DLQ topic `vm.metric-samples.dlq.v1`.
- DigitalOcean App Platform app created from `.do/app.yaml.tmpl`.
- App Platform API service.
- App Platform worker service.
- Database trusted-source rules allowing the App Platform app to reach PostgreSQL and Kafka.

No standalone DigitalOcean Load Balancer is required. App Platform ingress provides the public HTTP entrypoint, routing, TLS termination, and load balancing for the API service.

## Ownership

Terraform files in this directory create:

- Managed PostgreSQL.
- Managed Kafka.
- Kafka ingestion topic.
- Kafka DLQ topic.

The GitHub Actions workflow then:

1. Reads Terraform outputs.
2. Fetches the Kafka CA certificate with `doctl databases get-ca`.
3. Renders `.do/app.generated.yaml` from `.do/app.yaml.tmpl`.
4. Upserts the App Platform app with `doctl apps create --spec --upsert`.
5. Replaces PostgreSQL and Kafka trusted-source rules with `app:<app_id>`.
6. Triggers a deployment after trusted-source rules are active.

## Safety

Terraform creates paid resources. Use this only after manually-created resources have been destroyed or intentionally imported.

Terraform state contains generated database credentials. Configure a remote backend with restricted access before using GitHub Actions apply.

## Local Greenfield Deployment

Prerequisites:

- Terraform.
- doctl authenticated with your DigitalOcean account.
- jq.
- Python 3.
- App Platform GitHub integration installed for `amandayuelin/vm-service`.

Create data services:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
export DIGITALOCEAN_TOKEN=<your-token>
terraform init
terraform fmt
terraform plan
terraform apply
```

Render and deploy the App Spec from repo root:

```bash
cd ../..

export APP_NAME="$(terraform -chdir=infra/terraform output -raw app_name)"
export APP_REGION="$(terraform -chdir=infra/terraform output -raw app_region)"
export GITHUB_REPO="$(terraform -chdir=infra/terraform output -raw github_repo)"
export GITHUB_BRANCH="$(terraform -chdir=infra/terraform output -raw github_branch)"
export DATABASE_URL="$(terraform -chdir=infra/terraform output -raw database_url)"
export KAFKA_BOOTSTRAP_SERVERS="$(terraform -chdir=infra/terraform output -raw kafka_bootstrap_servers)"
export KAFKA_SASL_MECHANISM="$(terraform -chdir=infra/terraform output -raw kafka_sasl_mechanism)"
export KAFKA_USERNAME="$(terraform -chdir=infra/terraform output -raw kafka_username)"
export KAFKA_PASSWORD="$(terraform -chdir=infra/terraform output -raw kafka_password)"
export KAFKA_TOPIC="$(terraform -chdir=infra/terraform output -raw kafka_topic)"
export KAFKA_DLQ_TOPIC="$(terraform -chdir=infra/terraform output -raw kafka_dlq_topic)"
export KAFKA_CONSUMER_GROUP="$(terraform -chdir=infra/terraform output -raw kafka_consumer_group)"
export API_INSTANCE_COUNT="$(terraform -chdir=infra/terraform output -raw api_instance_count)"
export WORKER_INSTANCE_COUNT="$(terraform -chdir=infra/terraform output -raw worker_instance_count)"
export APP_INSTANCE_SIZE_SLUG="$(terraform -chdir=infra/terraform output -raw app_instance_size_slug)"
export WORKER_INSTANCE_SIZE_SLUG="$(terraform -chdir=infra/terraform output -raw worker_instance_size_slug)"
export MAX_INGEST_BATCH_SIZE="$(terraform -chdir=infra/terraform output -raw max_ingest_batch_size)"
export MAX_PAGE_SIZE="$(terraform -chdir=infra/terraform output -raw max_page_size)"
export KAFKA_SSL_CA_PEM="$(doctl databases get-ca "$(terraform -chdir=infra/terraform output -raw kafka_cluster_id)" -o json | jq -r .certificate | base64 --decode)"

python scripts/render_app_spec.py .do/app.yaml.tmpl .do/app.generated.yaml
doctl apps spec validate .do/app.generated.yaml --schema-only
APP_ID="$(doctl apps create --spec .do/app.generated.yaml --upsert --update-sources --format ID --no-header | awk 'NR == 1 {print $1}')"
doctl databases firewalls replace "$(terraform -chdir=infra/terraform output -raw postgres_cluster_id)" --rule "app:$APP_ID"
doctl databases firewalls replace "$(terraform -chdir=infra/terraform output -raw kafka_cluster_id)" --rule "app:$APP_ID"
doctl apps create-deployment "$APP_ID" --update-sources --wait
```

## GitHub Actions

Required GitHub secret:

- `DIGITALOCEAN_TOKEN`

Before using `apply=true` or `deploy_app=true`, configure `infra/terraform/backend.tf` from `backend.tf.example`.

Manual workflow usage:

1. Run `Terraform` with `apply=true`, `deploy_app=false` to create data services.
2. Run `Terraform` with `apply=false`, `deploy_app=true` to deploy/update App Platform from App Spec.

For a single future update after resources exist, use `apply=false`, `deploy_app=true` when only App Spec or application deployment settings changed.

## Import Existing Resources

Use import only if you keep resources created outside this workflow.

```bash
export DIGITALOCEAN_TOKEN=<your-token>
doctl databases list
```

Then import matching data resources:

```bash
cd infra/terraform
terraform init
terraform import digitalocean_database_cluster.postgres <postgres-cluster-id>
terraform import digitalocean_database_cluster.kafka <kafka-cluster-id>
terraform import digitalocean_database_kafka_topic.metric_samples <kafka-cluster-id>,vm.metric-samples.v1
terraform import digitalocean_database_kafka_topic.metric_samples_dlq <kafka-cluster-id>,vm.metric-samples.dlq.v1
terraform plan
```
