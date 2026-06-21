output "vpc_id" {
  description = "VPC ID used by App Platform and the data Droplet."
  value       = digitalocean_vpc.main.id
}

output "data_droplet_id" {
  description = "Self-managed PostgreSQL/Kafka Droplet ID."
  value       = digitalocean_droplet.data.id
}

output "data_droplet_public_ip" {
  description = "Public IP of the self-managed data Droplet."
  value       = digitalocean_droplet.data.ipv4_address
}

output "data_droplet_private_ip" {
  description = "Private IP of the self-managed data Droplet."
  value       = digitalocean_droplet.data.ipv4_address_private
}

output "database_url" {
  description = "SQLAlchemy PostgreSQL connection URL for the API and worker."
  value       = local.database_url
  sensitive   = true
}

output "kafka_bootstrap_servers" {
  description = "Self-managed Kafka bootstrap server host:port."
  value       = local.kafka_bootstrap_servers
}

output "kafka_security_protocol" {
  description = "Kafka security protocol used by the App Spec deployment workflow."
  value       = local.kafka_security_protocol
}

output "kafka_topic" {
  description = "Kafka topic used for metric ingestion."
  value       = var.kafka_topic
}

output "kafka_dlq_topic" {
  description = "Kafka topic reserved for dead-letter messages."
  value       = var.kafka_dlq_topic
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
