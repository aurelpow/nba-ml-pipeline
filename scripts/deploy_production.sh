#!/bin/bash

###############################################################################
# 🚀 Deploy to Production Environment
# Branch: main (production)
# Purpose: Update Docker image in Artifact Registry for production
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "⚠️  gcp_config.sh not found, relying on environment variables."
fi

echo "=================================================="
echo "🔧 DEPLOY TO PRODUCTION ENVIRONMENT"
echo "=================================================="
echo ""
echo "⚠️  WARNING: This will deploy to PRODUCTION!"
echo ""

# 🔄 1. Sync with GitHub (skip if in Jenkins)
if [ -z "$JENKINS_URL" ]; then
    echo "📥 Syncing with GitHub (Local Mode)..."
    cd "${PROJECT_DIR}"
    git fetch origin
    git reset --hard "origin/${PROD_BRANCH}"
else
    echo "⏭️ Jenkins detected: Skipping Git Sync"
fi

# 🧩 2. Display environment variables
echo "🧩 Step 2: Using environment configuration..."
echo "   📦 Project: ${PROJECT_ID}"
echo "   🌍 Region: ${REGION}"
echo "   📂 Repository: ${REPO_NAME}"
echo "   🏷️  Image: ${IMAGE_NAME}"
echo "   🔖 Tag: ${PROD_IMAGE_TAG}"
echo "   🎯 Full URI: ${PROD_IMAGE_URI}"
echo ""

# 🔐 3. Authenticate Docker (if needed)
echo "🔐 Step 3: Checking Docker authentication..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "✅ Docker authenticated"
echo ""

# 🚀 4. Build and push to Artifact Registry with 'latest' tag
echo "🚀 Step 4: Building and pushing image..."
echo "   ⏳ This may take several minutes..."
echo ""

gcloud builds submit \
  --tag "${PROD_IMAGE_URI}" \
  --project "${PROJECT_ID}" \
  --timeout=20m

echo ""
echo "=================================================="
echo "✅ PRODUCTION DEPLOYMENT COMPLETE!"
echo "=================================================="
echo ""
echo "📋 Deployment Summary:"
echo "   • Environment: PRODUCTION"
echo "   • Branch: ${PROD_BRANCH}"
echo "   • Image: ${PROD_IMAGE_URI}"
echo ""
echo "🔍 To verify your image:"
echo "   gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME} --filter='package=${IMAGE_NAME}'"
echo ""
