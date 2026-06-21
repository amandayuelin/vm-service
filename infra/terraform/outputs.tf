output "app_id" {
  description = "DigitalOcean App Platform app ID."
  value       = try(digitalocean_app.vm_service[0].id, null)
}

output "app_live_url" {
  description = "Live URL for the App Platform app."
  value       = try(digitalocean_app.vm_service[0].live_url, null)
}

output "postgres_cluster_id" {
  description = "Managed PostgreSQL cluster ID."
  value       = digitalocean_database_cluster.postgres.id
}

output "postgres_host" {
  description = "Managed PostgreSQL public host."
  value       = digitalocean_database_cluster.postgres.host
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
