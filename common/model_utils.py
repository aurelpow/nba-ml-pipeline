from copyreg import pickle
import pandas as pd
import numpy as np
import joblib
import os
import logging
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from lightgbm import LGBMRegressor
from google.cloud import storage
import tempfile

from common.io_utils import _parse_gcs_uri

logger = logging.getLogger(__name__)

def find_best_split(df: pd.DataFrame, target: str, 
                    feature_cols: List[str], 
                    test_sizes: List[float] = [0.15, 0.20, 0.25]) -> Dict[str, Any]:
    """
    Find optimal train/test split based on time-based evaluation.
    
    Args:
        df: preprocessed DataFrame with game_date column
        target: target variable name
        feature_cols: list of feature column names
        test_sizes: candidate test set sizes to evaluate
        
    Returns:
        dict with keys: best_test_size, best_split_date, best_r2, best_rmse
    """
    # Initialize tracking variables
    best_size = None
    best_r2 = -np.inf
    best_rmse = np.inf
    best_split_date = None
    
    # Unique sorted game dates for splitting
    unique_dates = np.sort(df['game_date'].unique())
    
    # Find best split
    logger.info(f"🔍 Searching for best split across {len(test_sizes)} test sizes...")
    for ts in test_sizes:
        idx = int((1 - ts) * len(unique_dates))
        split_date = unique_dates[idx]
        
        train_df = df[df['game_date'] < split_date]
        test_df = df[df['game_date'] >= split_date]
        
        X_tr, y_tr = train_df[feature_cols], train_df[target]
        X_te, y_te = test_df[feature_cols], test_df[target]
        
        # Clean data
        X_tr = X_tr.replace([np.inf, -np.inf], np.nan).fillna(0)
        X_te = X_te.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Quick baseline model for split evaluation
        model = LGBMRegressor(objective='regression', n_estimators=200, verbose=-1)
        model.fit(X_tr, y_tr)
        
        y_pred = model.predict(X_te)
        rmse = np.sqrt(mean_squared_error(y_te, y_pred))
        r2 = r2_score(y_te, y_pred)
        
        logger.info(f"  test_size={ts:.2f} → R²={r2:.4f}, RMSE={rmse:.4f}")
        
        if r2 > best_r2:
            best_r2 = r2
            best_rmse = rmse
            best_size = ts
            best_split_date = split_date
    
    logger.info(f"✅ Best split: test_size={best_size} (R²={best_r2:.4f})")
    
    return {
        'best_test_size': best_size,
        'best_split_date': best_split_date,
        'best_r2': best_r2,
        'best_rmse': best_rmse
    }

def tune_hyperparameters(X_train: pd.DataFrame, y_train: pd.Series,
                         n_iter: int = 20, cv_splits: int = 3) -> Dict[str, Any]:
    """
    Tune LightGBM hyperparameters using RandomizedSearchCV with time-series CV.
    
    Args:
        X_train: training features
        y_train: training target
        n_iter: number of random search iterations
        cv_splits: number of time-series cross-validation splits
        
    Returns:
        dict with best hyperparameters
    """
    logger.info(f"🎯 Tuning hyperparameters ({n_iter} iterations, {cv_splits}-fold TimeSeriesCV)...")
    
    param_distributions = {
        'n_estimators': [ 2000, 2200, 2500],
        'learning_rate': [ 0.003, 0.004, 0.005],
        'max_depth': [8, 9, 12],
        'num_leaves': [80, 90, 100],
        'min_child_samples': [ 40, 50],
        'subsample': [ 0.8, 1.0],
        'colsample_bytree': [0.6],
        'reg_alpha': [ 0.8, 1.0],
        'reg_lambda': [ 0.8, 1.0]
    }
    
    # Time-series aware cross-validation
    tscv = TimeSeriesSplit(n_splits=cv_splits)

    lgbm = LGBMRegressor(objective='regression', verbose=-1, random_state=42)

    random_search = RandomizedSearchCV(
        estimator=lgbm,
        param_distributions=param_distributions,
        n_iter=n_iter,
        cv=tscv,
        scoring='neg_root_mean_squared_error',
        n_jobs=-1,
        random_state=42,
        verbose=1
    )
    
    random_search.fit(X_train, y_train)

    logger.info(f"✅ Best CV R²: {-random_search.best_score_:.4f}")
    logger.info(f"📋 Best params: {random_search.best_params_}")
    
    return random_search.best_params_

