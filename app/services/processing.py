from __future__ import annotations

from app.core.config import Settings
from app.domain.models import MetricSampleMessage
from app.repositories.base import MetricRepository


class ProcessingService:
    def __init__(self, repository: MetricRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def process_message(self, message: MetricSampleMessage):
        return self._repository.process_sample(
            message,
            cpu_threshold=self._settings.cpu_alert_threshold_percent,
            memory_threshold=self._settings.memory_alert_threshold_percent,
        )

