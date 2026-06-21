from __future__ import annotations

import json
from typing import Protocol, Sequence

from app.core.config import Settings
from app.core.errors import ApiError
from app.domain.models import MetricSampleMessage


class MetricPublisher(Protocol):
    def health_check(self) -> bool:
        ...

    def publish_samples(self, samples: Sequence[MetricSampleMessage]) -> None:
        ...


class KafkaMetricPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer = None

    def _producer_config(self) -> dict[str, str]:
        config = {
            "bootstrap.servers": self._settings.kafka_bootstrap_servers,
            "client.id": "vm-metrics-api",
        }
        if self._settings.kafka_security_protocol:
            config["security.protocol"] = self._settings.kafka_security_protocol
        if self._settings.kafka_sasl_mechanism:
            config["sasl.mechanism"] = self._settings.kafka_sasl_mechanism
        if self._settings.kafka_username:
            config["sasl.username"] = self._settings.kafka_username
        if self._settings.kafka_password:
            config["sasl.password"] = self._settings.kafka_password
        return config

    def _get_producer(self):
        if self._producer is None:
            try:
                from confluent_kafka import Producer
            except ImportError as exc:
                raise ApiError(503, "dependency_unavailable", "Kafka client is not installed.") from exc
            self._producer = Producer(self._producer_config())
        return self._producer

    def health_check(self) -> bool:
        try:
            producer = self._get_producer()
            producer.list_topics(timeout=2)
            return True
        except Exception:
            return False

    def publish_samples(self, samples: Sequence[MetricSampleMessage]) -> None:
        producer = self._get_producer()
        delivery_errors: list[str] = []

        def on_delivery(error, message) -> None:
            if error is not None:
                delivery_errors.append(str(error))

        for sample in samples:
            producer.produce(
                topic=self._settings.kafka_topic,
                key=sample.vm_id.encode("utf-8"),
                value=json.dumps(sample.to_kafka_payload(), separators=(",", ":")).encode("utf-8"),
                on_delivery=on_delivery,
            )
            producer.poll(0)

        producer.flush(timeout=5)
        if delivery_errors:
            raise ApiError(
                503,
                "dependency_unavailable",
                "Failed to publish metric samples to Kafka.",
                {"publish_errors": delivery_errors[:3]},
            )
