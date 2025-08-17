#!/usr/bin/env bash
set -euo pipefail

# Expect these as env-vars (or hard-code sensible defaults):
: "${SEASON:?Please set SEASON (e.g. 2024-25)}"
: "${SEASON_TYPE:=Regular Season}"  # default to Regular Season
: "${SAVE_MODE:=bq}"  # default to BigQuery
: "${DATE:?Please set DATE (e.g. 2025-05-05)}"
: "${DAYS_NUMBER:=1}"
: "${MODEL_PATH:=ml_dev/models/best_lgbm_model_v2.pkl}"

echo "▶️ Running all processes for season=$SEASON, date=$DATE (days=$DAYS_NUMBER)"

python main.py -p get_nba_players              -s "$SEASON" -sm "$SAVE_MODE"
python main.py -p get_nba_teams                -sm "$SAVE_MODE"
python main.py -p get_nba_boxscore_basic       -s "$SEASON" -st "$SEASON_TYPE" -sm "$SAVE_MODE"
#python main.py -p get_future_games             -s "$SEASON" -sm "$SAVE_MODE"  -d "$DATE"   -dn "$DAYS_NUMBER"
python main.py -p get_nba_advanced_boxscore    -s "$SEASON" -st "$SEASON_TYPE" -sm "$SAVE_MODE"
python main.py -p get_predictions_stats_points -sm "$SAVE_MODE"   -d "$DATE"   -m "$MODEL_PATH"

echo "✅ All processes completed."