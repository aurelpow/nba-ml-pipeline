# NBA Project ML

A complete, modular pipeline for fetching, processing, modeling, and predicting NBA player performance. Whether you’re exploring the data in a notebook or running daily inference in production, this repo has you covered.

---

## 🚀 Key Components

1. **Data Ingestion**

   - **Players & Teams**: Retrieve active rosters and team metadata via the NBA Stats API. ([swar/nba_api](https://github.com/swar/nba_api.git))
   - **Boxscores**: Pull both basic and advanced boxscore statistics for every game.
   - **Schedule**: Fetch upcoming game schedules (but by default only process completed games).

2. **Feature Engineering**

   - **Rolling Statistics**: Compute configurable rolling-window averages (e.g. last 5, 10, 15 games) for pace, usage, shooting rates, etc.
   - **Matchup Averages**: Calculate per-opponent and per-position matchup performance (full history + recent windows).
   - **Normalization**: Derive per-36-minute and per-possession rates.
   - **Scaling**: Standardize features via `StandardScaler` for model input.

3. **Model Training & Evaluation**

   - **Notebook Workflow**: Explore data, engineer features, train LightGBM models, and evaluate via cross-validation in the Jupyter notebook [NBA\_Players\_Points\_Prediction\_ML.ipynb](ml_dev/notebooks/NBA_Players_Points_Prediction_ML.ipynb).
   - **Hyperparameter Tuning**: Grid-search rolling window sizes and `LightGBM` parameters to optimize RMSE.

4. **Inference & Deployment**

   - **Persistence**: Save the trained `best_lgbm_model.pkl` artifact.
   - **Dockerized Pipeline**: Single-entry `run_all.sh` script runs the full ETL + prediction workflow daily.
   - **Scheduling**: Easily schedule via cron or CI (GitHub Actions, Jenkins, etc.) to generate fresh `nba_boxscore_predictions.csv`.

---

## 📁 Repository Structure

```
NBA_project_ML/
├── Dockerfile
├── run_all.sh            # Orchestrates all processes via env-vars
├── requirements.txt      # Core Python dependencies
├── main.py               # CLI entrypoint for individual subprocesses
├── src/                  # Modular ETL and inference scripts
│   ├── get_nba_players.py
│   ├── get_nba_teams.py
│   ├── get_nba_boxscore_basic.py
│   ├── get_nba_advanced_boxscore.py
│   ├── get_future_games.py
│   └── get_predictions_stats_points.py
├── common/               # Shared utilities, parsers, and singletons
│   ├── parser.py
│   └── utils.py
├── ml_dev/
│   ├── notebooks/        # Jupyter notebooks for EDA & model development
│   │   └── NBA_Players_Points_Prediction_ML.ipynb
│   └── models/           # Serialized model artifacts
│       └── best_lgbm_model_v2.pkl
├── databases/            # Raw and processed data files
│   ├── nba_boxscore_basic.csv
│   ├── nba_boxscore_advanced.csv
│   ├── nba_future_games_df.csv
│   ├── nba_players_df.csv
│   ├── nba_points_predictions_df.csv
│   └── nba_teams_df.csv
└── README.md             # You are here
```

---

## ⚙️ Installation & Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/NBA_project_ML.git
   cd NBA_project_ML
   ```

2. **Build the Docker image**

   ```bash
   docker build -t nba-pipeline:latest .
   ```

3. **(Optional) Local Python environment**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

---

## 🔄 Running the Pipeline

### All-in-One (preferred)

Run every process—players, teams, boxscores, and predictions—with one command:

```bash
docker run --rm \
  -v "${PWD}/databases:/app/databases" \
  -e SEASON="2024-25" \
  -e DATE="$(date +'%Y-%m-%d')" \
  nba-pipeline:latest
```

### Individual Processes

You can still target a single step via CLI args:

```bash
# Example: only fetch basic boxscores
docker run --rm \
  -v "${PWD}/databases:/app/databases" \
  nba-pipeline:latest \
  -p get_nba_boxscore_basic -s 2024-25
```

---

## 📊 Model Insights & Metrics

- **Cross-Validation RMSE**: \~**X.XX** points (5-fold CV on hold-out season).
- **Top Features**:
  1. `avg_points_vs_opponent_per36`
  2. `avg_pts_opp_position_per_poss`
  3. Recent `fieldGoalsMade_roll10_per36`

Refer to the training notebook for full EDA, feature importance plots, and hyperparameter results.

---

## 📄 License & Credits

- **Author**: Aurelien Pow ([@aurelpow](https://github.com/aurelpow))

---
---

## 🏗️ Model Training Process

The training pipeline is fully coded in the Jupyter notebook **NBA\_Players\_Points\_Prediction\_ML.ipynb**, but here is a high-level overview:

1. **Load and Clean Data**

   - Merge basic and advanced boxscores with player & team metadata.
   - Filter out DNPs and games with incomplete data.

2. **Feature Engineering**

   - Compute rolling-window features for each stat (e.g. last 5, 10, 15 games).
   - Derive matchup-specific aggregates (`avg_points_vs_opponent`, `avg_pts_opp_position`) and their rolling variants.
   - Normalize to per-36 minutes and per-possession rates.
   - Standardize numeric features with `StandardScaler`.

3. **Train-Test Split**

   - Split by season or by date to simulate true forecasting (e.g. train on seasons 2022-23 & 2023-24, test on 2024-25).
   - Ensure no data leakage by time.

4. **Model Selection & Hyperparameter Tuning**

   - Use `lightgbm.LGBMRegressor` with early stopping on a validation set.
   - Grid-search window sizes (5, 10, 15) and key hyperparameters (`num_leaves`, `max_depth`, `learning_rate`).

5. **Cross-Validation**

   - Perform 5-fold time-series cross-validation to measure RMSE stability.
   - Save the best model and scaler artifacts to `ml_dev/models/`.

---

## 📈 Model Evaluation

After training, the final model is evaluated on a hold-out season:

| Metric        | Value     |
| ------------- | --------- |
| RMSE (points) | **4.070**  |
| MAE (points)  | **2.601**  |
| R²            | **0.798** |

### Feature Importance



- **Top 5 Features**:
  1. `avg_pts_opp_position_last_10_per36`
  2. `fieldGoalsMade_per_poss_rolling_5`
  3. `offensiveRating_per_position_all_per_poss`
  4. `avg_pts_opp_position_last_20_per36`
  5. `avg_pts_opp_position_last_all_per36`

### Error Analysis

- Analyze residuals by position, by opponent, and by minutes played to identify systematic biases.
- Visualize prediction vs. actual scatter plots for sample games.

---

## 🚀 Future Improvements

- **Automated Retraining**: Add a scheduled job to retrain the model weekly or monthly when performance degrades.
- **Advanced Models**: Experiment with tree ensembles (XGBoost), stacking, or neural networks for further gains.
- **Feature Expansion**: Incorporate opponent defensive metrics, player injury status, and lineup configurations.
- **API Service**: Expose predictions via a REST API (FastAPI/Flask) for real-time applications.
- **Dashboard**: Build an interactive dashboard (Plotly Dash or Power BI) to visualize predictions and model performance.

---

*Generated on 2025-08-02*