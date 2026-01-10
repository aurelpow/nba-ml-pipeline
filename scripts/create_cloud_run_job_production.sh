#!/bin/bash

###############################################################################
# 🚀 Create Cloud Run Job - Production Environment
# Purpose: Create a job to train BOTH models (points + fantasy_points)
###############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "⚠️  gcp_config.sh not found, relying on environment variables."
fi

# Parse arguments (override config if provided)
TUNE_PARAMS="${1:-${TUNE_PARAMS:-false}}"

# Job name
JOB_NAME="nba-training-prod"

# Define targets and model directory
TARGETS="${TARGETS:-points fantasy_points}"
MODEL_PATH="gs://${BUCKET_NAME}/${MODELS_FOLDER}/prod"

echo "=================================================="
echo "🔧 CREATE CLOUD RUN JOB - PRODUCTION"
echo "=================================================="
echo ""
echo "📦 Job Configuration:"
echo "   • Name: ${JOB_NAME}"
echo "   • Targets: ${TARGETS}"
echo "   • Model Path: ${MODEL_PATH}"
echo "   • Tune Params: ${TUNE_PARAMS}"
echo "   • Region: ${REGION}"
echo "   • Image: ${PROD_IMAGE_URI}"
echo "   • Service Account: ${SERVICE_ACCOUNT}"
echo ""

# 🚀 Create or Update Cloud Run Job
echo "📦 Managing Cloud Run Job: ${JOB_NAME}..."

# Ensure secrets are defined
NBA_PROXY_USER_SECRET="${NBA_PROXY_USER_SECRET:-nba-proxy-user}"
NBA_PROXY_PASS_SECRET="${NBA_PROXY_PASS_SECRET:-nba-proxy-pass}"

# Check if the job already exists and update it if so
if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "🔄 Job exists. Updating configuration..."
    gcloud run jobs update ${JOB_NAME} \
      --image=${PROD_IMAGE_URI} \
      --region=${REGION} \
      --service-account=${SERVICE_ACCOUNT} \
      --memory=${MEMORY} \
      --cpu=${CPU} \
      --task-timeout=${TIMEOUT} \
      --max-retries=${MAX_RETRIES} \
      --set-env-vars="TARGETS=${TARGETS},TUNE_PARAMS=${TUNE_PARAMS},MODEL_PATH=${MODEL_PATH},SEASON=${SEASON},SEASON_TYPE=${SEASON_TYPE},SAVE_MODE=${SAVE_MODE}" \
      --set-secrets="NBA_PROXY_USER=${NBA_PROXY_USER_SECRET}:latest,NBA_PROXY_PASS=${NBA_PROXY_PASS_SECRET}:latest" \
      --quiet
else
    echo "✨ Job not found. Creating new job..."
    gcloud run jobs create ${JOB_NAME} \
      --image=${PROD_IMAGE_URI} \
      --region=${REGION} \
      --service-account=${SERVICE_ACCOUNT} \
      --memory=${MEMORY} \
      --cpu=${CPU} \
      --task-timeout=${TIMEOUT} \
      --max-retries=${MAX_RETRIES} \
      --set-env-vars="TARGETS=${TARGETS},TUNE_PARAMS=${TUNE_PARAMS},MODEL_PATH=${MODEL_PATH},SEASON=${SEASON},SEASON_TYPE=${SEASON_TYPE},SAVE_MODE=${SAVE_MODE}" \
      --set-secrets="NBA_PROXY_USER=${NBA_PROXY_USER_SECRET}:latest,NBA_PROXY_PASS=${NBA_PROXY_PASS_SECRET}:latest" \
      --quiet
fi

echo ""
echo "=================================================="
echo "✅ CLOUD RUN JOB CREATED!"
echo "=================================================="
echo ""
echo "📋 Job Summary:"
echo "   • Job Name: ${JOB_NAME}"
echo "   • Environment: PRODUCTION"
echo "   • Trains: Points + Fantasy Points"
echo "   • Tuning: ${TUNE_PARAMS}"
echo "   • Season: ${SEASON} (${SEASON_TYPE})"
echo ""
echo "🚀 Execute job:"
echo "   ./scripts/run_cloud_job_production.sh"
echo ""
echo "🔍 Monitor job execution:"
echo "   gcloud run jobs executions list --job=${JOB_NAME} --region=${REGION}"
echo ""