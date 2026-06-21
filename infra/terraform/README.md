# Terraform Infrastructure

This directory defines the DigitalOcean production stack for the VM metrics service:

- App Platform web service for FastAPI.
- App Platform worker for Kafka consumption.
- Managed PostgreSQL.
- Managed Kafka.
- Kafka ingestion and DLQ topics.
- Trusted-source database firewalls scoped to the App Platform app.

## Important Safety Note

Terraform can create paid resources. You already created some resources manually, so do not run `terraform apply` blindly unless you either:

1. Want a fresh greenfield environment, or
2. Have imported the existing DigitalOcean resources into Terraform state.

Terraform state will contain generated database credentials and App Platform secret values. Use a remote backend with restricted access before using CI/CD apply.

## Local Greenfield Deployment

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars and paste the real Kafka CA cert
export DIGITALOCEAN_TOKEN=<your-token>
terraform init
terraform fmt
terraform plan
terraform apply
```

After the first apply, if the app deployment starts before trusted-source firewall rules are fully active, trigger one App Platform redeploy.

## Import Existing Resources

Use this path for the resources you already created in the DigitalOcean UI.

```bash
export DIGITALOCEAN_TOKEN=<your-token>
doctl apps list
doctl databases list
```

Then import matching resources:

```bash
cd infra/terraform
terraform init
terraform import digitalocean_app.vm_service <app-id>
terraform import digitalocean_database_cluster.postgres <postgres-cluster-id>
terraform import digitalocean_database_cluster.kafka <kafka-cluster-id>
terraform import digitalocean_database_kafka_topic.metric_samples <kafka-cluster-id>,vm.metric-samples.v1
terraform import digitalocean_database_kafka_topic.metric_samples_dlq <kafka-cluster-id>,vm.metric-samples.dlq.v1
terraform import 'digitalocean_database_firewall.postgres[0]' <postgres-cluster-id>
terraform import 'digitalocean_database_firewall.kafka[0]' <kafka-cluster-id>
```

After imports:

```bash
terraform plan
```

Review the plan carefully. If Terraform wants to replace resources you intend to keep, stop and adjust variables to match the existing setup.

## GitHub Actions

The Terraform workflow validates configuration on pull requests and supports manual plan/apply through `workflow_dispatch`.

Required GitHub secrets:

- `DIGITALOCEAN_TOKEN`
- `KAFKA_SSL_CA_PEM`

CI apply is intentionally blocked unless a real `backend.tf` exists in this directory. Add a remote backend before enabling apply from GitHub Actions.
