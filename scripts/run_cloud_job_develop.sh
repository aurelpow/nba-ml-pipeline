#!/bin/bash

###############################################################################
# ▶️  Execute Cloud Run Job - Develop Environment
# Purpose: Trigger the develop job and monitor execution
#
# Usage:
#   ./run_cloud_job_develop.sh
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "⚠️  gcp_config.sh not found, relying on environment variables."
fi

JOB_NAME="nba-training-develop"

echo "=================================================="
echo "▶️  EXECUTING CLOUD RUN JOB - DEVELOP"
echo "=================================================="
echo ""
echo "   • Job: ${JOB_NAME}"
echo "   • Region: ${REGION}"
echo ""

# 🚀 Execute the job
echo "🚀 Starting job execution..."
gcloud run jobs execute "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --wait

echo ""
echo "=================================================="
echo "✅ JOB EXECUTION COMPLETE!"
echo "=================================================="
echo ""

# 📊 Get execution details
echo "📊 Fetching execution details..."
EXECUTION_NAME=$(gcloud run jobs executions list \
    --job="${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --limit=1 \
    --format='value(name)')

echo "   • Execution: ${EXECUTION_NAME}"
echo ""

# 📋 Show logs
echo "📋 Showing logs (last 50 lines)..."
echo "=================================================="

# We use 'logging read' because it is stable and supports limits perfectly
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME} AND resource.labels.location=${REGION}" \
    --project="${PROJECT_ID}" \
    --limit=50 \
    --format="value(textPayload)"
echo ""
echo "=================================================="

echo ""
echo "=================================================="
echo "🔍 Full logs available at:"
echo "   https://console.cloud.google.com/run/jobs/details/${REGION}/${JOB_NAME}?project=${PROJECT_ID}"
echo ""
echo "🔍 Monitor execution:"
echo "   gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION}"
echo ""
echo "📊 View logs (if job fails):"
echo "   gcloud beta run jobs executions logs \$(gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION} --limit=1 --format='value(name)') --region=${REGION}"
echo ""
