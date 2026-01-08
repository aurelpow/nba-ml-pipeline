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
if [ -z "$CI" ] && [ -z "$JENKINS_URL" ]; then
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "❌ Deployment cancelled"
        exit 0
    fi
else
    echo "⏭️  CI/CD environment detected: Skipping confirmation prompt"
fi

# 🔄 1. Sync with GitHub (skip if in Jenkins)
# 🔄 1. Sync with GitHub (skip if in Jenkins)
if [ -z "$JENKINS_URL" ]; then
    echo "📥 Syncing with GitHub (Local Mode)..."
    cd "${PROJECT_DIR}"
    git fetch origin
    git reset --hard "origin/${PROD_BRANCH}"
else
    echo "⏭️ Jenkins detected: Skipping Git Sync"
fi

# 🧩 2. Define variables for PRODUCTION environment
echo "🧩 Step 2: Setting up environment variables..."

export PROJECT_ID="ml-nba-project"
export REGION="us-central1"
export REPO="nba-docker-repo"
export IMAGE="nba_project"
export ENVIRONMENT="production"

# Build image URI with latest tag
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}"

echo "   📦 Project: ${PROJECT_ID}"
echo "   🌍 Region: ${REGION}"
echo "   📂 Repository: ${REPO}"
echo "   🏷️  Image: ${IMAGE}"
echo "   🔖 Tag: latest"
echo "   🎯 Full URI: ${IMAGE_URI}:latest"
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
  --tag "${IMAGE_URI}:latest" \
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
echo "   gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO} --filter='package=${IMAGE}'"
echo ""
