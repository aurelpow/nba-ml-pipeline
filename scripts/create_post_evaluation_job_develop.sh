#!/bin/bash

###############################################################################
# Create Cloud Run Job - Post Evaluation (Develop)
# Purpose: Dedicated job that runs ONLY `post_evaluation` for a given date.
#          Bypasses run_all.sh by overriding the container ENTRYPOINT.
#
# Usage:
#   ./scripts/create_post_evaluation_job_develop.sh
#
# After creation, trigger runs with:
#   ./scripts/run_post_evaluation_job_develop.sh <YYYY-MM-DD>
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "gcp_config.sh not found, relying on environment variables."
fi

JOB_NAME="nba-post-evaluation-develop"

# Default date stored on the job (overridden at execute time).
# Falls back to yesterday in Europe/Madrid so a bare `gcloud run jobs execute` still works.
DEFAULT_DATE="$(TZ='Europe/Madrid' date -d 'yesterday' +%Y-%m-%d)"

# Lightweight resources — post-eval is read-only against BigQuery, finishes in seconds.
POST_EVAL_MEMORY="${POST_EVAL_MEMORY:-1Gi}"
POST_EVAL_CPU="${POST_EVAL_CPU:-1}"
POST_EVAL_TIMEOUT="${POST_EVAL_TIMEOUT:-900s}"
POST_EVAL_MAX_RETRIES="${POST_EVAL_MAX_RETRIES:-1}"

# Only DISCORD_WEBHOOK_URL is needed — no NBA API proxy required for post-eval.
DISCORD_WEBHOOK_URL_SECRET="${DISCORD_WEBHOOK_URL_SECRET:-discord-webhook-url}"

echo "=================================================="
echo "CREATE CLOUD RUN JOB - POST EVALUATION (DEVELOP)"
echo "=================================================="
echo ""
echo "Job Configuration:"
echo "   * Name: ${JOB_NAME}"
echo "   * Image: ${DEV_IMAGE_URI}"
echo "   * Region: ${REGION}"
echo "   * Service Account: (default Compute Engine SA)"
echo "   * Memory: ${POST_EVAL_MEMORY}"
echo "   * CPU: ${POST_EVAL_CPU}"
echo "   * Timeout: ${POST_EVAL_TIMEOUT}"
echo "   * Default date: ${DEFAULT_DATE}"
echo ""

# --command + --args override the Dockerfile ENTRYPOINT (run_all.sh)
# so this job runs ONLY `python main.py -p post_evaluation ...`.
COMMAND="python"
ARGS="main.py,-p,post_evaluation,-sm,bq,-d,${DEFAULT_DATE}"

if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Job exists. Updating configuration..."
    gcloud run jobs update "${JOB_NAME}" \
      --image="${DEV_IMAGE_URI}" \
      --region="${REGION}" \
      --memory="${POST_EVAL_MEMORY}" \
      --cpu="${POST_EVAL_CPU}" \
      --task-timeout="${POST_EVAL_TIMEOUT}" \
      --max-retries="${POST_EVAL_MAX_RETRIES}" \
      --command="${COMMAND}" \
      --args="${ARGS}" \
      --set-env-vars="SAVE_MODE=bq" \
      --set-secrets="DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL_SECRET}:latest" \
      --quiet
else
    echo "Job not found. Creating new job..."
    gcloud run jobs create "${JOB_NAME}" \
      --image="${DEV_IMAGE_URI}" \
      --region="${REGION}" \
      --project="${PROJECT_ID}" \
      --memory="${POST_EVAL_MEMORY}" \
      --cpu="${POST_EVAL_CPU}" \
      --task-timeout="${POST_EVAL_TIMEOUT}" \
      --max-retries="${POST_EVAL_MAX_RETRIES}" \
      --command="${COMMAND}" \
      --args="${ARGS}" \
      --set-env-vars="SAVE_MODE=bq" \
      --set-secrets="DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL_SECRET}:latest" \
      --quiet
fi

echo ""
echo "=================================================="
echo "CLOUD RUN JOB READY"
echo "=================================================="
echo ""
echo "Trigger a run for a specific date:"
echo "   ./scripts/run_post_evaluation_job_develop.sh 2026-05-09"
echo ""
echo "Monitor executions:"
echo "   gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION}"
echo ""
