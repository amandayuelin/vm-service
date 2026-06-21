locals {
  database_url            = replace(digitalocean_database_cluster.postgres.uri, "postgresql://", "postgresql+psycopg://")
  kafka_bootstrap_servers = "${digitalocean_database_cluster.kafka.host}:${digitalocean_database_cluster.kafka.port}"
  tags                    = ["vm-service", "managed-by-terraform"]
}

resource "digitalocean_database_cluster" "postgres" {
  name                 = "${var.name_prefix}-postgres"
  engine               = "pg"
  version              = var.postgres_version
  size                 = var.postgres_size
  region               = var.database_region
  node_count           = var.postgres_node_count
  private_network_uuid = var.vpc_id
  project_id           = var.project_id
  tags                 = local.tags
}

resource "digitalocean_database_cluster" "kafka" {
  name                 = "${var.name_prefix}-kafka"
  engine               = "kafka"
  version              = var.kafka_version
  size                 = var.kafka_size
  region               = var.database_region
  node_count           = var.kafka_node_count
  private_network_uuid = var.vpc_id
  project_id           = var.project_id
  tags                 = local.tags
}

resource "digitalocean_database_kafka_topic" "metric_samples" {
  cluster_id         = digitalocean_database_cluster.kafka.id
  name               = var.kafka_topic
  partition_count    = var.kafka_partition_count
  replication_factor = var.kafka_replication_factor
}

resource "digitalocean_database_kafka_topic" "metric_samples_dlq" {
  cluster_id         = digitalocean_database_cluster.kafka.id
  name               = var.kafka_dlq_topic
  partition_count    = 3
  replication_factor = var.kafka_replication_factor
}
