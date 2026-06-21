from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.models import MetricSampleMessage
from app.repositories.in_memory import InMemoryMetricRepository
from app.main import create_app


class FakePublisher:
    def __init__(self) -> None:
        self.available = True
        self.published: list[MetricSampleMessage] = []
        self.fail_publish = False

    def health_check(self) -> bool:
        return self.available

    def publish_samples(self, samples: Sequence[MetricSampleMessage]) -> None:
        if self.fail_publish:
            raise RuntimeError("publish failed")
        self.published.extend(samples)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        auto_create_schema=False,
        max_ingest_batch_size=3,
        max_page_size=1000,
        max_raw_query_hours=24,
        cpu_alert_threshold_percent=90,
        memory_alert_threshold_percent=90,
    )


@pytest.fixture
def repository() -> InMemoryMetricRepository:
    return InMemoryMetricRepository()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def client(settings: Settings, repository: InMemoryMetricRepository, publisher: FakePublisher) -> TestClient:
    app = create_app(settings=settings, repository=repository, publisher=publisher)
    with TestClient(app) as test_client:
        yield test_client
