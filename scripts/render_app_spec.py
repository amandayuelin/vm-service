from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


JSON_QUOTED_KEYS = {
    "APP_NAME",
    "APP_REGION",
    "VPC_ID",
    "DATABASE_URL",
    "KAFKA_BOOTSTRAP_SERVERS",
    "KAFKA_SECURITY_PROTOCOL",
    "KAFKA_TOPIC",
    "KAFKA_DLQ_TOPIC",
    "KAFKA_CONSUMER_GROUP",
    "GITHUB_REPO",
    "GITHUB_BRANCH",
    "APP_INSTANCE_SIZE_SLUG",
    "WORKER_INSTANCE_SIZE_SLUG",
    "MAX_INGEST_BATCH_SIZE",
    "MAX_PAGE_SIZE",
}

RAW_KEYS = {
    "API_INSTANCE_COUNT",
    "WORKER_INSTANCE_COUNT",
}


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def replacement(name: str) -> str:
    if name in JSON_QUOTED_KEYS:
        return json.dumps(required_env(name))
    if name in RAW_KEYS:
        return required_env(name)
    raise SystemExit(f"unsupported template variable: {name}")


def render(template_path: Path, output_path: Path) -> None:
    template = template_path.read_text(encoding="utf-8")

    rendered = re.sub(r"\$\{([A-Z0-9_]+)\}", lambda match: replacement(match.group(1)), template)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_app_spec.py <template> <output>")
    render(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
