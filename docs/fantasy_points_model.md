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

The training pipeline is defined in `src/train_fantasy_model.py`.

**Steps:**
1.  **Load Data**: Fetches Boxscores, Advanced Stats, and Player info.
2.  **Preprocessing**: Merges data, handles missing values, parses minutes.
3.  **Target Calculation**: Computes the `fantasy_points` column.
4.  **Feature Engineering**:
    - Creates historical features (time-aware).
    - Normalizes stats (per 36 min, per 100 poss).
    - Computes rolling averages.
    - Encodes categorical variables (Position, Team, etc.).
5.  **Split**: Time-based train/test split (auto-selected for best performance).
6.  **Tuning**: RandomizedSearchCV with TimeSeriesSplit.
7.  **Training**: Fits the final LightGBM model.
8.  **Evaluation**: Computes RMSE, MAE, R².
9.  **Saving**: Saves the model artifact (model, scaler, metadata) to disk or GCS.

**Usage:**
```bash
python main.py -p train_fantasy_model -s 2024-25 -m "ml_dev/models/fantasy_model.pkl" -sm "local"
```

## 🔮 Inference Pipeline

The inference pipeline is defined in `src/get_predictions_fantasy_points.py`.

**Steps:**
1.  **Load Schedule**: Gets games for the target date.
2.  **Load Model**: Loads the trained artifact.
3.  **Feature Construction**: Recreates the exact features used in training for the target players.
    - *Crucial*: Uses the same historical windows and normalization logic.
4.  **Prediction**: Generates point estimates.
5.  **Output**: Saves predictions to CSV or BigQuery.

**Usage:**
```bash
python main.py -p get_predictions_fantasy_points -s 2024-25 -d "2025-04-13" -m "ml_dev/models/fantasy_model.pkl" -sm "local"
```

## 📊 EDA & Analysis

See `ml_dev/notebooks/fantasy_points_eda.ipynb` for exploratory data analysis, including:
- Distribution of fantasy points.
- Correlation analysis.
- Feature importance.
- Bonus achievement rates.
