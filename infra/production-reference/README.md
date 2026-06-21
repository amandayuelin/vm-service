# Production IaC Reference

This directory is a reference-only production evolution for architecture review.

The interview deployment uses `infra/terraform` because a self-managed data Droplet provisions quickly. In a real production deployment, replace that Droplet with:

- DigitalOcean Managed PostgreSQL.
- DigitalOcean Managed Kafka.
- Kafka topics managed by Terraform.
- Trusted-source rules scoped to the App Platform app.
- App Platform API and worker configured for `SASL_SSL`.

Use `managed-data.tf.example` as the starting point for the production data layer. It is intentionally not part of the current deployment workflow.
