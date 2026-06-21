from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    port: int = Field(default=8000, alias="PORT")
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/vm_metrics",
        alias="DATABASE_URL",
    )
    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_username: str | None = Field(default=None, alias="KAFKA_USERNAME")
    kafka_password: str | None = Field(default=None, alias="KAFKA_PASSWORD")
    kafka_security_protocol: str = Field(default="PLAINTEXT", alias="KAFKA_SECURITY_PROTOCOL")
    kafka_sasl_mechanism: str | None = Field(default=None, alias="KAFKA_SASL_MECHANISM")
    kafka_ssl_ca_location: str | None = Field(default=None, alias="KAFKA_SSL_CA_LOCATION")
    kafka_ssl_ca_pem: str | None = Field(default=None, alias="KAFKA_SSL_CA_PEM")
    kafka_topic: str = Field(default="vm.metric-samples.v1", alias="KAFKA_TOPIC")
    kafka_dlq_topic: str = Field(default="vm.metric-samples.dlq.v1", alias="KAFKA_DLQ_TOPIC")
    kafka_consumer_group: str = Field(default="vm-metrics-processors", alias="KAFKA_CONSUMER_GROUP")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    max_page_size: int = Field(default=1000, alias="MAX_PAGE_SIZE")
    max_ingest_batch_size: int = Field(default=1000, alias="MAX_INGEST_BATCH_SIZE")
    cpu_alert_threshold_percent: float = Field(default=90.0, alias="CPU_ALERT_THRESHOLD_PERCENT")
    memory_alert_threshold_percent: float = Field(default=90.0, alias="MEMORY_ALERT_THRESHOLD_PERCENT")
    raw_retention_days: int = Field(default=7, alias="RAW_RETENTION_DAYS")
    aggregate_retention_days: int = Field(default=90, alias="AGGREGATE_RETENTION_DAYS")
    max_raw_query_hours: int = Field(default=24, alias="MAX_RAW_QUERY_HOURS")
    max_future_skew_seconds: int = Field(default=300, alias="MAX_FUTURE_SKEW_SECONDS")
    auto_create_schema: bool = Field(default=True, alias="AUTO_CREATE_SCHEMA")

    def resolved_kafka_ssl_ca_location(self) -> str | None:
        if self.kafka_ssl_ca_location:
            return self.kafka_ssl_ca_location
        if not self.kafka_ssl_ca_pem:
            return None

        ca_path = Path("/tmp/kafka-ca-certificate.crt")
        ca_path.write_text(self.kafka_ssl_ca_pem.replace("\\n", "\n"), encoding="utf-8")
        ca_path.chmod(0o600)
        return str(ca_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
