# Terraform Infrastructure

This directory defines the DigitalOcean production stack for the VM metrics service:

- App Platform web service for FastAPI.
- App Platform worker for Kafka consumption.
- Managed PostgreSQL.
- Managed Kafka.
- Kafka ingestion and DLQ topics.
- Trusted-source database firewalls scoped to the App Platform app.

## Important Safety Note

Terraform creates paid resources. Use this directory as the source of truth for a fresh greenfield environment after manually-created resources have been destroyed.

Terraform state will contain generated database credentials and App Platform secret values. Use a remote backend with restricted access before using CI/CD apply.

## Local Greenfield Deployment

Managed Kafka needs a CA certificate, but the CA certificate is only available after Kafka exists. Greenfield deployment therefore uses two applies.

### Phase 1: Data Services

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# keep enable_app=false
export DIGITALOCEAN_TOKEN=<your-token>
terraform init
terraform fmt
terraform plan
terraform apply
```

This creates:

- Managed PostgreSQL.
- Managed Kafka.
- Kafka ingestion topic.
- Kafka DLQ topic.

### Phase 2: App Platform API and Worker

Download the Managed Kafka CA certificate from DigitalOcean, then update `terraform.tfvars`:

```hcl
enable_app = true

kafka_ssl_ca_pem = <<EOT
-----BEGIN CERTIFICATE-----
paste-the-real-kafka-ca-certificate
-----END CERTIFICATE-----
EOT
```

Apply again:

```bash
terraform plan
terraform apply
```

This creates:

- App Platform API service.
- App Platform worker.
- App-level environment variables.
- Trusted-source database firewall rules.

After phase 2, if the app deployment starts before trusted-source firewall rules are fully active, trigger one App Platform redeploy.

## Import Existing Resources

Use this only if you keep any resources that were created in the DigitalOcean UI.

```bash
export DIGITALOCEAN_TOKEN=<your-token>
doctl apps list
doctl databases list
```

Then import matching resources:

```bash
cd infra/terraform
terraform init
terraform import 'digitalocean_app.vm_service[0]' <app-id>
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
