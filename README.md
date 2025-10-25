# NBA Player Predictions - End to End Pipeline (Docker +Google Cloud )

*A complete, modular pipeline for fetching, processing, modeling, and predicting NBA player performance. 
Whether you're exploring the data in a notebook or running daily inference in production, this repo has you covered.*

I built this because I love **basketball + data🏀📈**. 

---

## ✨ Recent Enhancements
![GitHub Release](https://img.shields.io/github/v/release/aurelpow/nba-ml-pipeline?color=blue&logo=github)

**Production Training Pipeline (`train_model.py`):**
- Automated train/test split selection (15%/20%/25%) with time-series cross-validation
- Hyperparameter tuning: `RandomizedSearchCV` with `TimeSeriesSplit` (20 iterations, 9 params)
- Feature engineering: position groups, historical opponent stats, rolling windows (5/10/20 games), per-36/per-possession metrics
- Complete artifact packaging: model + scaler + features + metrics

**Inference Pipeline (`get_predictions_stats_points.py`):**
- Mirror-accurate feature engineering matching training pipeline
- Handles missing data, new categories, DNPs gracefully
- Supports local CSV and BigQuery persistence

---

## 📥 Data Sources and Ingestion
[swar/nba_api](https://github.com/swar/nba_api/)

   - **Players**: Retrieve active rosters via the NBA Stats API
      - Source : [swar/nba_api/stats/endpoints/playerindex](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/playerindex.py)
      - Ingestion : [src/get_nba_players](src/get_nba_players.py)
   - **Teams**: Retrieve team metadata via the NBA Stats API.
      - Source : [swar/nba_api/stats/static/teams](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/static/teams.py)
      - Ingestion : [src/get_nba_teams](src/get_nba_teams.py)
   - **Boxscores**: Pull both basic and advanced boxscore statistics for every game.
      - **Basic Boxscore**: 
         - Source : [swar/nba_api/stats/endpoints/boxscoretraditionalv3](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/boxscoretraditionalv3.py)
         - Ingestion : [src/get_nba_boxscore_basic](src/get_nba_boxscore_basic.py) 
      - **Advanced Boxscore**
         - Source : [swar/nba_api/stats/endpoints/boxscoreadvancedv3](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/boxscoreadvancedv3.py)
         - Ingestion : [src/get_nba_advanced_boxscore](src/get_nba_advanced_boxscore.py) 
   - **Schedule**: Fetch all game schedules for a specific season.
      - Source [swar/nba_api/stats/endpoints/scheduleleaguev2](https://github.com/swar/nba_api/blob/master/src/nba_api/stats/endpoints/scheduleleaguev2.py)
      - Ingestion : [src/get_nba_schedule.py](src/get_nba_schedule.py)

> 🔐 NBA API calls can use a private proxy ([DecoDO](https://dashboard.decodo.com/welcome)) via `HTTP_PROXY` / `HTTPS_PROXY`. — avoids timeouts  
> In Cloud Run, mount these from **Secret Manager**.

## 🧠 Machine Learning Model

- **Notebook**:  [NBA_Players_Points_Prediction_ML](ml_dev/notebooks/NBA_Players_Points_Prediction_ML.ipynb)
  - Data exploration & cleaning
  - Feature engineering (touches, shooting splits, contested/uncontested, defended-at-rim, opponent/position effects, rolling windows)
  - Model selection: **LightGBM** for Points (PTS)
  - Evaluation & tuning (metrics + plots)
  - Export artifact: `best_lgbm_model.pkl`

### 🚀 Training Pipeline ([src/train_model.py](src/train_model.py))
Automated production training with time-series cross-validation, hyperparameter tuning, and complete artifact packaging.

**Usage:**
```bash
python -u main.py -p train_model -s 2024-25 -m "ml_dev/models/best_lgbm_model.pkl" -sm "local"
```

---
## 🧰 Inference Pipeline

### ([src/get_predictions_stats_points.py](src/get_predictions_stats_points.py))

Generates player-game predictions with feature engineering matching the training pipeline exactly.

**Workflow:**
1. Load schedule for target date & expand to player-game rows
2. Load model from local path or `gs://...` (auto-downloads)
3. Build features: historical stats, rolling windows (5/10/20), per-36/per-possession metrics, categorical encoding
4. Generate predictions & save to CSV or BigQuery

**Usage:**
```bash
python -u main.py -p get_predictions_stats_points -s 2024-25 -d "2025-04-13" -m "ml_dev/models/best_lgbm_model.pkl" -sm "local"
```

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
│   ├── get_nba_schedule.py
│   ├── get_predictions_stats_points.py
│   └── train_model.py   
├── common/               # Shared utilities, parsers, and singletons
│   ├── common.py
│   ├── io_utils.py
│   ├── parser.py
│   ├── singleton_meta.py
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
## ⚙️ Configuration (env vars)

| Var | Required | Example | Notes |
|---|---|---|---|
| `SEASON` | ✅ | `2024-25` | Target season |
| `SEASON_TYPE` | ❕ | `Regular Season` | Default: Regular Season |
| `DATE` | ❕ | `2025-05-01` | Start date for inference (required for predictions) |
| `DAYS_NUMBER` | ❕ | `1` | Days ahead (default: 1) |
| `SAVE_MODE` | ❕ | `local` \| `bq` | CSV vs BigQuery (default: local) |
| `MODEL_PATH` | ❕ | `ml_dev/models/best_lgbm_model.pkl` \| `gs://…/model.pkl` | Local or GCS path |
| `HTTP_PROXY` / `HTTPS_PROXY` | ❕ | secret | Use in cloud to avoid API timeouts |

> **Note**: If `MODEL_PATH` starts with `gs://`, the app downloads the file at runtime (see `common/io_utils.py::load_model()`).


## ⚙️  Setup

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

### A) Local (CSV)

**Train a new model:**
```bash
python -u main.py -p train_model -s 2024-25 -m "ml_dev/models/best_lgbm_model_v3.pkl" -sm "local"
# Runs full training pipeline with hyperparameter tuning
# Output: trained model saved to specified path with metrics
```

**Generate predictions for specific date:**
```bash
python -u main.py -p get_predictions_stats_points -s 2024-25 -d "2025-04-13" -m "ml_dev/models/best_lgbm_model.pkl" -sm "local"
# -> ./databases/nba_points_predictions_df.csv
```

**Parameters:**
- `-p` process name (`train_model` | `get_predictions_stats_points` | `get_nba_players` | etc.)
- `-s` season (e.g., `2024-25`)
- `-d` date for predictions (format: `YYYY-MM-DD`)
- `-m` model path (local or `gs://...`)
- `-sm` save mode (`local` | `bq`)

### B) Docker

**Train model:**
```bash
docker run --rm \
  -e PROCESS="train_model" \
  -e SEASON="2024-25" \
  -e SAVE_MODE="local" \
  -e MODEL_PATH="ml_dev/models/best_lgbm_model.pkl" \
  nba_project_ml:latest
```

**Generate predictions:**
```bash
docker run --rm \
  -e PROCESS="get_predictions_stats_points" \
  -e SEASON="2024-25" \
  -e SEASON_TYPE="Regular Season" \
  -e DATE="2025-05-01" \
  -e SAVE_MODE="local" \
  -e MODEL_PATH="ml_dev/models/best_lgbm_model.pkl" \
  nba_project_ml:latest
```
### C) Cloud Run Job (BigQuery + proxy secret)

**Setup:**
```bash
# build & push (see cloudbuild.yaml) or:
PROJECT_ID="your-gcp-project"
REGION="us-central1"
ARTIFACT_REPO="nba-docker-repo"
IMAGE_NAME="nba_project"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${IMAGE_NAME}:latest"

BUCKET_MODELS="gs://your-bucket/models_trained"
MODEL_PATH="${BUCKET_MODELS}/best_lgbm_model.pkl"

# one-time proxy secret (DecoDO URL)
# gcloud secrets create PROXY_URL --data-file=<(echo -n "http://user:pass@host:port")
```

**Create Cloud Run Job for Training:**
```bash
gcloud run jobs create nba-training-job \
  --image "$IMAGE_URI" \
  --region "$REGION" \
  --set-env-vars=PROCESS=train_model,SEASON=2024-25,SAVE_MODE=bq,MODEL_PATH="${MODEL_PATH}" \
  --set-secrets=HTTPS_PROXY=PROXY_URL:latest,HTTP_PROXY=PROXY_URL:latest \
  --max-retries=1 --memory=2Gi --cpu=2 --task-timeout=3600s
```

**Create Cloud Run Job for Predictions:**
```bash
gcloud run jobs create nba-prediction-job \
  --image "$IMAGE_URI" \
  --region "$REGION" \
  --set-env-vars=SEASON=2024-25,SEASON_TYPE="Regular Season",DATE=2025-05-01,DAYS_NUMBER=1,SAVE_MODE=bq,MODEL_PATH="${MODEL_PATH}" \
  --set-secrets=HTTPS_PROXY=PROXY_URL:latest,HTTP_PROXY=PROXY_URL:latest \
  --max-retries=1 --memory=1Gi --cpu=1 --task-timeout=1800s \
|| gcloud run jobs update nba-prediction-job \
  --image "$IMAGE_URI" \
  --region "$REGION" \
  --set-env-vars=SEASON=2024-25,SEASON_TYPE="Regular Season",DATE=2025-05-01,DAYS_NUMBER=1,SAVE_MODE=bq,MODEL_PATH="${MODEL_PATH}" \
  --set-secrets=HTTPS_PROXY=PROXY_URL:latest,HTTP_PROXY=PROXY_URL:latest

# Execute ad-hoc
gcloud run jobs execute nba-prediction-job --region "$REGION"
gcloud run jobs execute nba-training-job --region "$REGION"
```

**Scheduling (Cloud Scheduler):**
```bash
# Daily predictions at 10 AM EST
gcloud scheduler jobs create http nba-daily-predictions \
  --location="$REGION" \
  --schedule="0 10 * * *" \
  --time-zone="America/New_York" \
  --uri="https://run.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/jobs/nba-prediction-job:run" \
  --http-method=POST \
  --oauth-service-account-email="your-service-account@$PROJECT_ID.iam.gserviceaccount.com"

# Weekly model retraining (Sunday at 2 AM)
gcloud scheduler jobs create http nba-weekly-training \
  --location="$REGION" \
  --schedule="0 2 * * 0" \
  --time-zone="America/New_York" \
  --uri="https://run.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/jobs/nba-training-job:run" \
  --http-method=POST \
  --oauth-service-account-email="your-service-account@$PROJECT_ID.iam.gserviceaccount.com"
```
## 🗺️ Modes & Outputs

- Run: local 🖥️ / docker 🐳 / cloud ☁️
- Save: SAVE_MODE=local → 📄 CSV | SAVE_MODE=bq → 🗄️ BigQuery

## 📄 License & Credits

- **Author**: Aurelien Pow ([@aurelpow](https://github.com/aurelpow))

## 🛣️ Next Improvements and Features
- **➕ More stats** (AST / TOV / REB)
- **🩺 Injury-aware predictions**
- **🌐 API Service**: Expose predictions via a REST API (FastAPI/Flask) for real-time applications.
- **📊 Dashboard**: Build an interactive dashboard (Plotly Dash or Power BI) to visualize predictions and model performance.