# Unified Training - Quick Reference

## Command Syntax

```bash
python main.py --process train \
               --target {points|fantasy_points} \
               --model_path <path> \
               --save_mode {local|bq} \
               --tune_params {true|false}
```

## Parameters

| Parameter | Options | Default | Description |
|-----------|---------|---------|-------------|
| `--target` | `points`, `fantasy_points` | `points` | What to predict |
| `--save_mode` | `local`, `bq` | `bq` | Where to save model |
| `--tune_params` | `true`, `false` | `false` | Enable hyperparameter tuning |
| `--model_path` | any path | required | Model save location |

## Examples

### 1. Train Fantasy Points (Fast - No Tuning)
```bash
python main.py --process train \
               --target fantasy_points \
               --model_path ml_dev/models/fantasy_model.pkl \
               --save_mode local \
               --tune_params false
```

### 2. Train Fantasy Points (Optimized - With Tuning)
```bash
python main.py --process train \
               --target fantasy_points \
               --model_path ml_dev/models/fantasy_model.pkl \
               --save_mode local \
               --tune_params true
```

### 3. Train Points Prediction (Fast)
```bash
python main.py --process train \
               --target points \
               --model_path ml_dev/models/points_model.pkl \
               --save_mode local \
               --tune_params false
```

### 4. Train Points Prediction (With Tuning)
```bash
python main.py --process train \
               --target points \
               --model_path ml_dev/models/points_model.pkl \
               --save_mode local \
               --tune_params true
```

### 5. Save to Google Cloud Storage
```bash
python main.py --process train \
               --target fantasy_points \
               --model_path gs://my-bucket/models/fantasy_model.pkl \
               --save_mode bq \
               --tune_params false
```

## Default Hyperparameters

### Points
```python
{
    'n_estimators': 200,
    'learning_rate': 0.1,
    'max_depth': 7,
    'num_leaves': 31,
    'subsample': 0.8,
    'colsample_bytree': 0.8
}
```

### Fantasy Points
```python
{
    'n_estimators': 1500,
    'learning_rate': 0.005,
    'max_depth': -1,
    'num_leaves': 63,
    'subsample': 0.8,
    'colsample_bytree': 0.6,
    'reg_alpha': 0,
    'reg_lambda': 0,
    'min_child_samples': 50
}
```

## Training Time Estimates

| Configuration | Approximate Time |
|--------------|-----------------|
| `tune_params=false` | 2-5 minutes |
| `tune_params=true` (20 iterations) | 30-60 minutes |

## Output

Training produces:
- Trained model (`.pkl` file)
- Model metadata (features, metrics, hyperparameters)
- Console logs with performance metrics

Example output:
```
✅ Best split: test_size=0.2 (R²=0.6510)
🎯 Tuning hyperparameters (20 iterations, 3-fold TimeSeriesCV)...
✅ Best CV R²: 0.7461
📊 Evaluating model performance...
  Test  → R²=0.6266, RMSE=9.1163, MAE=6.2671
  Train → R²=0.7461, RMSE=7.5748
✅ Model saved successfully
```
