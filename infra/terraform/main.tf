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

resource "digitalocean_app" "vm_service" {
  spec {
    name       = var.app_name
    region     = var.app_region
    project_id = var.project_id

    dynamic "vpc" {
      for_each = var.vpc_id == null ? [] : [var.vpc_id]
      content {
        id = vpc.value
      }
    }

    alert {
      rule     = "DEPLOYMENT_FAILED"
      disabled = false
    }

    env {
      key   = "ENVIRONMENT"
      value = "production"
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "LOG_LEVEL"
      value = "INFO"
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "PORT"
      value = "8000"
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "AUTO_CREATE_SCHEMA"
      value = "true"
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "DATABASE_URL"
      value = local.database_url
      scope = "RUN_TIME"
      type  = "SECRET"
    }

    env {
      key   = "KAFKA_BOOTSTRAP_SERVERS"
      value = local.kafka_bootstrap_servers
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "KAFKA_SECURITY_PROTOCOL"
      value = "SASL_SSL"
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "KAFKA_SASL_MECHANISM"
      value = var.kafka_sasl_mechanism
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "KAFKA_USERNAME"
      value = digitalocean_database_cluster.kafka.user
      scope = "RUN_TIME"
      type  = "SECRET"
    }

    env {
      key   = "KAFKA_PASSWORD"
      value = digitalocean_database_cluster.kafka.password
      scope = "RUN_TIME"
      type  = "SECRET"
    }

    env {
      key   = "KAFKA_SSL_CA_PEM"
      value = var.kafka_ssl_ca_pem
      scope = "RUN_TIME"
      type  = "SECRET"
    }

    env {
      key   = "KAFKA_TOPIC"
      value = var.kafka_topic
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "KAFKA_DLQ_TOPIC"
      value = var.kafka_dlq_topic
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "KAFKA_CONSUMER_GROUP"
      value = var.kafka_consumer_group
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "MAX_INGEST_BATCH_SIZE"
      value = tostring(var.max_ingest_batch_size)
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    env {
      key   = "MAX_PAGE_SIZE"
      value = tostring(var.max_page_size)
      scope = "RUN_TIME"
      type  = "GENERAL"
    }

    service {
      name               = "api"
      instance_count     = var.api_instance_count
      instance_size_slug = var.app_instance_size_slug
      dockerfile_path    = "Dockerfile"
      http_port          = 8000

      github {
        repo           = var.github_repo
        branch         = var.github_branch
        deploy_on_push = true
      }

      health_check {
        http_path             = "/healthz"
        initial_delay_seconds = 30
        period_seconds        = 10
        timeout_seconds       = 5
        success_threshold     = 1
        failure_threshold     = 5
      }
    }

    worker {
      name               = "worker"
      instance_count     = var.worker_instance_count
      instance_size_slug = var.worker_instance_size_slug
      dockerfile_path    = "Dockerfile"
      run_command        = "python -m app.workers.metrics_worker"

      github {
        repo           = var.github_repo
        branch         = var.github_branch
        deploy_on_push = true
      }

      alert {
        rule     = "RESTART_COUNT"
        value    = 5
        operator = "GREATER_THAN"
        window   = "TEN_MINUTES"
      }
    }

    ingress {
      rule {
        component {
          name = "api"
        }

        match {
          path {
            prefix = "/"
          }
        }
      }
    }
  }

  depends_on = [
    digitalocean_database_kafka_topic.metric_samples,
    digitalocean_database_kafka_topic.metric_samples_dlq,
  ]
}

resource "digitalocean_database_firewall" "postgres" {
  count      = var.enable_database_firewalls ? 1 : 0
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type  = "app"
    value = digitalocean_app.vm_service.id
  }
}

resource "digitalocean_database_firewall" "kafka" {
  count      = var.enable_database_firewalls ? 1 : 0
  cluster_id = digitalocean_database_cluster.kafka.id

  rule {
    type  = "app"
    value = digitalocean_app.vm_service.id
  }
}
