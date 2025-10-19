#!/usr/bin/env bash
set -euo pipefail

# ---- required/optional env ----
: "${SEASON:?Please set SEASON (e.g. 2024-25)}"
: "${SEASON_TYPE:=Regular Season}"      # default to Regular Season
: "${SAVE_MODE:=bq}"                    # default to BigQuery
: "${MODEL_PATH:=ml_dev/models/best_lgbm_model_v2.pkl}"

# Optional proxy creds (exported if present)
: "${NBA_PROXY_USER:=}"
: "${NBA_PROXY_PASS:=}"
export NBA_PROXY_USER NBA_PROXY_PASS PYTHONUNBUFFERED=1

# If DATE not provided, use "today" in Europe/Madrid
if [ -z "${DATE:-}" ]; then
  DATE="$(python - <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
z = ZoneInfo("Europe/Madrid")
print(datetime.now(z).date().isoformat())
PY
)"
fi

# ---- helpers ----
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*"; }
trap 'echo "[ERROR $(ts)] Failed at line $LINENO"; exit 1' ERR


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

log "➡️ Running train_model..."
python main.py -p train_model -sm "$SAVE_MODE" -m "$MODEL_PATH"
log "✅ Finished train_model"

log "➡️ Running get_predictions_stats_points..."
python main.py -p get_predictions_stats_points -sm "$SAVE_MODE" -d "$DATE" -m "$MODEL_PATH"
log "✅ Finished get_predictions_stats_points"

log "✅ All processes completed.✅"