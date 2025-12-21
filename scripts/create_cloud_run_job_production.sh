#!/bin/bash

###############################################################################
# 🚀 Create Cloud Run Job - Production Environment
# Purpose: Create a job to train BOTH models (points + fantasy_points)
###############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/gcp_config.sh"

# Parse arguments (override config if provided)
TUNE_PARAMS="${1:-${TUNE_PARAMS:-true}}"
JOB_NAME="nba-training-prod"

TARGETS="${TARGETS:-points fantasy_points}"
MODEL_DIR="gs://${BUCKET_NAME}/${MODELS_FOLDER}/prod"

echo "=================================================="
echo "🔧 CREATE CLOUD RUN JOB - PRODUCTION"
echo "=================================================="
echo ""
echo "📦 Job Configuration:"
echo "   • Name: ${JOB_NAME}"
echo "   • Targets: ${TARGETS}"
echo "   • Model Dir: ${MODEL_DIR}"
echo ""

# Delete existing if present
if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "⚠️  Deleting existing job..."
    gcloud run jobs delete "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --quiet
fi

# Create job

# Ensure secrets are defined
NBA_PROXY_USER_SECRET="${NBA_PROXY_USER_SECRET:-nba-proxy-user}"
NBA_PROXY_PASS_SECRET="${NBA_PROXY_PASS_SECRET:-nba-proxy-pass}"

gcloud run jobs create ${JOB_NAME} \
  --image=${PROD_IMAGE_URI} \
  --region=${REGION} \
  --service-account=${SERVICE_ACCOUNT} \
  --memory=${MEMORY} \
  --cpu=${CPU} \
  --task-timeout=${TIMEOUT} \
  --max-retries=${MAX_RETRIES} \
  --set-env-vars="SEASON=${SEASON},SEASON_TYPE=${SEASON_TYPE},SAVE_MODE=bq,TARGET=${TARGETS},MODEL_PATH=${MODEL_DIR},TUNE_HYPERPARAMETERS=${TUNE_PARAMS}" \
  --set-secrets="NBA_PROXY_USER=${NBA_PROXY_USER_SECRET}:latest,NBA_PROXY_PASS=${NBA_PROXY_PASS_SECRET}:latest"

echo ""
echo "✅ Production job created: ${JOB_NAME}"
