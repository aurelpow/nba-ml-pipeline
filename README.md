# NBA Player Predictions - End to End Pipeline (Docker +Google Cloud )

*A complete, modular pipeline for fetching, processing, modeling, and predicting NBA player performance. 
Whether you’re exploring the data in a notebook or running daily inference in production, this repo has you covered.*

I built this because I love **basketball + data🏀📈**. 

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
### 🧭 How to Train & Export
1. Open the notebook `ml_dev/notebooks/NBA_Players_Points_Prediction_ML.ipynb`
2. Run training cells → evaluate → persist the **best** model:
   - Local:
     ```python
     joblib.dump(model, "ml_dev/models/best_lgbm_model.pkl")
     ```
   - GCS: Copy and paste the model to a google cloud bucket

---
## 🧰 Data Prep & Inference
**Goal**: prepare the inputs to the exact feature schema the trained model expects, then generate player-game predictions.
Core utilities live in `common/`:
- `parser.py`, `utils.py`, `io_utils.py`, `constants.py`
- Tasks: schema normalization, joins (players/teams ↔ boxscores), type casting, dedup, and quality checks.

### Inference ([src/get_predictions_stats_points.py](src/get_predictions_stats_points.py))
1) **Load schedule** for `DATE … DATE + DAYS_NUMBER` (`get_nba_schedule.py`).
2) Expand to **player-game** rows for active rosters.
3) **Load model** from `MODEL_PATH` (local path or `gs://…`):
   the loader downloads from GCS at runtime if needed.
4) Build the **same feature set** used at train time for each player-game.
5) **Predict** points (PTS). Optionally compute fantasy/scoring aggregates.
6) **Persist (by `SAVE_MODE`)**
   - `local` → `predictions_${DATE}.csv`
   - `bq`    → BigQuery table (configured in `io_utils.py` / `constants.py`)

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
│   └── get_predictions_stats_points.py
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
| `DATE` | ✅ | `2025-05-01` | Start date for inference |
| `DAYS_NUMBER` | ❕ | `1` | Days ahead |
| `SAVE_MODE` | ❕ | `local` \| `bq` | CSV vs BigQuery |
| `MODEL_PATH` | ❕ | `ml_dev/models/best_lgbm_model.pkl` \| `gs://…/best_lgbm_model.pkl` | Local or GCS |
| `HTTP_PROXY` / `HTTPS_PROXY` | ❕ | secret | Use in cloud to avoid API timeouts |

> If `MODEL_PATH` starts with `gs://`, the app downloads the file at runtime (see `common/io_utils.py::load_model()`).

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
To run a specific process 
```bash
python -u main.py -p get_predictions_stats_points -s 2024-25 -d "2025-04-13" -m "ml_dev/models/best_lgbm_model.pkl" -sm "local"
# -> ./databases/nba_points_predictions_df.csv
```
>-p process, -s season, -d date, -m model path, -sm save mode.

### B) Docker
```bash
docker run --rm \
  -e SEASON="2024-25" -e SEASON_TYPE="Regular Season" \
  -e DATE="2025-05-01" \
  -e SAVE_MODE="local" \
  -e MODEL_PATH="ml_dev/models/best_lgbm_model.pkl" \
  nba_project_ml:latest
```
### C) Cloud Run Job (BigQuery + proxy secret)
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

# Create or update the Cloud Run Job with env vars + secrets
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
```
## 🗺️ Modes & Outputs

- Run: local 🖥️ / docker 🐳 / cloud ☁️
- Save: SAVE_MODE=local → 📄 CSV | SAVE_MODE=bq → 🗄️ BigQuery

## 📄 License & Credits

- **Author**: Aurelien Pow ([@aurelpow](https://github.com/aurelpow))

## 🛣️ Next Improvements and Features
- **🔁 Automated Retraining**: Add a scheduled job to retrain the model weekly or monthly when performance degrades.
- **➕ More stats** (AST / TOV / REB)
- **🩺 Injury-aware predictions**
- **🌐 API Service**: Expose predictions via a REST API (FastAPI/Flask) for real-time applications.
- **📊 Dashboard**: Build an interactive dashboard (Plotly Dash or Power BI) to visualize predictions and model performance.