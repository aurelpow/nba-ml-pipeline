#!/usr/bin/env bash
set -euo pipefail

# ---- required/optional env ----
: "${SEASON:?Please set SEASON (e.g. 2024-25)}"
: "${SEASON_TYPE:=Regular Season}"      # default to Regular Season
: "${SAVE_MODE:=local}"                    # default to local (bq for Cloud)
: "${MODEL_PATH:=ml_dev/models}"            # default to local directory
: "${TARGETS:=points}"                      # default to points only
: "${TUNE_HYPERPARAMETERS:=false}"         # default to no tuning

# Optional proxy creds (exported if present)
: "${NBA_PROXY_USER:=}"
: "${NBA_PROXY_PASS:=}"
: "${DISCORD_WEBHOOK_URL:=}"
export NBA_PROXY_USER NBA_PROXY_PASS DISCORD_WEBHOOK_URL PYTHONUNBUFFERED=1

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

# EVAL_DATE: date to evaluate predictions against actuals (defaults to yesterday)
if [ -z "${EVAL_DATE:-}" ]; then
  EVAL_DATE="$(python - <<'PY'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
z = ZoneInfo("Europe/Madrid")
print((datetime.now(z).date() - timedelta(days=1)).isoformat())
PY
)"
fi

# ---- helpers ----
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(ts)] $*"; }
trap 'echo "[ERROR $(ts)] Failed at line $LINENO"; exit 1' ERR


# ---- main ----

log "▶️ Running all processes for season=$SEASON, date=$DATE (season_type=$SEASON_TYPE, save_mode=$SAVE_MODE)"

# ── 1. Post-game evaluation (always runs first, independent of today's games) ─
log "➡️ Running post_evaluation for eval_date=$EVAL_DATE..."
POST_EVALUATION_ARGS=(-p post_evaluation -sm "$SAVE_MODE" -d "$EVAL_DATE")
if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
  POST_EVALUATION_ARGS+=(--discord_webhook_url "$DISCORD_WEBHOOK_URL")
fi
python main.py "${POST_EVALUATION_ARGS[@]}"
log "✅ Finished post_evaluation"

# ── 2. Games gate ─────────────────────────────────────────────────────────────
# Exit code 2 = no games for DATE → nothing to collect, train, or predict.
log "➡️ Checking if games are scheduled for $DATE..."
set +e
python main.py -p check_games_scheduled -d "$DATE" -sm "$SAVE_MODE"
GAMES_RC=$?
set -e

if [ "$GAMES_RC" -eq 2 ]; then
  log "⏭️  No games for $DATE — skipping data collection, training, and predictions."
  log "✅ All processes completed (no-games day).✅"
  exit 0
elif [ "$GAMES_RC" -ne 0 ]; then
  log "❌ check_games_scheduled failed (exit $GAMES_RC) — aborting."
  exit "$GAMES_RC"
fi
log "✅ Games found for $DATE — running full pipeline."
# ─────────────────────────────────────────────────────────────────────────────

# ── 3. Full pipeline ──────────────────────────────────────────────────────────

# ── Proxy pre-flight (always runs; prints diagnostics, never blocks) ────────
if [ -n "${NBA_PROXY_USER:-}" ] && [ -n "${NBA_PROXY_PASS:-}" ]; then
  log "🔍 Running proxy pre-flight check..."
  python scripts/test_proxy.py || log "⚠️  Proxy pre-flight reported issues – check logs above"
else
  log "⚠️  NBA_PROXY_USER / NBA_PROXY_PASS not set – skipping proxy pre-flight"
fi
# ────────────────────────────────────────────────────────────────────────────

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

log "➡️ Running get_injury_report..."
python main.py -p get_injury_report -sm "$SAVE_MODE" -d "$DATE"
log "✅ Finished get_injury_report"

log "➡️ Running compute_availability..."
python main.py -p compute_availability -sm "$SAVE_MODE" -d "$DATE"
log "✅ Finished compute_availability"

log "➡️ Running train..."
# Convert space-separated targets to individual arguments
python main.py -p train -sm "$SAVE_MODE" -m "$MODEL_PATH" -t $TARGETS --tune_params "$TUNE_HYPERPARAMETERS"
log "✅ Finished train"

log "➡️ Running get_predictions_stats_points..."
python main.py -p get_predictions_stats_points -sm "$SAVE_MODE" -d "$DATE" -m "$MODEL_PATH"
log "✅ Finished get_predictions_stats_points"

log "➡️ Running get_predictions_fantasy_points..."
python main.py -p get_predictions_fantasy_points -sm "$SAVE_MODE" -d "$DATE" -m "$MODEL_PATH"
log "✅ Finished get_predictions_fantasy_points"

log "✅ All processes completed.✅"