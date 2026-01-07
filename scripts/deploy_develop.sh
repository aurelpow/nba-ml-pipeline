#!/bin/bash

###############################################################################
# 🚀 Deploy to Develop Environment
# Branch: feature/fantsay-points-prediction
# Purpose: Update Docker image in Artifact Registry for development testing
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
echo "🔧 DEPLOY TO DEVELOP ENVIRONMENT"
echo "=================================================="
echo ""

# 🔄 1. Sync with GitHub (skip if in Jenkins)
if [ -z "$JENKINS_URL" ]; then
    echo "📥 Step 1: Syncing with GitHub..."
    echo "   • Branch: ${DEV_BRANCH}"
    echo "   • Directory: ${PROJECT_DIR}"
    cd "${PROJECT_DIR}" || { echo "❌ Directory not found: ${PROJECT_DIR}"; exit 1; }

    git fetch origin
    git reset --hard "origin/${DEV_BRANCH}"

    echo "✅ Code synced with remote branch"
    echo ""
else
    echo "⏭️  Step 1: Skipping GitHub sync (Jenkins environment detected)"
    cd "${PROJECT_DIR}"
fi

# 🧩 2. Display environment variables
echo "🧩 Step 2: Using environment configuration..."
echo "   📦 Project: ${PROJECT_ID}"
echo "   🌍 Region: ${REGION}"
echo "   📂 Repository: ${REPO_NAME}"
echo "   🏷️  Image: ${IMAGE_NAME}"
echo "   🔖 Tag: ${DEV_IMAGE_TAG}"
echo "   🎯 Full URI: ${DEV_IMAGE_URI}"
echo ""

# 🔐 3. Authenticate Docker (if needed)
echo "🔐 Step 3: Checking Docker authentication..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "✅ Docker authenticated"
echo ""

# 🚀 4. Build and push to Artifact Registry with 'develop' tag
echo "🚀 Step 4: Building and pushing image..."
echo "   ⏳ This may take several minutes..."
echo ""

gcloud builds submit \
  --tag "${DEV_IMAGE_URI}" \
  --project "${PROJECT_ID}" \
  --timeout=20m

echo ""
echo "=================================================="
echo "✅ DEPLOYMENT COMPLETE!"
echo "=================================================="
echo ""
echo "📋 Deployment Summary:"
echo "   • Environment: DEVELOP"
echo "   • Branch: ${DEV_BRANCH}"
echo "   • Image: ${DEV_IMAGE_URI}"
echo ""
echo "🔍 To verify your image:"
echo "   gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME} --filter='package=${IMAGE_NAME}'"
echo ""
echo "🚀 Next steps:"
echo "   1. Test the image in develop environment"
echo "   2. Verify training pipeline works as expected"
echo "   3. When ready, merge to main and deploy to production"
echo ""
