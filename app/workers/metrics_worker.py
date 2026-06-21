from __future__ import annotations

import json
import logging
import signal
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.domain.models import MetricSampleMessage
from app.repositories.postgres import PostgresMetricRepository
from app.services.processing import ProcessingService

logger = logging.getLogger(__name__)


@dataclass
class WorkerRuntime:
    running: bool = True


def consumer_config(settings: Settings) -> dict[str, str | bool]:
    config: dict[str, str | bool] = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": settings.kafka_consumer_group,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
    if settings.kafka_security_protocol:
        config["security.protocol"] = settings.kafka_security_protocol
    if settings.kafka_sasl_mechanism:
        config["sasl.mechanism"] = settings.kafka_sasl_mechanism
    if settings.kafka_username:
        config["sasl.username"] = settings.kafka_username
    if settings.kafka_password:
        config["sasl.password"] = settings.kafka_password
    return config


def process_kafka_payload(payload: bytes, service: ProcessingService):
    decoded = json.loads(payload.decode("utf-8"))
    message = MetricSampleMessage.from_kafka_payload(decoded)
    return service.process_message(message)


def run_worker(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    try:
        from confluent_kafka import Consumer, KafkaError, KafkaException
    except ImportError as exc:
        raise RuntimeError("confluent-kafka is required to run the worker") from exc

    repository = PostgresMetricRepository(settings)
    if settings.auto_create_schema:
        repository.initialize()
    service = ProcessingService(repository, settings)
    consumer = Consumer(consumer_config(settings))
    runtime = WorkerRuntime()

    def stop(_signum, _frame) -> None:
        runtime.running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    consumer.subscribe([settings.kafka_topic])
    logger.info("worker_started", extra={"topic": settings.kafka_topic, "group": settings.kafka_consumer_group})
    try:
        while runtime.running:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    logger.warning("topic_not_available_yet", extra={"topic": settings.kafka_topic})
                    continue
                raise KafkaException(message.error())
            try:
                result = process_kafka_payload(message.value(), service)
                consumer.commit(message=message)
                logger.info(
                    "sample_processed",
                    extra={
                        "sample_id": result.sample_id,
                        "inserted": result.inserted,
                        "duplicate": result.duplicate,
                        "alert_transition": result.alert_transition,
                    },
                )
            except Exception:
                logger.exception("sample_processing_failed")
                # Do not commit the offset; Kafka will redeliver. Production should add retry topics and DLQ.
    finally:
        consumer.close()
        logger.info("worker_stopped")


if __name__ == "__main__":
    run_worker()
