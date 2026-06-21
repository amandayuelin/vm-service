from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.domain.models import (
    AlertRecord,
    AlertStatus,
    BatchRecord,
    BatchStatus,
    MetricHealthRecord,
    MetricSampleMessage,
    MetricSampleRecord,
    MetricType,
    Page,
    ProcessSampleResult,
    decode_cursor,
    encode_cursor,
    floor_to_hour,
    utc_now,
)


METRIC_TYPE_VALUES = ", ".join(f"'{metric.value}'" for metric in MetricType)

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS ingestion_batches (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    request_id TEXT,
    status TEXT NOT NULL,
    submitted_count INTEGER NOT NULL CHECK (submitted_count >= 0),
    processed_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_count >= 0),
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingestion_batches_status ON ingestion_batches(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_batches_created_at ON ingestion_batches(created_at);

CREATE TABLE IF NOT EXISTS metric_samples (
    id BIGSERIAL PRIMARY KEY,
    sample_id TEXT NOT NULL UNIQUE,
    batch_id TEXT REFERENCES ingestion_batches(id) ON DELETE SET NULL,
    vm_id TEXT NOT NULL,
    metric_type TEXT NOT NULL CHECK (metric_type IN ({METRIC_TYPE_VALUES})),
    value DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metric_samples_vm_observed ON metric_samples(vm_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_metric_samples_vm_type_observed ON metric_samples(vm_id, metric_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_metric_samples_observed_at ON metric_samples(observed_at);

CREATE TABLE IF NOT EXISTS metric_hourly_aggregates (
    id BIGSERIAL PRIMARY KEY,
    vm_id TEXT NOT NULL,
    metric_type TEXT NOT NULL CHECK (metric_type IN ({METRIC_TYPE_VALUES})),
    hour_start TIMESTAMPTZ NOT NULL,
    sample_count INTEGER NOT NULL CHECK (sample_count >= 0),
    sum_value DOUBLE PRECISION NOT NULL,
    min_value DOUBLE PRECISION NOT NULL,
    max_value DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (vm_id, metric_type, hour_start)
);

CREATE INDEX IF NOT EXISTS idx_metric_hourly_vm_type_hour
    ON metric_hourly_aggregates(vm_id, metric_type, hour_start DESC);
CREATE INDEX IF NOT EXISTS idx_metric_hourly_hour_start ON metric_hourly_aggregates(hour_start);

CREATE TABLE IF NOT EXISTS vm_metric_health (
    vm_id TEXT NOT NULL,
    metric_type TEXT NOT NULL CHECK (metric_type IN ('cpu_usage_percent', 'memory_usage_percent')),
    latest_value DOUBLE PRECISION NOT NULL,
    latest_sample_id TEXT NOT NULL,
    latest_observed_at TIMESTAMPTZ NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    consecutive_breaches INTEGER NOT NULL CHECK (consecutive_breaches >= 0),
    alerting BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (vm_id, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_vm_metric_health_alerting ON vm_metric_health(alerting);
CREATE INDEX IF NOT EXISTS idx_vm_metric_health_latest_observed ON vm_metric_health(latest_observed_at);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    vm_id TEXT NOT NULL,
    metric_type TEXT NOT NULL CHECK (metric_type IN ('cpu_usage_percent', 'memory_usage_percent')),
    threshold DOUBLE PRECISION NOT NULL,
    latest_value DOUBLE PRECISION NOT NULL,
    consecutive_breaches INTEGER NOT NULL CHECK (consecutive_breaches >= 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RESOLVED')),
    started_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_one_active_per_vm_metric
    ON alerts(vm_id, metric_type) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_alerts_status_updated ON alerts(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_vm_status ON alerts(vm_id, status);
"""


class PostgresMetricRepository:
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._settings = settings
        self._engine = engine or create_engine(settings.database_url, pool_pre_ping=True, future=True)

    def initialize(self) -> None:
        with self._engine.begin() as conn:
            for statement in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
                conn.execute(text(statement))

    def health_check(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def create_or_get_batch(
        self,
        *,
        idempotency_key: str | None,
        request_id: str,
        submitted_count: int,
    ) -> tuple[BatchRecord, bool]:
        now = utc_now()
        batch_id = f"batch-{uuid4()}"
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO ingestion_batches (
                            id, idempotency_key, request_id, status, submitted_count,
                            processed_count, duplicate_count, failed_count, created_at, updated_at
                        )
                        VALUES (
                            :id, :idempotency_key, :request_id, :status, :submitted_count,
                            0, 0, 0, :created_at, :updated_at
                        )
                        RETURNING *
                        """
                    ),
                    {
                        "id": batch_id,
                        "idempotency_key": idempotency_key,
                        "request_id": request_id,
                        "status": BatchStatus.ACCEPTED.value,
                        "submitted_count": submitted_count,
                        "created_at": now,
                        "updated_at": now,
                    },
                ).mappings().one()
                return _batch_from_row(row), False
        except IntegrityError:
            if not idempotency_key:
                raise
            existing = self._get_batch_by_idempotency_key(idempotency_key)
            if existing is None:
                raise
            return existing, True

    def _get_batch_by_idempotency_key(self, idempotency_key: str) -> BatchRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ingestion_batches WHERE idempotency_key = :idempotency_key"),
                {"idempotency_key": idempotency_key},
            ).mappings().first()
            return _batch_from_row(row) if row else None

    def mark_batch_processing(self, batch_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ingestion_batches
                    SET status = :status, updated_at = :updated_at
                    WHERE id = :id AND status = :accepted
                    """
                ),
                {
                    "id": batch_id,
                    "status": BatchStatus.PROCESSING.value,
                    "accepted": BatchStatus.ACCEPTED.value,
                    "updated_at": utc_now(),
                },
            )

    def mark_batch_failed(self, batch_id: str, error: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE ingestion_batches
                    SET status = :status, failed_count = submitted_count, last_error = :last_error, updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": batch_id,
                    "status": BatchStatus.FAILED.value,
                    "last_error": error[:1000],
                    "updated_at": utc_now(),
                },
            )

    def get_batch(self, batch_id: str) -> BatchRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ingestion_batches WHERE id = :id"),
                {"id": batch_id},
            ).mappings().first()
            return _batch_from_row(row) if row else None

    def process_sample(
        self,
        message: MetricSampleMessage,
        *,
        cpu_threshold: float,
        memory_threshold: float,
    ) -> ProcessSampleResult:
        now = utc_now()
        with self._engine.begin() as conn:
            inserted = self._insert_sample(conn, message, now)
            if not inserted:
                self._increment_batch_counters(conn, message.batch_id, duplicate_delta=1)
                return ProcessSampleResult(sample_id=message.sample_id, inserted=False, duplicate=True)

            self._upsert_hourly_aggregate(conn, message, now)
            transition = self._update_health_and_alerts(
                conn,
                message,
                now,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
            )
            self._increment_batch_counters(conn, message.batch_id, processed_delta=1)
            return ProcessSampleResult(
                sample_id=message.sample_id,
                inserted=True,
                duplicate=False,
                alert_transition=transition,
            )

    def _insert_sample(self, conn: Connection, message: MetricSampleMessage, now: datetime) -> bool:
        row = conn.execute(
            text(
                """
                INSERT INTO metric_samples (
                    sample_id, batch_id, vm_id, metric_type, value, observed_at,
                    received_at, processed_at, created_at
                )
                VALUES (
                    :sample_id, :batch_id, :vm_id, :metric_type, :value, :observed_at,
                    :received_at, :processed_at, :created_at
                )
                ON CONFLICT (sample_id) DO NOTHING
                RETURNING sample_id
                """
            ),
            {
                "sample_id": message.sample_id,
                "batch_id": message.batch_id,
                "vm_id": message.vm_id,
                "metric_type": message.metric_type.value,
                "value": message.value,
                "observed_at": message.observed_at,
                "received_at": message.received_at,
                "processed_at": now,
                "created_at": now,
            },
        ).first()
        return row is not None

    def _upsert_hourly_aggregate(self, conn: Connection, message: MetricSampleMessage, now: datetime) -> None:
        conn.execute(
            text(
                """
                INSERT INTO metric_hourly_aggregates (
                    vm_id, metric_type, hour_start, sample_count, sum_value, min_value, max_value, updated_at
                )
                VALUES (:vm_id, :metric_type, :hour_start, 1, :value, :value, :value, :updated_at)
                ON CONFLICT (vm_id, metric_type, hour_start)
                DO UPDATE SET
                    sample_count = metric_hourly_aggregates.sample_count + 1,
                    sum_value = metric_hourly_aggregates.sum_value + EXCLUDED.sum_value,
                    min_value = LEAST(metric_hourly_aggregates.min_value, EXCLUDED.min_value),
                    max_value = GREATEST(metric_hourly_aggregates.max_value, EXCLUDED.max_value),
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "vm_id": message.vm_id,
                "metric_type": message.metric_type.value,
                "hour_start": floor_to_hour(message.observed_at),
                "value": message.value,
                "updated_at": now,
            },
        )

    def _update_health_and_alerts(
        self,
        conn: Connection,
        message: MetricSampleMessage,
        now: datetime,
        *,
        cpu_threshold: float,
        memory_threshold: float,
    ) -> str | None:
        if message.metric_type == MetricType.CPU_USAGE_PERCENT:
            threshold = cpu_threshold
        elif message.metric_type == MetricType.MEMORY_USAGE_PERCENT:
            threshold = memory_threshold
        else:
            return None

        current = conn.execute(
            text(
                """
                SELECT *
                FROM vm_metric_health
                WHERE vm_id = :vm_id AND metric_type = :metric_type
                FOR UPDATE
                """
            ),
            {"vm_id": message.vm_id, "metric_type": message.metric_type.value},
        ).mappings().first()

        if current and current["latest_observed_at"] > message.observed_at:
            return None

        breached = message.value > threshold
        previous_breaches = int(current["consecutive_breaches"]) if current else 0
        consecutive_breaches = previous_breaches + 1 if breached else 0
        alerting = consecutive_breaches >= 3

        conn.execute(
            text(
                """
                INSERT INTO vm_metric_health (
                    vm_id, metric_type, latest_value, latest_sample_id, latest_observed_at,
                    threshold, consecutive_breaches, alerting, updated_at
                )
                VALUES (
                    :vm_id, :metric_type, :latest_value, :latest_sample_id, :latest_observed_at,
                    :threshold, :consecutive_breaches, :alerting, :updated_at
                )
                ON CONFLICT (vm_id, metric_type)
                DO UPDATE SET
                    latest_value = EXCLUDED.latest_value,
                    latest_sample_id = EXCLUDED.latest_sample_id,
                    latest_observed_at = EXCLUDED.latest_observed_at,
                    threshold = EXCLUDED.threshold,
                    consecutive_breaches = EXCLUDED.consecutive_breaches,
                    alerting = EXCLUDED.alerting,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "vm_id": message.vm_id,
                "metric_type": message.metric_type.value,
                "latest_value": message.value,
                "latest_sample_id": message.sample_id,
                "latest_observed_at": message.observed_at,
                "threshold": threshold,
                "consecutive_breaches": consecutive_breaches,
                "alerting": alerting,
                "updated_at": now,
            },
        )

        was_alerting = bool(current["alerting"]) if current else False
        if alerting:
            conn.execute(
                text(
                    """
                    INSERT INTO alerts (
                        id, vm_id, metric_type, threshold, latest_value,
                        consecutive_breaches, status, started_at, resolved_at, updated_at
                    )
                    VALUES (
                        :id, :vm_id, :metric_type, :threshold, :latest_value,
                        :consecutive_breaches, :status, :started_at, NULL, :updated_at
                    )
                    ON CONFLICT (vm_id, metric_type) WHERE status = 'ACTIVE'
                    DO UPDATE SET
                        threshold = EXCLUDED.threshold,
                        latest_value = EXCLUDED.latest_value,
                        consecutive_breaches = EXCLUDED.consecutive_breaches,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": f"alert-{uuid4()}",
                    "vm_id": message.vm_id,
                    "metric_type": message.metric_type.value,
                    "threshold": threshold,
                    "latest_value": message.value,
                    "consecutive_breaches": consecutive_breaches,
                    "status": AlertStatus.ACTIVE.value,
                    "started_at": now,
                    "updated_at": now,
                },
            )
            return "created" if not was_alerting else "updated"

        conn.execute(
            text(
                """
                UPDATE alerts
                SET status = :resolved, resolved_at = :resolved_at, updated_at = :updated_at
                WHERE vm_id = :vm_id AND metric_type = :metric_type AND status = :active
                """
            ),
            {
                "vm_id": message.vm_id,
                "metric_type": message.metric_type.value,
                "active": AlertStatus.ACTIVE.value,
                "resolved": AlertStatus.RESOLVED.value,
                "resolved_at": now,
                "updated_at": now,
            },
        )
        return "resolved" if was_alerting else None

    def _increment_batch_counters(
        self,
        conn: Connection,
        batch_id: str,
        *,
        processed_delta: int = 0,
        duplicate_delta: int = 0,
        failed_delta: int = 0,
        last_error: str | None = None,
    ) -> None:
        row = conn.execute(
            text(
                """
                UPDATE ingestion_batches
                SET
                    processed_count = processed_count + :processed_delta,
                    duplicate_count = duplicate_count + :duplicate_delta,
                    failed_count = failed_count + :failed_delta,
                    last_error = COALESCE(:last_error, last_error),
                    updated_at = :updated_at
                WHERE id = :id
                RETURNING submitted_count, processed_count, duplicate_count, failed_count
                """
            ),
            {
                "id": batch_id,
                "processed_delta": processed_delta,
                "duplicate_delta": duplicate_delta,
                "failed_delta": failed_delta,
                "last_error": last_error,
                "updated_at": utc_now(),
            },
        ).mappings().first()
        if not row:
            return

        total_done = row["processed_count"] + row["duplicate_count"] + row["failed_count"]
        if total_done < row["submitted_count"]:
            status = BatchStatus.PROCESSING
        elif row["failed_count"] == row["submitted_count"]:
            status = BatchStatus.FAILED
        elif row["failed_count"] > 0:
            status = BatchStatus.PARTIAL_FAILED
        else:
            status = BatchStatus.PROCESSED

        conn.execute(
            text("UPDATE ingestion_batches SET status = :status, updated_at = :updated_at WHERE id = :id"),
            {"id": batch_id, "status": status.value, "updated_at": utc_now()},
        )

    def list_metric_samples(
        self,
        *,
        vm_id: str,
        start: datetime,
        end: datetime,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        cursor_observed_at: datetime | None = None
        cursor_id: int | None = None
        if cursor:
            cursor_observed_at, cursor_id = decode_cursor(cursor)

        filters = [
            "vm_id = :vm_id",
            "observed_at >= :start",
            "observed_at <= :end",
        ]
        params = {
            "vm_id": vm_id,
            "start": start,
            "end": end,
            "limit": limit + 1,
            "metric_type": metric_type.value if metric_type else None,
            "cursor_observed_at": cursor_observed_at,
            "cursor_id": cursor_id,
        }
        if metric_type:
            filters.append("metric_type = :metric_type")
        if cursor_observed_at is not None:
            filters.append("(observed_at, id) < (:cursor_observed_at, :cursor_id)")

        sql = f"""
            SELECT *
            FROM metric_samples
            WHERE {" AND ".join(filters)}
            ORDER BY observed_at DESC, id DESC
            LIMIT :limit
        """
        with self._engine.connect() as conn:
            rows = list(conn.execute(text(sql), params).mappings())

        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last["observed_at"], last["id"])
            rows = rows[:limit]

        return Page(items=[_sample_from_row(row) for row in rows], next_cursor=next_cursor)

    def get_vm_health(self, vm_id: str) -> list[MetricHealthRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM vm_metric_health
                    WHERE vm_id = :vm_id
                    ORDER BY metric_type
                    """
                ),
                {"vm_id": vm_id},
            ).mappings()
            return [_health_from_row(row) for row in rows]

    def list_active_alerts(
        self,
        *,
        vm_id: str | None,
        metric_type: MetricType | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        cursor_updated_at: datetime | None = None
        cursor_id: str | None = None
        if cursor:
            cursor_updated_at, decoded_id = decode_cursor(cursor)
            cursor_id = str(decoded_id) if decoded_id is not None else None

        filters = ["status = :status"]
        params = {
            "status": AlertStatus.ACTIVE.value,
            "vm_id": vm_id,
            "metric_type": metric_type.value if metric_type else None,
            "limit": limit + 1,
            "cursor_updated_at": cursor_updated_at,
            "cursor_id": cursor_id,
        }
        if vm_id:
            filters.append("vm_id = :vm_id")
        if metric_type:
            filters.append("metric_type = :metric_type")
        if cursor_updated_at is not None:
            filters.append("(updated_at, id) < (:cursor_updated_at, :cursor_id)")

        sql = f"""
            SELECT *
            FROM alerts
            WHERE {" AND ".join(filters)}
            ORDER BY updated_at DESC, id DESC
            LIMIT :limit
        """
        with self._engine.connect() as conn:
            rows = list(conn.execute(text(sql), params).mappings())

        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last["updated_at"], last["id"])
            rows = rows[:limit]
        return Page(items=[_alert_from_row(row) for row in rows], next_cursor=next_cursor)


def _batch_from_row(row: RowMapping) -> BatchRecord:
    return BatchRecord(
        id=row["id"],
        idempotency_key=row["idempotency_key"],
        request_id=row["request_id"],
        status=BatchStatus(row["status"]),
        submitted_count=row["submitted_count"],
        processed_count=row["processed_count"],
        duplicate_count=row["duplicate_count"],
        failed_count=row["failed_count"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _sample_from_row(row: RowMapping) -> MetricSampleRecord:
    return MetricSampleRecord(
        id=row["id"],
        sample_id=row["sample_id"],
        batch_id=row["batch_id"],
        vm_id=row["vm_id"],
        metric_type=MetricType(row["metric_type"]),
        value=row["value"],
        observed_at=row["observed_at"],
        received_at=row["received_at"],
        processed_at=row["processed_at"],
    )


def _health_from_row(row: RowMapping) -> MetricHealthRecord:
    return MetricHealthRecord(
        vm_id=row["vm_id"],
        metric_type=MetricType(row["metric_type"]),
        latest_value=row["latest_value"],
        latest_sample_id=row["latest_sample_id"],
        latest_observed_at=row["latest_observed_at"],
        threshold=row["threshold"],
        consecutive_breaches=row["consecutive_breaches"],
        alerting=row["alerting"],
        updated_at=row["updated_at"],
    )


def _alert_from_row(row: RowMapping) -> AlertRecord:
    return AlertRecord(
        id=row["id"],
        vm_id=row["vm_id"],
        metric_type=MetricType(row["metric_type"]),
        threshold=row["threshold"],
        latest_value=row["latest_value"],
        consecutive_breaches=row["consecutive_breaches"],
        status=AlertStatus(row["status"]),
        started_at=row["started_at"],
        resolved_at=row["resolved_at"],
        updated_at=row["updated_at"],
    )
