#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_digitalocean.sh [options]

Deploy the interview stack to DigitalOcean:
  1. Terraform creates VPC + self-managed PostgreSQL/Kafka Droplet.
  2. App Spec deploys the FastAPI API and worker to App Platform.

Options:
  --auto-approve       Run terraform apply without an interactive approval prompt.
  --skip-infra         Skip terraform plan/apply and only deploy the App Spec.
  --skip-app           Skip App Spec deployment and only apply Terraform.
  --wait-seconds N     Wait N seconds after infrastructure apply before deploying app. Default: 120.
  -h, --help           Show this help.

Required environment:
  DIGITALOCEAN_TOKEN   DigitalOcean API token with read/write permissions.

Examples:
  export DIGITALOCEAN_TOKEN=...
  scripts/deploy_digitalocean.sh
  scripts/deploy_digitalocean.sh --auto-approve
  scripts/deploy_digitalocean.sh --skip-infra
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

auto_approve=false
skip_infra=false
skip_app=false
wait_seconds="${BOOTSTRAP_WAIT_SECONDS:-120}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --auto-approve)
      auto_approve=true
      ;;
    --skip-infra)
      skip_infra=true
      ;;
    --skip-app)
      skip_app=true
      ;;
    --wait-seconds)
      shift
      if [ "$#" -eq 0 ]; then
        echo "--wait-seconds requires a value" >&2
        exit 1
      fi
      wait_seconds="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [ "$skip_infra" = true ] && [ "$skip_app" = true ]; then
  echo "Nothing to do: --skip-infra and --skip-app were both set." >&2
  exit 1
fi

if [ -z "${DIGITALOCEAN_TOKEN:-}" ]; then
  echo "DIGITALOCEAN_TOKEN is required." >&2
  exit 1
fi

require_cmd terraform
require_cmd doctl
require_cmd awk

python_bin="${PYTHON_BIN:-python3}"
require_cmd "$python_bin"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
tf_dir="$repo_root/infra/terraform"
app_spec="$repo_root/.do/app.generated.yaml"

if [ ! -f "$tf_dir/terraform.tfvars" ]; then
  cp "$tf_dir/terraform.tfvars.example" "$tf_dir/terraform.tfvars"
  echo "Created $tf_dir/terraform.tfvars from terraform.tfvars.example"
fi

if [ "$skip_infra" = false ]; then
  echo "==> Initializing Terraform"
  terraform -chdir="$tf_dir" init

  echo "==> Planning infrastructure"
  terraform -chdir="$tf_dir" plan -out=tfplan

  echo "==> Applying infrastructure"
  if [ "$auto_approve" = true ]; then
    terraform -chdir="$tf_dir" apply -auto-approve tfplan
  else
    terraform -chdir="$tf_dir" apply tfplan
  fi
fi

tfout() {
  terraform -chdir="$tf_dir" output -raw "$1"
}

if [ "$skip_app" = true ]; then
  echo "==> Skipping App Platform deployment"
  exit 0
fi

if [ "$skip_infra" = false ] && [ "$wait_seconds" -gt 0 ]; then
  echo "==> Waiting ${wait_seconds}s for Droplet cloud-init to bootstrap PostgreSQL/Kafka"
  sleep "$wait_seconds"
fi

echo "==> Rendering App Spec"
export APP_NAME="$(tfout app_name)"
export APP_REGION="$(tfout app_region)"
export VPC_ID="$(tfout vpc_id)"
export GITHUB_REPO="$(tfout github_repo)"
export GITHUB_BRANCH="$(tfout github_branch)"
export DATABASE_URL="$(tfout database_url)"
export KAFKA_BOOTSTRAP_SERVERS="$(tfout kafka_bootstrap_servers)"
export KAFKA_SECURITY_PROTOCOL="$(tfout kafka_security_protocol)"
export KAFKA_TOPIC="$(tfout kafka_topic)"
export KAFKA_DLQ_TOPIC="$(tfout kafka_dlq_topic)"
export KAFKA_CONSUMER_GROUP="$(tfout kafka_consumer_group)"
export API_INSTANCE_COUNT="$(tfout api_instance_count)"
export WORKER_INSTANCE_COUNT="$(tfout worker_instance_count)"
export APP_INSTANCE_SIZE_SLUG="$(tfout app_instance_size_slug)"
export WORKER_INSTANCE_SIZE_SLUG="$(tfout worker_instance_size_slug)"
export MAX_INGEST_BATCH_SIZE="$(tfout max_ingest_batch_size)"
export MAX_PAGE_SIZE="$(tfout max_page_size)"

"$python_bin" "$repo_root/scripts/render_app_spec.py" "$repo_root/.do/app.yaml.tmpl" "$app_spec"

echo "==> Validating App Spec schema"
doctl apps spec validate "$app_spec" --schema-only > /dev/null

echo "==> Upserting App Platform app"
app_id="$(doctl apps create --spec "$app_spec" --upsert --update-sources --format ID --no-header | awk 'NR == 1 {print $1}')"
if [ -z "$app_id" ]; then
  echo "App upsert did not return an app ID." >&2
  exit 1
fi

echo "==> Creating App Platform deployment"
doctl apps create-deployment "$app_id" --update-sources --wait

default_ingress="$(doctl apps get "$app_id" --format DefaultIngress --no-header | awk 'NR == 1 {print $1}')"
echo "==> Deployment complete"
echo "App ID: $app_id"
if [ -n "$default_ingress" ]; then
  echo "URL: https://$default_ingress"
fi