def train_model(X_train: pd.DataFrame, y_train: pd.Series,
                best_params: Dict[str, Any]) -> LGBMRegressor:
    """
    Train the final model with best hyperparameters.
    
    Args:
        X_train: training features
        y_train: training target
        best_params: optimized hyperparameters
        
    Returns:
        trained LGBMRegressor model
    """
    logger.info(f"🚀 Training final model with best params...")
    
    model = LGBMRegressor(**best_params, objective='regression', verbose=-1)
    model.fit(X_train, y_train)
    
    # Log feature importance
    importance = pd.DataFrame({
        'feature': X_train.columns,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    logger.info("🔝 Top 20 Features:")
    for _, row in importance.head(20).iterrows():
        logger.info(f"   {row['feature']}: {row['importance']}")
    
    return model

def evaluate_model(model: LGBMRegressor, 
                   X_test: pd.DataFrame, y_test: pd.Series,
                   X_train: pd.DataFrame, y_train: pd.Series) -> Dict[str, Any]:
    """
    Comprehensive model evaluation on train and test sets.
    
    Args:
        model: trained model
        X_test: test features
        y_test: test target
        X_train: train features (for overfitting check)
        y_train: train target
        
    Returns:
        dict with train/test metrics
    """
    logger.info(f"📊 Evaluating model performance...")
    
    # Test set predictions
    y_pred_test = model.predict(X_test)
    test_r2 = r2_score(y_test, y_pred_test)
    test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
    test_mae = mean_absolute_error(y_test, y_pred_test)
    
    # Train set predictions (overfitting check)
    y_pred_train = model.predict(X_train)
    train_r2 = r2_score(y_train, y_pred_train)
    train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
    
    metrics = {
        'test_r2': test_r2,
        'test_rmse': test_rmse,
        'test_mae': test_mae,
        'train_r2': train_r2,
        'train_rmse': train_rmse,
        'test_samples': len(X_test),
        'train_samples': len(X_train),
        'overfitting_gap': train_r2 - test_r2
    }
    
    logger.info(f"  Test  → R²={test_r2:.4f}, RMSE={test_rmse:.4f}, MAE={test_mae:.4f}")
    logger.info(f"  Train → R²={train_r2:.4f}, RMSE={train_rmse:.4f}")
    logger.info(f"  Overfit Gap: {metrics['overfitting_gap']:.4f}")
    
    return metrics

def save_model_artifact(model: Any, metrics: Dict[str, Any], 
                        feature_cols: List[str], 
                        target: str,
                        key_stats: Dict[str, str],
                        categorical_cols: List[str],
                        filepath: str,
                        save_mode: str = "local",
                        scaler: Any = None) -> None:
    """
    Save trained model, scaler, feature columns, and metrics to disk or GCS.
    
    Args:
        model: trained model to save
        metrics: evaluation metrics to save
        feature_cols: list of feature columns
        target: target variable name
        key_stats: dictionary of key stats
        categorical_cols: list of categorical columns
        filepath: path where to save the model artifact
        save_mode: save mode ('local' or 'bq')
        scaler: optional scaler object
    """
    # Define full filepath
    full_path = os.path.join(filepath, f"{target}_model.pkl")
    logger.info(f"Saving model artifact to {full_path}...")

    # Package everything needed for prediction
    artifact = {
        'model': model,
        'scaler': scaler,
        'feature_cols': feature_cols,
        'metrics': metrics,
        'target': target,
        'key_stats': key_stats,
        'categorical_cols': categorical_cols,
        'training_date': datetime.now().isoformat()
    }

    if save_mode == "bq":
        # Save to GCS bucket
        bucket_name, blob_name = full_path.removeprefix("gs://").split("/", 1)
        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp:
            joblib.dump(artifact, tmp.name)
            storage.Client().bucket(bucket_name).blob(blob_name).upload_from_filename(tmp.name)
    elif save_mode == "local":
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        joblib.dump(artifact, full_path)
    else:
        raise ValueError(f"Unsupported save_mode: {save_mode}")
        
    logger.info(f"✅ Model saved successfully")


def load_model_artifact(model_path: str, target: str, mode: str) -> Any:
    """
    Load a model artifact from either local disk or GCS.

    Args:
        model_path: local path or 'gs://bucket/obj' (can be directory or full .pkl path)
        target: target variable name (e.g., 'points', 'fantasy_points')
        mode: 'local' or 'bq' (if 'bq' and path is gs://, downloads from GCS)

    Returns:
        The trained model object
    """
    # If model_path is a directory, append the target model filename
    if not model_path.endswith('.pkl'):
        model_path = os.path.join(model_path, f'{target}_model.pkl')
    
    logger.info(f"Loading model artifact from {model_path}...")
    
    if mode == 'local':
        # Load from local file system
        logger.info(f"Loading model from local path: {model_path}")
        artifact = joblib.load(model_path)
        
    elif mode == 'bq':
        # Load from GCS
        if not model_path.startswith('gs://'):
            raise ValueError(f"GCS path must start with 'gs://': {model_path}")
        
        bucket_name, blob_path = _parse_gcs_uri(model_path)
        logger.info(f"Loading model from GCS: bucket={bucket_name}, path={blob_path}")
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        
        # Download to temporary file and load with joblib
        with tempfile.NamedTemporaryFile(suffix='.pkl', delete=False) as tmp:
            blob.download_to_filename(tmp.name)
            artifact = joblib.load(tmp.name)
            os.unlink(tmp.name)  # Clean up temp file
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'local' or 'bq'")
    
    # Extract model from artifact dictionary
    if isinstance(artifact, dict):
        model = artifact.get('model')
        if model is None:
            raise ValueError(f"Model artifact missing 'model' key. Found keys: {list(artifact.keys())}")
        logger.info(f"✅ Model loaded successfully from {model_path}")
        return model
    else:
        # Artifact is already a model object
        logger.info(f"✅ Model loaded successfully from {model_path}")
        return artifact