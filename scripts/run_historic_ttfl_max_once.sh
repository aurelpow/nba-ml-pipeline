#!/bin/bash

###############################################################################
# Run ONCE - Historic TTFL max (Develop image)
# Purpose: Build the `nba_historic_ttfl_max` BigQuery table (career-high TTFL
#          per player, regular season + playoffs, all seasons before $SEASON).
#          Creates a throw-away Cloud Run Job, executes it, waits for the
#          result and deletes the job on success, so it can never be
#          re-triggered or scheduled by accident.
#
# Not part of run_all.sh / Cloud Scheduler. BigQuery table and dataset are the
# same for develop and prod, so one run is enough.
#
# Prerequisite: the develop image must contain the get_historic_ttfl_max
#               process (push `dev` and wait for the Jenkins develop build).
#
# Usage:
#   ./scripts/run_historic_ttfl_max_once.sh            # run, then delete the job
#   KEEP_JOB=true ./scripts/run_historic_ttfl_max_once.sh   # keep the job (debugging)
###############################################################################

set -e  # Exit on any error

# Load GCP configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/gcp_config.sh" ]; then
    source "${SCRIPT_DIR}/gcp_config.sh"
else
    echo "gcp_config.sh not found, relying on environment variables."
fi

: "${SEASON:?Please set SEASON (e.g. 2026-27) in gcp_config.sh or the environment}"

JOB_NAME="nba-historic-ttfl-max-once"
KEEP_JOB="${KEEP_JOB:-false}"

# ~46 API calls (2 per season) * up to 60s timeout, through the proxy.
HISTORIC_MEMORY="${HISTORIC_MEMORY:-2Gi}"
HISTORIC_CPU="${HISTORIC_CPU:-1}"
HISTORIC_TIMEOUT="${HISTORIC_TIMEOUT:-3600s}"

NBA_PROXY_USER_SECRET="${NBA_PROXY_USER_SECRET:-nba-proxy-user}"
NBA_PROXY_PASS_SECRET="${NBA_PROXY_PASS_SECRET:-nba-proxy-pass}"

# --command + --args override the Dockerfile ENTRYPOINT (run_all.sh).
# Seasons strictly before $SEASON are processed (current season = boxscore table).
COMMAND="python"
ARGS="main.py,-p,get_historic_ttfl_max,-s,${SEASON},-sm,bq"

echo "=================================================="
echo "HISTORIC TTFL MAX - ONE-SHOT RUN"
echo "=================================================="
echo ""
echo "   * Job: ${JOB_NAME}"
echo "   * Image: ${DEV_IMAGE_URI}"
echo "   * Region: ${REGION}"
echo "   * Seasons: all before ${SEASON}"
echo "   * Table: ${PROJECT_ID}.nba_dataset.nba_historic_ttfl_max (overwritten)"
echo ""

JOB_FLAGS=(
    --image="${DEV_IMAGE_URI}"
    --region="${REGION}"
    --service-account="${SERVICE_ACCOUNT}"
    --memory="${HISTORIC_MEMORY}"
    --cpu="${HISTORIC_CPU}"
    --task-timeout="${HISTORIC_TIMEOUT}"
    --max-retries=0   # the script is idempotent but each retry burns proxy bandwidth
    --command="${COMMAND}"
    --args="${ARGS}"
    --set-env-vars="SAVE_MODE=bq"
    --set-secrets="NBA_PROXY_USER=${NBA_PROXY_USER_SECRET}:latest,NBA_PROXY_PASS=${NBA_PROXY_PASS_SECRET}:latest"
    --quiet
)

if gcloud run jobs describe "${JOB_NAME}" --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Job exists (previous failed run?). Updating configuration..."
    gcloud run jobs update "${JOB_NAME}" --project="${PROJECT_ID}" "${JOB_FLAGS[@]}"
else
    echo "Creating job..."
    gcloud run jobs create "${JOB_NAME}" --project="${PROJECT_ID}" "${JOB_FLAGS[@]}"
fi

echo ""
echo "Executing job (waiting for completion)..."
if gcloud run jobs execute "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --wait; then
    echo ""
    echo "Execution succeeded."
    if [ "${KEEP_JOB}" = "true" ]; then
        echo "KEEP_JOB=true: job '${JOB_NAME}' kept."
    else
        gcloud run jobs delete "${JOB_NAME}" \
            --region="${REGION}" --project="${PROJECT_ID}" --quiet
        echo "Job '${JOB_NAME}' deleted - it cannot run again."
    fi
else
    echo ""
    echo "Execution FAILED - job kept so you can inspect and re-run this script."
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
    exit 1
fi

echo ""
echo "Verify in BigQuery:"
echo "   bq query --use_legacy_sql=false \\"
echo "     \"SELECT season_type, COUNT(*) AS n_players, MAX(max_ttfl) AS best \\"
echo "      FROM \\\`${PROJECT_ID}.nba_dataset.nba_historic_ttfl_max\\\` GROUP BY season_type\""
echo ""
