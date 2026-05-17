# CLAUDE.md

Guidance for Claude Code when working in **NBA_project_ML** — an end-to-end ML pipeline that ingests NBA data, trains LightGBM models, predicts player stats (points + TTFL fantasy points), and monitors prediction quality.

---

## 1. The one-minute mental model

```
NBA API ──> data_collectors ──> CSV / BigQuery
                                    │
                       feature_engineering (common/)
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
       training/train.py                     predictors/unified_predictor.py
       (UnifiedModelTrainer)                 (UnifiedPredictor) ──> predictions table
                                                                       │
                                                                       ▼
                                                    evaluators/post_evaluation.py
                                                    (PostGameEvaluator + Discord alerts)
```

Everything is dispatched through a single CLI: `python main.py -p <process> [...]`. There is **one** trainer class and **one** predictor class — both parameterized by `target` (`points` or `fantasy_points`). Adding a new target = adding an entry to `TARGET_CONFIGS` in [common/constants.py](common/constants.py), not a new file.

---

## 2. Stack & environment

- **Python**: 3.11 in Docker ([Dockerfile](Dockerfile)), 3.12 in the local `.venv`. Stick to 3.11-compatible syntax.
- **Core libs**: pandas ≥ 2.2, numpy ≥ 2.0, lightgbm ≥ 4.5, scikit-learn ≥ 1.6, `nba_api`, `google-cloud-bigquery`, `pdfplumber` (injury PDFs).
- **OS**: Windows 11. Shell is **PowerShell** — use `$env:VAR` not `$VAR`, `;` not `&&`. Bash exists via WSL/git-bash for the `scripts/*.sh` orchestrators.
- **Cloud target**: GCP — Cloud Run Jobs + BigQuery dataset `ml-nba-project.nba_dataset` (see [common/io_utils.py:36-37](common/io_utils.py#L36-L37)).
- **Timezone**: All audit timestamps use `Europe/Madrid`. Don't change this without a reason — it's load-bearing for the daily Cloud Scheduler runs.

---

## 3. Project layout (what lives where)

| Path | Purpose | Touch when… |
|------|---------|-------------|
| [main.py](main.py) | CLI dispatcher | adding a new `--process` value |
| [common/parser.py](common/parser.py) | argparse for the CLI | adding a new CLI flag |
| [common/constants.py](common/constants.py) | **All** target configs, thresholds, tier boundaries, availability maps | tuning ML behavior, adding a target |
| [common/raw_columns.py](common/raw_columns.py) | Canonical column-name constants | **never hardcode column names — import from here** |
| [common/io_utils.py](common/io_utils.py) | CSV ↔ BigQuery abstraction, idempotent writes | adding a new table / changing persistence |
| [common/feature_engineering.py](common/feature_engineering.py) | Rolling stats, opponent-position averages, encoding | feature changes (must mirror in training **and** inference) |
| [common/model_utils.py](common/model_utils.py), [common/training_helpers.py](common/training_helpers.py) | Train/eval/persist helpers | hyperparameter / split / metric changes |
| [src/data_collectors/](src/data_collectors/) | `nba_api` wrappers (players, teams, schedule, basic + advanced boxscore, injury report PDF) | data ingestion changes |
| [src/availability/](src/availability/) | Injury-report normalization → `play_probability` | injury / availability logic |
| [src/training/train.py](src/training/train.py) | `UnifiedModelTrainer` | training-pipeline changes |
| [src/predictors/unified_predictor.py](src/predictors/unified_predictor.py) | `UnifiedPredictor`, writes narrow-format predictions | inference changes |
| [src/evaluators/post_evaluation.py](src/evaluators/post_evaluation.py) | `PostGameEvaluator`, Discord alerts | monitoring / metric changes |
| [src/targets/fantasy_points.py](src/targets/fantasy_points.py) | TTFL formula | target definition changes |
| [tests/](tests/) | pytest suite — unittest style | any logic change |
| [scripts/](scripts/) | Bash orchestrators + GCP deploy scripts | Cloud Run / deploy changes |
| [docs/](docs/) | Long-form guides — keep in sync when behavior changes | |
| `databases/` | Local CSV outputs (gitignored data) | n/a — never commit data |
| `ml_dev/` | Notebooks + saved model `.pkl` artifacts | model exploration |

---

## 4. Conventions you must follow

### 4.1 Column names — use the constants
Never hardcode `"gameId"`, `"personId"`, `"game_date"`, etc. Import from [common/raw_columns.py](common/raw_columns.py):

```python
from common.raw_columns import game_id_col, person_id_col_alt, game_date_col
```

**Critical gotcha — camelCase vs snake_case for IDs and dates:**

| Concept | Boxscore / schedule / actuals | Predictions table |
|--------|---|---|
| Game ID | `game_id` (`game_id_col_alt`) | `gameId` (`game_id_col`) |
| Person ID | `person_id` (`person_id_col`) | `personId` (`person_id_col_alt`) |
| Game date | `game_date` (`game_date_col`) | `gameDate` (`game_date_col_alt`) |

When merging predictions with actuals, you'll usually merge on `person_id_col_alt` (camelCase) and convert the date format explicitly. See [post_evaluation.py:108-128](src/evaluators/post_evaluation.py#L108-L128) for the canonical pattern.

### 4.2 Predictions output is *narrow* format
Predictions are written as one row per `(gameId, personId, Measure)`. The `Measure` column encodes what the `Predictions` value means — defined in [common/constants.py](common/constants.py):

| `Measure` | Meaning |
|---|---|
| `1` (`MEASURE_PREDICTED_POINTS`) | Predicted points |
| `2` (`MEASURE_PREDICTED_FANTASY_POINTS`) | Predicted fantasy points (TTFL) |
| `3` (`MEASURE_POINTS_VOLATILITY`) | Points prediction volatility |
| `4` (`MEASURE_FANTASY_VOLATILITY`) | Fantasy points prediction volatility |

When filtering predictions, **always** filter by `Measure`. See [post_evaluation.py:89-92](src/evaluators/post_evaluation.py#L89-L92).

### 4.3 Adding a new target — only edit `TARGET_CONFIGS`
[common/constants.py](common/constants.py) has `TARGET_CONFIGS: dict[str, dict]` keyed by target name. Each entry holds `key_stats`, `categorical_cols`, `target_variable`, `rolling_windows`, `measure_prediction`, `measure_volatility`, `target_computer_fn` (string reference, lazily imported to avoid circular deps — keep it that way). The trainer/predictor read from this dict; do not duplicate logic in either class.

### 4.4 Singletons
`UnifiedPredictor` and `PostGameEvaluator` use `SingletonMeta` ([common/singleton_meta.py](common/singleton_meta.py)). In tests, reset between cases:
```python
SingletonMeta._instances.pop(PostGameEvaluator, None)
```
(See the helper in [tests/test_post_evaluation.py:17-20](tests/test_post_evaluation.py#L17-L20).)

### 4.5 Persistence — pick the right helper
- `save_database(df, table, mode, write_disposition=..., skip_dedup=...)` — generic writer. If `gameId` is in the df and `write_disposition="WRITE_APPEND"` and `skip_dedup=False`, it does **delete-by-gameId then append** (idempotent at game level).
- `save_predictions(df, table, mode)` — composite-key idempotency on `(gameId, personId, Measure)`. **Use this for the predictions table.**
- `delete_rows_by_evaluation_date(table, date)` — for evaluation tables, the evaluator deletes first and writes with `skip_dedup=True` (see [post_evaluation.py:316-329](src/evaluators/post_evaluation.py#L316-L329)).

Don't write your own idempotency logic — extend one of these.

### 4.6 `save_mode`: `"local"` or `"bq"`
Every persistence-touching class accepts `save_mode`. Local writes go to `databases/<table>.csv`; bq writes to `ml-nba-project.nba_dataset.<table>`. Both paths must keep working — test changes with `save_mode="local"` first.

### 4.7 Training/inference feature parity
Training features and inference features come from the **same** functions in [common/feature_engineering.py](common/feature_engineering.py) (`create_historical_features`, `compute_rolling_stats`, `normalize_features`, `encode_categorical_features`, `get_feature_cols`). If you change one, you change both — otherwise the model sees a different feature space at inference and predictions silently degrade. The encoder is saved with the model artifact for exactly this reason.

### 4.8 LightGBM objectives differ by target
[src/training/train.py:30-52](src/training/train.py#L30-L52) — `points` uses regression defaults, `fantasy_points` uses **quantile** objective (`alpha=0.75`) and pinball loss. Don't paste hyperparams across targets.

---

## 5. Running things

### 5.1 Single processes (PowerShell)
```powershell
# Train
python main.py -p train -t fantasy_points -m "ml_dev/models/fp_model.pkl" -sm local --tune_params false

# Predict for a specific date
python main.py -p get_predictions_fantasy_points -d "2025-12-05" -m "ml_dev/models/fp_model.pkl" -sm local

# Post-game evaluation (defaults to yesterday if -d omitted)
python main.py -p post_evaluation -d "2025-12-04" -sm local
```

Valid `-p` values: `get_nba_players`, `get_nba_teams`, `get_nba_schedule`, `get_nba_boxscore_basic`, `get_nba_advanced_boxscore`, `get_injury_report`, `compute_availability`, `train`, `get_predictions_stats_points`, `get_predictions_fantasy_points`, `post_evaluation`. The full list is enforced in [main.py:52-64](main.py#L52-L64).

### 5.2 Full daily pipeline
[scripts/run_all.sh](scripts/run_all.sh) chains everything in order and is the **container ENTRYPOINT**. It's the source of truth for "what runs in production every day" — read it before changing run order.

### 5.3 Tests
```powershell
pytest -q                                  # all tests
pytest tests/test_post_evaluation.py -q    # one file
pytest tests/test_post_evaluation.py::TestAssignTier -q
```
- **Framework**: unittest classes run by pytest. Match the style; don't introduce pytest-fixture-only patterns mid-file.
- **Mocks**: heavy use of `unittest.mock` for I/O (`load_data`, `save_database`, etc.). When you add a new write helper, the tests that mocked the old one will need updating.
- **Singletons**: reset in `setUp` (see §4.4).
- No mocks for the fantasy-points formula itself — it's a pure function and tests use real arithmetic.

### 5.4 Docker
```powershell
docker build -t nba-pipeline:latest .
docker run --rm -e SEASON=2024-25 -e DATE=2025-12-05 -e SAVE_MODE=local nba-pipeline:latest
```
Entry is [scripts/run_all.sh](scripts/run_all.sh); env vars listed at its top are the public interface (`SEASON`, `DATE`, `EVAL_DATE`, `SAVE_MODE`, `MODEL_PATH`, `TARGETS`, `TUNE_HYPERPARAMETERS`, `NBA_PROXY_USER`/`NBA_PROXY_PASS`, `DISCORD_WEBHOOK_URL`).

### 5.5 Cloud Run
Deploy via [scripts/deploy_develop.sh](scripts/deploy_develop.sh) / [scripts/deploy_production.sh](scripts/deploy_production.sh). GCP config is in `scripts/gcp_config.sh` (gitignored). CI/CD is local Jenkins ([jenkins/](jenkins/)) triggered on `dev`/`master` pushes.

---

## 6. Things that have burned us — read before changing

1. **NBA API rate limits.** Calls go through a paid DecoDO proxy in cloud (`HTTP_PROXY`/`HTTPS_PROXY` from Secret Manager). `nba_api_timeout=60s`, `max_retries=3` — see [common/constants.py:6-10](common/constants.py#L6-L10). Don't lower the timeout.
2. **Date format mismatch.** Predictions store `gameDate` as ISO string; boxscore stores `game_date` as a date. Compare via `pd.to_datetime(...).dt.strftime("%Y-%m-%d") == self.date`. See [post_evaluation.py:73-75](src/evaluators/post_evaluation.py#L73-L75).
3. **Minutes filtering.** Use `parse_minutes()` from [common/utils.py](common/utils.py) — the raw `minutes` column is `"MM:SS"`, not a number.
4. **Idempotency in evaluation writes** (commit `6931c70`): delete-by-`evaluation_date` **before** append, and pass `skip_dedup=True` to `save_database`, otherwise the generic delete-by-`gameId` path runs and deletes the wrong rows.
5. **Encoding on Windows.** `main.py` force-reconfigures stdout/stderr to UTF-8 because emoji prints crash `cp1252`. Don't remove the `_force_utf8_stream` block.
6. **Confidence tiers gate alerts.** `Green ≥ 0.60`, `Blue ≥ 0.30`, else `Orange`. Alert thresholds in `EVAL_MAE_THRESHOLDS` ([constants.py:142-146](common/constants.py#L142-L146)). If you change tier boundaries, also update the test cases that assert at the boundaries.
7. **Don't commit `databases/*.csv`** or `scripts/gcp_config.sh` — both are gitignored for a reason (data + credentials).

---

## 7. Style

- Type hints on function signatures (the codebase is consistent about this).
- Module-level `logger = logging.getLogger(__name__)`, not `print()` in library code. CLI scripts (`main.py`, `run_all.sh`) print for human-readable progress.
- Docstrings: short summary + `Args:` / `Returns:` blocks. Match the existing style in [src/evaluators/post_evaluation.py](src/evaluators/post_evaluation.py).
- Don't add files for one-off scripts — extend the CLI dispatcher or the relevant helper module.
- Don't break the single-trainer / single-predictor architecture — if you find yourself wanting a second predictor class, add a `TARGET_CONFIGS` entry instead.

---

## 8. Useful docs in-repo

- [docs/TRAINING_GUIDE.md](docs/TRAINING_GUIDE.md) — training pipeline details
- [docs/fantasy_points_model.md](docs/fantasy_points_model.md) — TTFL target & quantile model
- [docs/CLOUD_JOBS_GUIDE.md](docs/CLOUD_JOBS_GUIDE.md), [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md), [docs/CLOUD_SETUP_QUICKSTART.md](docs/CLOUD_SETUP_QUICKSTART.md) — GCP setup
- [docs/JENKINS_SETUP.md](docs/JENKINS_SETUP.md) — CI/CD
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) — deeper module-by-module breakdown
