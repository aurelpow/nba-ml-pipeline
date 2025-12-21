# Fantasy Points Prediction Model

This model predicts NBA player fantasy points based on the TTFL (TrashTalk Fantasy League) scoring system. It leverages historical performance, opponent strength, and advanced stats to generate daily projections.

## 🎯 Target Variable: Fantasy Points (TTFL)

The target variable is calculated using the TTFL formula:

$$
\text{Fantasy Points} = \text{PTS} + \text{REB} + \text{AST} + \text{STL} + \text{BLK} + \text{FGM} + \text{3PM} + \text{FTM} - \text{TOV} - (\text{FGA} - \text{FGM}) - (\text{3PA} - \text{3PM}) - (\text{FTA} - \text{FTM})
$$

*Note: Missed shots (FG, 3P, FT) and turnovers are penalized.*

## 🧠 Model Architecture

- **Algorithm**: LightGBM Regressor
- **Objective**: Regression (RMSE)
- **Features**:
    - **Rolling Stats**: 5, 10, 20 game windows (Mean)
    - **Per-Minute/Per-Possession**: Normalized stats to account for playing time and pace.
    - **Historical Opponent Stats**: How well a player's position group performs against the specific opponent.
    - **Context**: Home/Away, Rest Days (implicit in date), Opponent Strength.

## 🛠️ Training Pipeline

The training pipeline uses the unified trainer in `src/training/train.py` (class: `UnifiedModelTrainer`).

**Steps:**
1.  **Load Data**: Fetches Boxscores, Advanced Stats, and Player info.
2.  **Preprocessing**: Merges data, handles missing values, parses minutes.
3.  **Target Calculation**: Computes the `fantasy_points` column using `src/targets/fantasy_points.py`.
4.  **Feature Engineering**:
    - Creates historical features (time-aware).
    - Normalizes stats (per 36 min, per 100 poss).
    - Computes rolling averages.
    - Encodes categorical variables (Position, Team, etc.).
5.  **Split**: Time-based train/test split (auto-selected for best performance).
6.  **Tuning**: RandomizedSearchCV with TimeSeriesSplit (optional).
7.  **Training**: Fits the final LightGBM model.
8.  **Evaluation**: Computes RMSE, MAE, R².
9.  **Saving**: Saves the model artifact (model + metadata) to disk or GCS.

**Usage:**
```bash
# Fast training (no tuning)
python main.py -p train -t fantasy_points -m "ml_dev/models/fantasy_points_model.pkl" -sm "local"

# With hyperparameter tuning
python main.py -p train -t fantasy_points -m "ml_dev/models/" -sm "local" --tune_params true
```

## 🔮 Inference Pipeline

The inference pipeline uses the unified predictor in `src/predictors/unified_predictor.py` (class: `UnifiedPredictor`).

**Steps:**
1.  **Load Schedule**: Gets games for the target date.
2.  **Load Model**: Loads the trained artifact from local or GCS.
3.  **Feature Construction**: Recreates the exact features used in training for the target players.
    - *Crucial*: Uses the same historical windows and normalization logic.
4.  **Prediction**: Generates point estimates and volatility metrics.
5.  **Output**: Saves predictions in narrow format (Measure + Predictions columns) to CSV or BigQuery.
    - Intelligent append logic prevents duplicates when re-running same dates

**Usage:**
```bash
python main.py -p get_predictions_fantasy_points -d "2025-04-13" -m "ml_dev/models/fantasy_points_model.pkl" -sm "local"
```

**Output Format:**
- `Measure`: 2 (fantasy predictions) or 4 (fantasy volatility)
- `Predictions`: Numeric prediction value
- Other columns: gameId, gameDate, teamId, opponentId, personId, player_slug

## 📊 EDA & Analysis

See `ml_dev/notebooks/fantasy_points_eda.ipynb` for exploratory data analysis, including:
- Distribution of fantasy points.
- Correlation analysis.
- Feature importance.
- Bonus achievement rates.
