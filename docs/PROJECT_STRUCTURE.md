# Project Structure Documentation

## Overview
This project follows a clean, modular architecture with clear separation of concerns:
- **Data Collection**: Fetch NBA statistics from APIs
- **Training**: ML model training with unified pipeline
- **Prediction**: Generate forecasts using trained models
- **Common**: Shared utilities and helpers

---

## Directory Structure

```
NBA_project_ML/
├── src/
│   ├── data_collectors/      # Data fetching modules
│   │   ├── get_nba_players.py
│   │   ├── get_nba_teams.py
│   │   ├── get_nba_schedule.py
│   │   ├── get_nba_boxscore_basic.py
│   │   └── get_nba_advanced_boxscore.py
│   │
│   ├── training/              # Model training pipelines
│   │   ├── train.py           # Unified training module (NEW!)
│   │   ├── train_model.py     # Legacy points trainer (deprecated)
│   │   └── train_fantasy_model.py  # Legacy fantasy trainer (deprecated)
│   │
│   ├── predictors/            # Prediction/inference modules
│   │   ├── get_predictions_stats_points.py
│   │   └── get_predictions_fantasy_points.py
│   │
│   └── targets/               # Target variable calculators
│       └── fantasy_points.py
│
├── common/                    # Shared utilities (consolidated)
│   ├── constants.py           # Configuration constants
│   ├── io_utils.py            # File I/O operations
│   ├── utils.py               # General utilities
│   ├── parser.py              # CLI argument parsing
│   ├── singleton_meta.py      # Singleton metaclass
│   ├── feature_engineering.py # Feature transformation (moved from src/utils)
│   ├── model_utils.py         # ML model utilities (moved from src/utils)
│   └── training_helpers.py    # Training pipeline helpers (NEW!)
│
├── tests/                     # Unit and integration tests
├── databases/                 # Local data storage (CSV files)
├── ml_dev/models/             # Trained model files
├── main.py                    # Main entry point
└── README.md                  # Project documentation
```

---

## Key Improvements

### 1. **Unified Training Module** (`src/training/train.py`)
- Single entry point for all training tasks
- Supports multiple targets via `--target` parameter
- Configurable hyperparameter tuning via `--tune_params` flag
- Follows consistent **read → transform → persist** pattern

### 2. **Training Helpers** (`common/training_helpers.py`)
Extracted reusable functions:
- `read_training_data()`: Load required datasets
- `transform_data()`: Feature engineering pipeline
- `split_train_test()`: Time-based data splitting
- `train_and_evaluate()`: Model training and evaluation
- `persist_model()`: Save model artifacts

### 3. **Consolidated Common Module**
- Moved utilities from `src/utils/` to `common/`
- Eliminates redundancy

---

## Usage Examples

### Training Models

**Train Points Prediction (with tuning):**
```bash
python main.py --process train \
               --target points \
               --model_path ml_dev/models/points_model.pkl \
               --save_mode local \
               --tune_params
```

**Train Fantasy Points (default params):**
```bash
python main.py --process train \
               --target fantasy_points \
               --model_path ml_dev/models/fantasy_model.pkl \
               --save_mode local
```

### Predictions

```bash
python main.py --process get_predictions_fantasy_points \
               --date 2025-12-06 \
               --model_path ml_dev/models/fantasy_model.pkl \
               --save_mode local
```

---

## Design Pattern: Read-Transform-Persist

```python
class UnifiedModelTrainer:
    def read(self):
        """Load raw data"""
        
    def transform(self, data):
        """Apply feature engineering"""
        
    def persist(self, model, metrics):
        """Save trained model"""
        
    def run(self):
        """Orchestrate pipeline"""
```
