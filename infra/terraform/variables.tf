variable "name_prefix" {
  description = "Prefix used for managed infrastructure resource names."
  type        = string
  default     = "vm-service"
}

variable "app_name" {
  description = "DigitalOcean App Platform application name."
  type        = string
  default     = "vm-service"
}

variable "github_repo" {
  description = "GitHub repository connected to App Platform, in owner/repo format."
  type        = string
  default     = "amandayuelin/vm-service"
}

variable "github_branch" {
  description = "GitHub branch App Platform should deploy from."
  type        = string
  default     = "main"
}

variable "app_region" {
  description = "App Platform region slug."
  type        = string
  default     = "nyc"
}

variable "database_region" {
  description = "DigitalOcean database region slug."
  type        = string
  default     = "nyc1"
}

variable "project_id" {
  description = "Optional DigitalOcean project ID for created resources."
  type        = string
  default     = null
}

variable "vpc_id" {
  description = "Optional VPC UUID to attach App Platform and database clusters."
  type        = string
  default     = null
}

variable "enable_app" {
  description = "Create the App Platform API and worker. For greenfield deploys, set false for phase 1 until the Kafka CA certificate is available."
  type        = bool
  default     = false
}

variable "postgres_version" {
  description = "Managed PostgreSQL major version."
  type        = string
  default     = "18"
}

variable "postgres_size" {
  description = "Managed PostgreSQL cluster size slug."
  type        = string
  default     = "db-s-1vcpu-1gb"
}

variable "postgres_node_count" {
  description = "Managed PostgreSQL node count."
  type        = number
  default     = 1
}

variable "kafka_version" {
  description = "Managed Kafka version."
  type        = string
  default     = "3.5"
}

variable "kafka_size" {
  description = "Managed Kafka cluster size slug."
  type        = string
  default     = "db-s-2vcpu-2gb"
}

variable "kafka_node_count" {
  description = "Managed Kafka node count. DigitalOcean requires 3 for Kafka clusters."
  type        = number
  default     = 3

  validation {
    condition     = var.kafka_node_count == 3
    error_message = "DigitalOcean Managed Kafka clusters require kafka_node_count to be 3."
  }
}

variable "kafka_topic" {
  description = "Kafka topic used for VM metric sample ingestion."
  type        = string
  default     = "vm.metric-samples.v1"
}

variable "kafka_dlq_topic" {
  description = "Kafka dead-letter topic name reserved for production failure handling."
  type        = string
  default     = "vm.metric-samples.dlq.v1"
}

variable "kafka_partition_count" {
  description = "Partition count for the ingestion Kafka topic."
  type        = number
  default     = 12

  validation {
    condition     = var.kafka_partition_count >= 3
    error_message = "Kafka topic partition count must be at least 3."
  }
}

variable "kafka_replication_factor" {
  description = "Replication factor for Kafka topics."
  type        = number
  default     = 2

  validation {
    condition     = var.kafka_replication_factor >= 2 && var.kafka_replication_factor <= var.kafka_node_count
    error_message = "Kafka topic replication factor must be at least 2 and no greater than kafka_node_count."
  }
}

variable "kafka_sasl_mechanism" {
  description = "SASL mechanism for DigitalOcean Managed Kafka."
  type        = string
  default     = "SCRAM-SHA-256"
}

variable "kafka_ssl_ca_pem" {
  description = "DigitalOcean Managed Kafka CA certificate contents."
  type        = string
  default     = ""
  sensitive   = true
}

variable "kafka_consumer_group" {
  description = "Kafka consumer group used by App Platform worker components."
  type        = string
  default     = "vm-metrics-processors"
}

variable "api_instance_count" {
  description = "Number of App Platform API service instances."
  type        = number
  default     = 1
}

variable "worker_instance_count" {
  description = "Number of App Platform worker instances."
  type        = number
  default     = 1
}

variable "app_instance_size_slug" {
  description = "App Platform API instance size slug."
  type        = string
  default     = "apps-s-1vcpu-1gb"
}

variable "worker_instance_size_slug" {
  description = "App Platform worker instance size slug."
  type        = string
  default     = "apps-s-1vcpu-1gb"
}

variable "max_ingest_batch_size" {
  description = "Maximum samples accepted in one ingestion request."
  type        = number
  default     = 1000
}

variable "max_page_size" {
  description = "Maximum rows returned by paginated query endpoints."
  type        = number
  default     = 1000
}

variable "enable_database_firewalls" {
  description = "Restrict database and Kafka access to the App Platform app."
  type        = bool
  default     = true
}
