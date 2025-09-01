#!/usr/bin/env bash
set -euo pipefail

# ---- required/optional env ----
: "${SEASON:?Please set SEASON (e.g. 2024-25)}"
: "${SEASON_TYPE:=Regular Season}"      # default to Regular Season
: "${SAVE_MODE:=bq}"                    # default to BigQuery
: "${DATE:?Please set DATE (e.g. 2025-05-05)}"
: "${DAYS_NUMBER:=1}"
: "${MODEL_PATH:=ml_dev/models/best_lgbm_model_v2.pkl}"

# Optional proxy creds (exported if present)
: "${NBA_PROXY_USER:=}"
: "${NBA_PROXY_PASS:=}"
export NBA_PROXY_USER NBA_PROXY_PASS PYTHONUNBUFFERED=1

# ---- helpers ----
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*"; }
trap 'echo "[ERROR $(ts)] Failed at line $LINENO"; exit 1' ERR

# ---- basic validation ----
if ! [[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "DATE must be YYYY-MM-DD (got: $DATE)"
  exit 2
fi

if ! [[ "$DAYS_NUMBER" =~ ^[0-9]+$ ]]; then
  echo "DAYS_NUMBER must be an integer (got: $DAYS_NUMBER)"
  exit 2
fi

# ---- main ----

log "▶️ Running all processes for season=$SEASON, date=$DATE (days=$DAYS_NUMBER, season_type=$SEASON_TYPE, save_mode=$SAVE_MODE)"

log "➡️ Running get_nba_players..."
python main.py -p get_nba_players -s "$SEASON" -sm "$SAVE_MODE"
log "✅ Finished get_nba_players"

log "➡️ Running get_nba_teams..."
python main.py -p get_nba_teams -sm "$SAVE_MODE"
log "✅ Finished get_nba_teams"

log "➡️ Running get_nba_schedule..."
python main.py -p get_nba_schedule -s "$SEASON" -sm "$SAVE_MODE"
log "✅ Finished get_nba_schedule"

log "➡️ Running get_nba_boxscore_basic..."
python main.py -p get_nba_boxscore_basic -s "$SEASON" -st "$SEASON_TYPE" -sm "$SAVE_MODE"
log "✅ Finished get_nba_boxscore_basic"

log "➡️ Running get_nba_advanced_boxscore..."
python main.py -p get_nba_advanced_boxscore -s "$SEASON" -st "$SEASON_TYPE" -sm "$SAVE_MODE"
log "✅ Finished get_nba_advanced_boxscore"

log "➡️ Running get_predictions_stats_points..."
python main.py -p get_predictions_stats_points -sm "$SAVE_MODE" -d "$DATE" -m "$MODEL_PATH"
log "✅ Finished get_predictions_stats_points"

log "✅ All processes completed.✅"