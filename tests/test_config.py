from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def test_resolved_kafka_ssl_ca_location_prefers_explicit_path():
    settings = Settings(
        auto_create_schema=False,
        kafka_ssl_ca_location="/certs/ca.crt",
        kafka_ssl_ca_pem="-----BEGIN CERTIFICATE-----\\nignored\\n-----END CERTIFICATE-----",
    )

    assert settings.resolved_kafka_ssl_ca_location() == "/certs/ca.crt"


def test_resolved_kafka_ssl_ca_location_writes_pem_file():
    pem = "-----BEGIN CERTIFICATE-----\\nexample\\n-----END CERTIFICATE-----"
    settings = Settings(auto_create_schema=False, kafka_ssl_ca_pem=pem)

    location = settings.resolved_kafka_ssl_ca_location()

    assert location == "/tmp/kafka-ca-certificate.crt"
    assert Path(location).read_text(encoding="utf-8") == pem.replace("\\n", "\n")

