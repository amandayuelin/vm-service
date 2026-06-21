locals {
  postgres_db             = var.postgres_db
  postgres_user           = var.postgres_user
  kafka_security_protocol = "PLAINTEXT"
  kafka_bootstrap_servers = "${digitalocean_droplet.data.ipv4_address_private}:9092"
  database_url            = "postgresql+psycopg://${local.postgres_user}:${random_password.postgres.result}@${digitalocean_droplet.data.ipv4_address_private}:5432/${local.postgres_db}"
  tags                    = ["vm-service", "managed-by-terraform"]
}

resource "digitalocean_vpc" "main" {
  name     = "${var.name_prefix}-vpc"
  region   = var.region
  ip_range = var.vpc_ip_range
}

resource "random_password" "postgres" {
  length  = 24
  special = false
}

resource "random_id" "kafka_cluster" {
  byte_length = 16
}

resource "digitalocean_droplet" "data" {
  name       = "${var.name_prefix}-data"
  image      = var.data_droplet_image
  size       = var.data_droplet_size
  region     = var.region
  vpc_uuid   = digitalocean_vpc.main.id
  monitoring = true
  ssh_keys   = var.ssh_key_fingerprints
  tags       = local.tags

  user_data = templatefile("${path.module}/cloud-init-data.yaml.tftpl", {
    postgres_db             = local.postgres_db
    postgres_user           = local.postgres_user
    postgres_password       = random_password.postgres.result
    kafka_cluster_id        = random_id.kafka_cluster.b64_url
    kafka_topic             = var.kafka_topic
    kafka_dlq_topic         = var.kafka_dlq_topic
    kafka_partition_count   = var.kafka_partition_count
    max_kafka_heap_mb       = var.max_kafka_heap_mb
    postgres_container_port = 5432
    kafka_container_port    = 9092
  })
}

resource "digitalocean_firewall" "data" {
  name        = "${var.name_prefix}-data-firewall"
  droplet_ids = [digitalocean_droplet.data.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "5432"
    source_addresses = [digitalocean_vpc.main.ip_range]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "9092"
    source_addresses = [digitalocean_vpc.main.ip_range]
  }

  dynamic "inbound_rule" {
    for_each = length(var.ssh_allowed_cidrs) == 0 ? [] : [1]
    content {
      protocol         = "tcp"
      port_range       = "22"
      source_addresses = var.ssh_allowed_cidrs
    }
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
