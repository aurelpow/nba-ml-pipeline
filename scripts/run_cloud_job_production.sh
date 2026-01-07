#!/bin/bash

###############################################################################
# ▶️  Execute Cloud Run Job - Production Environment
# Purpose: Trigger the production job and monitor execution
#
# Usage:
#   ./run_cloud_job_production.sh <target>
#
# Examples:
#   ./run_cloud_job_production.sh fantasy_points
#   ./run_cloud_job_production.sh points
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "⚠️  gcp_config.sh not found, relying on environment variables."
fi

JOB_NAME="nba-training-prod"

echo "=================================================="
echo "▶️  EXECUTING CLOUD RUN JOB - PRODUCTION"
echo "=================================================="
echo ""
echo "   • Job: ${JOB_NAME}"
echo ""
echo "⚠️  WARNING: This will execute a PRODUCTION job!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Execution cancelled"
    exit 0
fi

echo ""
# 🚀 Execute the job
echo "🚀 Starting job execution..."
gcloud run jobs execute ${JOB_NAME} \
  --region=${REGION} \
  --project=${PROJECT_ID}

echo "✅ Job execution started!"
echo ""
echo "📊 View logs (if job fails):"
echo "   gcloud beta run jobs executions logs \$(gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION} --limit=1 --format='value(name)') --region=${REGION}"

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
gcloud run jobs executions logs "${EXECUTION_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --limit=50

echo ""
echo "=================================================="
echo "🔍 Full logs available at:"
echo "   https://console.cloud.google.com/run/jobs/details/${REGION}/${JOB_NAME}?project=${PROJECT_ID}"
echo ""
