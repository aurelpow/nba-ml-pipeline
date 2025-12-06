#!/bin/bash

###############################################################################
# 🚀 Deploy to Develop Environment
# Branch: feature/fantsay-points-prediction
# Purpose: Update Docker image in Artifact Registry for development testing
###############################################################################

set -e  # Exit on any error

echo "=================================================="
echo "🔧 DEPLOY TO DEVELOP ENVIRONMENT"
echo "=================================================="
echo ""

# 🔄 1. Sync with GitHub
echo "📥 Step 1: Syncing with GitHub..."
cd ~/nba_project_ML || { echo "❌ Directory not found!"; exit 1; }

git fetch origin
git reset --hard origin/feature/fantsay-points-prediction

echo "✅ Code synced with remote branch"
echo ""

# 🧩 2. Define variables for DEVELOP environment
echo "🧩 Step 2: Setting up environment variables..."

export PROJECT_ID="ml-nba-project"
export REGION="us-central1"
export REPO="nba-docker-repo"
export IMAGE="nba_project"
export ENVIRONMENT="develop"  # Develop environment marker

# Build image URI with develop tag
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}"

echo "   📦 Project: ${PROJECT_ID}"
echo "   🌍 Region: ${REGION}"
echo "   📂 Repository: ${REPO}"
echo "   🏷️  Image: ${IMAGE}"
echo "   🔖 Tag: develop"
echo "   🎯 Full URI: ${IMAGE_URI}:develop"
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
  --tag "${IMAGE_URI}:develop" \
  --project "${PROJECT_ID}" \
  --timeout=20m

echo ""
echo "=================================================="
echo "✅ DEPLOYMENT COMPLETE!"
echo "=================================================="
echo ""
echo "📋 Deployment Summary:"
echo "   • Environment: DEVELOP"
echo "   • Branch: feature/fantsay-points-prediction"
echo "   • Image: ${IMAGE_URI}:develop"
echo ""
echo "🔍 To verify your image:"
echo "   gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO} --filter='package=${IMAGE}'"
echo ""
echo "🚀 Next steps:"
echo "   1. Test the image in develop environment"
echo "   2. Verify training pipeline works as expected"
echo "   3. When ready, merge to main and deploy to production"
echo ""
