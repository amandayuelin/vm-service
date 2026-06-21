variable "name_prefix" {
  description = "Prefix used for infrastructure resource names."
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

variable "region" {
  description = "DigitalOcean region for the VPC and self-managed data Droplet."
  type        = string
  default     = "nyc1"
}

variable "vpc_ip_range" {
  description = "Private CIDR range for App Platform to data Droplet communication."
  type        = string
  default     = "10.20.0.0/16"
}

variable "data_droplet_image" {
  description = "Droplet image used for the self-managed data node."
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "data_droplet_size" {
  description = "Droplet size used for self-managed PostgreSQL and Kafka."
  type        = string
  default     = "s-2vcpu-2gb"
}

variable "ssh_key_fingerprints" {
  description = "Optional SSH key fingerprints/IDs for Droplet access."
  type        = list(string)
  default     = []
}

variable "ssh_allowed_cidrs" {
  description = "Optional CIDR blocks allowed to SSH to the data Droplet. Leave empty to block SSH."
  type        = list(string)
  default     = []
}

variable "postgres_db" {
  description = "PostgreSQL database name."
  type        = string
  default     = "vm_metrics"
}

variable "postgres_user" {
  description = "PostgreSQL application username."
  type        = string
  default     = "vm_metrics"
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
    condition     = var.kafka_partition_count >= 1
    error_message = "Kafka topic partition count must be at least 1."
  }
}

variable "max_kafka_heap_mb" {
  description = "Kafka JVM heap size in MB on the self-managed data Droplet."
  type        = number
  default     = 768
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
