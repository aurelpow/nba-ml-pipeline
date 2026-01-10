#!/bin/bash

###############################################################################
# 🗑️  Delete Cloud Run Job - Develop Environment
# Purpose: Clean up develop job resources
#
# Usage:
#   ./delete_cloud_job_develop.sh <target>
#
# Examples:
#   ./delete_cloud_job_develop.sh fantasy_points
#   ./delete_cloud_job_develop.sh points
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/gcp_config.sh"

# Parse arguments
TARGET="${1}"

if [ -z "$TARGET" ]; then
    echo "❌ ERROR: Target is required"
    echo ""
    echo "Usage: ./delete_cloud_job_develop.sh <target>"
    echo "  targets: points, fantasy_points"
    exit 1
fi

# Validate target
if [[ "$TARGET" != "points" && "$TARGET" != "fantasy_points" ]]; then
    echo "❌ ERROR: Invalid target '${TARGET}'"
    echo "   Valid options: points, fantasy_points"
    exit 1
fi

# Job name - replace underscores with dashes for GCP compliance
JOB_NAME="nba-training-${TARGET_NAME//_/-}-develop"

echo "=================================================="
echo "🗑️  DELETE CLOUD RUN JOB - DEVELOP"
echo "=================================================="
echo ""
echo "⚠️  WARNING: This will delete the job '${JOB_NAME}'"
echo ""

if [ -z "$CI" ] && [ -z "$JENKINS_URL" ]; then
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "❌ Deletion cancelled"
        exit 0
    fi
else
    echo "⏭️  CI/CD environment detected: Skipping confirmation prompt"
fi

echo ""
echo "🗑️  Deleting job..."
gcloud run jobs delete "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet

echo ""
echo "=================================================="
echo "✅ JOB DELETED!"
echo "=================================================="
echo ""
