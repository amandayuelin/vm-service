# DigitalOcean Infrastructure

This project uses a fast interview-friendly IaC model:

- Terraform creates the private network and self-managed data node.
- The data node runs PostgreSQL and Kafka with Docker Compose.
- DigitalOcean App Spec owns App Platform API/worker configuration.
- App Platform ingress provides the public HTTP entrypoint and load balancing.

## Resources

Terraform creates:

- DigitalOcean VPC.
- One Ubuntu data Droplet.
- Dockerized PostgreSQL on the data Droplet.
- Dockerized single-node Kafka on the data Droplet.
- Kafka ingestion topic `vm.metric-samples.v1`.
- Kafka DLQ topic `vm.metric-samples.dlq.v1`.
- DigitalOcean Cloud Firewall allowing PostgreSQL/Kafka only from the VPC.

App Spec creates:

- DigitalOcean App Platform app.
- App Platform API service.
- App Platform worker service.
- App Platform ingress route to the API service.

No standalone DigitalOcean Load Balancer is required. App Platform ingress provides public routing, TLS termination, and load balancing for the API service.

## Trade-off

This self-managed data node provisions much faster than DigitalOcean Managed Kafka and is good for a 3-hour interview/demo. It is not HA and should not be presented as the final production architecture. The production evolution is Managed PostgreSQL, Managed Kafka, backups, multi-node Kafka, stronger auth, metrics, and alerting.

## Safety

Terraform creates paid resources. If a previous managed-database apply partially succeeded, this new plan may show destroys for the old managed resources and creates for the new Droplet/VPC resources. Review the plan before typing `yes`.

Terraform state contains generated PostgreSQL credentials. Configure a remote backend with restricted access before using GitHub Actions apply.

## Local Greenfield Deployment

Prerequisites:

- Terraform.
- doctl authenticated with your DigitalOcean account.
- Python 3.
- App Platform GitHub integration installed for `amandayuelin/vm-service`.

Fast path from the repo root:

```bash
export DIGITALOCEAN_TOKEN=<your-token>
scripts/deploy_digitalocean.sh
```

For a non-interactive demo run:

```bash
export DIGITALOCEAN_TOKEN=<your-token>
scripts/deploy_digitalocean.sh --auto-approve
```

Useful split commands:

```bash
scripts/deploy_digitalocean.sh --skip-app      # create/update only VPC + data Droplet
scripts/deploy_digitalocean.sh --skip-infra    # deploy only App Platform from current Terraform outputs
```

Manual flow:

Create infrastructure:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
export DIGITALOCEAN_TOKEN=<your-token>
terraform init
terraform fmt
terraform plan
terraform apply
```

The Droplet cloud-init script installs Docker, starts PostgreSQL/Kafka, and creates Kafka topics. It can take several minutes after the Droplet resource is created for Docker and Kafka to finish bootstrapping.

Render and deploy the App Spec from repo root:

```bash
cd ../..

export APP_NAME="$(terraform -chdir=infra/terraform output -raw app_name)"
export APP_REGION="$(terraform -chdir=infra/terraform output -raw app_region)"
export VPC_ID="$(terraform -chdir=infra/terraform output -raw vpc_id)"
export GITHUB_REPO="$(terraform -chdir=infra/terraform output -raw github_repo)"
export GITHUB_BRANCH="$(terraform -chdir=infra/terraform output -raw github_branch)"
export DATABASE_URL="$(terraform -chdir=infra/terraform output -raw database_url)"
export KAFKA_BOOTSTRAP_SERVERS="$(terraform -chdir=infra/terraform output -raw kafka_bootstrap_servers)"
export KAFKA_SECURITY_PROTOCOL="$(terraform -chdir=infra/terraform output -raw kafka_security_protocol)"
export KAFKA_TOPIC="$(terraform -chdir=infra/terraform output -raw kafka_topic)"
export KAFKA_DLQ_TOPIC="$(terraform -chdir=infra/terraform output -raw kafka_dlq_topic)"
export KAFKA_CONSUMER_GROUP="$(terraform -chdir=infra/terraform output -raw kafka_consumer_group)"
export API_INSTANCE_COUNT="$(terraform -chdir=infra/terraform output -raw api_instance_count)"
export WORKER_INSTANCE_COUNT="$(terraform -chdir=infra/terraform output -raw worker_instance_count)"
export APP_INSTANCE_SIZE_SLUG="$(terraform -chdir=infra/terraform output -raw app_instance_size_slug)"
export WORKER_INSTANCE_SIZE_SLUG="$(terraform -chdir=infra/terraform output -raw worker_instance_size_slug)"
export MAX_INGEST_BATCH_SIZE="$(terraform -chdir=infra/terraform output -raw max_ingest_batch_size)"
export MAX_PAGE_SIZE="$(terraform -chdir=infra/terraform output -raw max_page_size)"

python scripts/render_app_spec.py .do/app.yaml.tmpl .do/app.generated.yaml
doctl apps spec validate .do/app.generated.yaml --schema-only > /dev/null
APP_ID="$(doctl apps create --spec .do/app.generated.yaml --upsert --update-sources --wait --format ID --no-header | awk 'NR == 1 {print $1}')"
```

## GitHub Actions

Required GitHub secret:

- `DIGITALOCEAN_TOKEN`

Before using `apply=true` or `deploy_app=true`, configure `infra/terraform/backend.tf` from `backend.tf.example`.

Manual workflow usage:

1. Run `Terraform` with `apply=true`, `deploy_app=false` to create the VPC and data Droplet.
2. Run `Terraform` with `apply=false`, `deploy_app=true` to deploy/update App Platform from App Spec.

For a single future update after resources exist, use `apply=false`, `deploy_app=true` when only App Spec or application deployment settings changed.

## Production Reference

The production managed-service version is documented separately in `../production-reference`. Keep the interview deployment fast with this self-managed Droplet path, and use the production reference to explain the Managed PostgreSQL/Managed Kafka evolution during review.
