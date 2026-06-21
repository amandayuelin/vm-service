output "postgres_cluster_id" {
  description = "Managed PostgreSQL cluster ID."
  value       = digitalocean_database_cluster.postgres.id
}

output "postgres_host" {
  description = "Managed PostgreSQL public host."
  value       = digitalocean_database_cluster.postgres.host
}

output "database_url" {
  description = "SQLAlchemy PostgreSQL connection URL for the API and worker."
  value       = local.database_url
  sensitive   = true
}

output "kafka_cluster_id" {
  description = "Managed Kafka cluster ID."
  value       = digitalocean_database_cluster.kafka.id
}

output "kafka_bootstrap_servers" {
  description = "Managed Kafka bootstrap server host:port."
  value       = local.kafka_bootstrap_servers
}

output "kafka_topic" {
  description = "Kafka topic used for metric ingestion."
  value       = digitalocean_database_kafka_topic.metric_samples.name
}

output "kafka_dlq_topic" {
  description = "Kafka topic reserved for dead-letter messages."
  value       = digitalocean_database_kafka_topic.metric_samples_dlq.name
}

output "kafka_username" {
  description = "Managed Kafka default username."
  value       = digitalocean_database_cluster.kafka.user
  sensitive   = true
}

output "kafka_password" {
  description = "Managed Kafka default password."
  value       = digitalocean_database_cluster.kafka.password
  sensitive   = true
}

output "app_name" {
  description = "App Platform app name used by the App Spec deployment workflow."
  value       = var.app_name
}

output "app_region" {
  description = "App Platform region used by the App Spec deployment workflow."
  value       = var.app_region
}

output "github_repo" {
  description = "GitHub repository used by the App Spec deployment workflow."
  value       = var.github_repo
}

output "github_branch" {
  description = "GitHub branch used by the App Spec deployment workflow."
  value       = var.github_branch
}

output "kafka_sasl_mechanism" {
  description = "Kafka SASL mechanism used by the App Spec deployment workflow."
  value       = var.kafka_sasl_mechanism
}

output "kafka_consumer_group" {
  description = "Kafka consumer group used by App Platform workers."
  value       = var.kafka_consumer_group
}

output "api_instance_count" {
  description = "App Platform API instance count."
  value       = var.api_instance_count
}

output "worker_instance_count" {
  description = "App Platform worker instance count."
  value       = var.worker_instance_count
}

output "app_instance_size_slug" {
  description = "App Platform API instance size."
  value       = var.app_instance_size_slug
}

output "worker_instance_size_slug" {
  description = "App Platform worker instance size."
  value       = var.worker_instance_size_slug
}

output "max_ingest_batch_size" {
  description = "Maximum ingestion batch size."
  value       = var.max_ingest_batch_size
}

output "max_page_size" {
  description = "Maximum query page size."
  value       = var.max_page_size
}
