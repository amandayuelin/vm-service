from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def app_spec_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_NAME": "vm-service",
            "APP_REGION": "nyc",
            "GITHUB_REPO": "amandayuelin/vm-service",
            "GITHUB_BRANCH": "main",
            "DATABASE_URL": "postgresql+psycopg://user:pass@example.com:25060/defaultdb?sslmode=require",
            "KAFKA_BOOTSTRAP_SERVERS": "kafka.example.com:25061",
            "KAFKA_SASL_MECHANISM": "SCRAM-SHA-256",
            "KAFKA_USERNAME": "doadmin",
            "KAFKA_PASSWORD": "secret",
            "KAFKA_TOPIC": "vm.metric-samples.v1",
            "KAFKA_DLQ_TOPIC": "vm.metric-samples.dlq.v1",
            "KAFKA_CONSUMER_GROUP": "vm-metrics-processors",
            "API_INSTANCE_COUNT": "1",
            "WORKER_INSTANCE_COUNT": "1",
            "APP_INSTANCE_SIZE_SLUG": "apps-s-1vcpu-1gb",
            "WORKER_INSTANCE_SIZE_SLUG": "apps-s-1vcpu-1gb",
            "MAX_INGEST_BATCH_SIZE": "1000",
            "MAX_PAGE_SIZE": "1000",
            "KAFKA_SSL_CA_PEM": "-----BEGIN CERTIFICATE-----\\ndummy\\n-----END CERTIFICATE-----",
        }
    )
    return env


def test_render_app_spec_quotes_env_values(tmp_path: Path) -> None:
    output = tmp_path / "app.yaml"

    subprocess.run(
        [sys.executable, "scripts/render_app_spec.py", ".do/app.yaml.tmpl", str(output)],
        check=True,
        env=app_spec_env(),
    )

    rendered = output.read_text(encoding="utf-8")
    assert 'value: "1000"' in rendered
    assert "instance_count: 1" in rendered
    assert "-----BEGIN CERTIFICATE-----" in rendered


def test_render_app_spec_fails_for_missing_env(tmp_path: Path) -> None:
    output = tmp_path / "app.yaml"
    env = app_spec_env()
    del env["DATABASE_URL"]

    result = subprocess.run(
        [sys.executable, "scripts/render_app_spec.py", ".do/app.yaml.tmpl", str(output)],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr
