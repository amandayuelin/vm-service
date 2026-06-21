from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import register_routes
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.middleware import RequestIdMiddleware
from app.messaging.publisher import KafkaMetricPublisher, MetricPublisher
from app.repositories.base import MetricRepository
from app.repositories.postgres import PostgresMetricRepository
from app.services.ingestion import IngestionService
from app.services.queries import QueryService


def create_app(
    *,
    settings: Settings | None = None,
    repository: MetricRepository | None = None,
    publisher: MetricPublisher | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    repository = repository or PostgresMetricRepository(settings)
    publisher = publisher or KafkaMetricPublisher(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.auto_create_schema:
            repository.initialize()
        yield

    app = FastAPI(
        title="VM Metrics Ingestion and Alerting Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    app.state.settings = settings
    app.state.repository = repository
    app.state.publisher = publisher
    app.state.ingestion_service = IngestionService(repository, publisher, settings)
    app.state.query_service = QueryService(repository, settings)

    register_routes(app, repository, publisher)
    return app


app = create_app()
