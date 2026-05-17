#!/bin/bash

###############################################################################
# Execute Cloud Run Job - Post Evaluation (Develop)
# Purpose: Run `post_evaluation` for a specific date against BigQuery.
#
# Usage:
#   ./scripts/run_post_evaluation_job_develop.sh <YYYY-MM-DD>
#
# Example:
#   ./scripts/run_post_evaluation_job_develop.sh 2026-05-09
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "gcp_config.sh not found, relying on environment variables."
fi

# --- Date argument ----------------------------------------------------------
EVAL_DATE="${1:-}"
if [ -z "${EVAL_DATE}" ]; then
    echo "ERROR: date argument required."
    echo "Usage: $0 <YYYY-MM-DD>"
    exit 1
fi

# Basic format validation (YYYY-MM-DD)
if ! [[ "${EVAL_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "ERROR: invalid date format '${EVAL_DATE}'. Expected YYYY-MM-DD."
    exit 1
fi

JOB_NAME="nba-post-evaluation-develop"

echo "=================================================="
echo "EXECUTING POST EVALUATION JOB - DEVELOP"
echo "=================================================="
echo ""
echo "   * Job: ${JOB_NAME}"
echo "   * Region: ${REGION}"
echo "   * Date: ${EVAL_DATE}"
echo ""

# --args override at execute time injects the date for this run only;
# the job's stored args (default date) are not modified.
gcloud run jobs execute "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --args="main.py,-p,post_evaluation,-sm,bq,-d,${EVAL_DATE}" \
    --wait

echo ""
echo "=================================================="
echo "JOB EXECUTION COMPLETE"
echo "=================================================="
echo ""

EXECUTION_NAME=$(gcloud run jobs executions list \
    --job="${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --limit=1 \
    --format='value(name)')

echo "Execution: ${EXECUTION_NAME}"
echo ""
echo "Last 50 log lines:"
echo "--------------------------------------------------"
gcloud logging read \
    "resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME} AND resource.labels.location=${REGION}" \
    --project="${PROJECT_ID}" \
    --limit=50 \
    --format="value(textPayload)" \
    --order=desc
echo "--------------------------------------------------"
echo ""
echo "Verify in BigQuery:"
echo "   bq query --use_legacy_sql=false \\"
echo "     \"SELECT evaluation_date, tier, n_players, mae, alert_triggered \\"
echo "      FROM \\\`${PROJECT_ID}.nba_dataset.nba_model_evaluation\\\` \\"
echo "      WHERE evaluation_date = '${EVAL_DATE}' ORDER BY tier\""
echo ""
echo "Console: https://console.cloud.google.com/run/jobs/details/${REGION}/${JOB_NAME}?project=${PROJECT_ID}"
echo ""
