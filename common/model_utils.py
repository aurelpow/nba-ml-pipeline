from copyreg import pickle
import pandas as pd
import numpy as np
import joblib
import os
import logging
from typing import Dict, List, Any, Tuple, Optional, Union
from datetime import datetime
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from lightgbm import LGBMRegressor
from google.cloud import storage
import tempfile

from sklearn.preprocessing import OneHotEncoder

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
        
        y_pred = np.asarray(model.predict(X_te)).ravel()
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
                         n_iter: int = 20, cv_splits: int = 3,
                         alpha: Optional[float] = None) -> Dict[str, Any]:
    """
    Tune LightGBM hyperparameters using RandomizedSearchCV with time-series CV.

    Args:
        X_train: training features
        y_train: training target
        n_iter: number of random search iterations
        cv_splits: number of time-series cross-validation splits
        alpha: quantile level (e.g. 0.75). When provided the base estimator uses
               objective='quantile' and tuning is scored with pinball loss.
               When None, objective='regression' and RMSE scoring are used.

    Returns:
        dict with best hyperparameters (objective/alpha are NOT included —
        they are fixed constants, not search dimensions)
    """
    logger.info(f"🎯 Tuning hyperparameters ({n_iter} iterations, {cv_splits}-fold TimeSeriesCV)...")

    if alpha is not None:
        # Quantile regression — piecewise linear loss, needs faster/shallower tuning
        param_distributions = {
            'n_estimators':       [400, 600, 800, 1000, 1200],
            'learning_rate':      [0.01, 0.02, 0.03, 0.05],
            'max_depth':          [5, 6, 7, 8],
            'num_leaves':         [31, 40, 50, 63],
            'min_child_samples':  [30, 40, 50],
            'subsample':          [0.7, 0.8, 0.9],
            'colsample_bytree':   [0.5, 0.6, 0.7],
            'reg_alpha':          [0.1, 0.5, 1.0],
            'reg_lambda':         [0.5, 1.0, 2.0],
        }
    else:
        # MSE regression — smooth loss tolerates slower/deeper tuning
        param_distributions = {
            'n_estimators':       [800, 1200, 1600, 2000],
            'learning_rate':      [0.005, 0.01, 0.02, 0.05],
            'max_depth':          [6, 7, 8, 9],
            'num_leaves':         [50, 63, 80, 100],
            'min_child_samples':  [30, 40, 50],
            'subsample':          [0.7, 0.8, 1.0],
            'colsample_bytree':   [0.6, 0.7],
            'reg_alpha':          [0.0, 0.5, 1.0],
            'reg_lambda':         [0.5, 1.0],
        }

    # Base estimator: fix objective/alpha so the tuner only searches the grid above.
    # Typed as Any because LightGBM's type stubs do not expose BaseEstimator to Pylance.
    lgbm: Any
    if alpha is not None:
        lgbm = LGBMRegressor(objective='quantile', alpha=alpha, verbose=-1, random_state=42)
        # Pinball loss is the correct scoring metric for quantile models
        def _pinball(y_true, y_pred):
            e = np.asarray(y_true) - np.asarray(y_pred)
            return float(np.where(e >= 0, alpha * e, (alpha - 1) * e).mean())
        from sklearn.metrics import make_scorer
        scoring = make_scorer(_pinball, greater_is_better=False)
        logger.info(f"  Using quantile objective (α={alpha}) with pinball scoring")
    else:
        lgbm = LGBMRegressor(objective='regression', verbose=-1, random_state=42)
        scoring = 'neg_root_mean_squared_error'
        logger.info("  Using regression objective with RMSE scoring")

    # Time-series aware cross-validation
    tscv = TimeSeriesSplit(n_splits=cv_splits)

    random_search = RandomizedSearchCV(
        estimator=lgbm,
        param_distributions=param_distributions,
        n_iter=n_iter,
        cv=tscv,
        scoring=scoring,
        n_jobs=-1,
        random_state=42,
        verbose=1,
    )

    random_search.fit(X_train, y_train)

    logger.info(f"✅ Best CV score: {-random_search.best_score_:.4f}")
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
    
    # objective and verbose are carried by best_params when present (e.g. quantile);
    # only inject defaults when the caller did not supply them.
    params = {'objective': 'regression', 'verbose': -1}
    params.update(best_params)
    model = LGBMRegressor(**params)
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
    y_pred_test = np.asarray(model.predict(X_test)).ravel()
    test_r2 = r2_score(y_test, y_pred_test)
    test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
    test_mae = mean_absolute_error(y_test, y_pred_test)
    
    # Train set predictions (overfitting check)
    y_pred_train = np.asarray(model.predict(X_train)).ravel()
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
        'overfitting_gap': train_r2 - test_r2,
    }

    logger.info(f"  Test  → R²={test_r2:.4f}, RMSE={test_rmse:.4f}, MAE={test_mae:.4f}")
    logger.info(f"  Train → R²={train_r2:.4f}, RMSE={train_rmse:.4f}")
    logger.info(f"  Overfit Gap: {metrics['overfitting_gap']:.4f}")

    # Pinball loss — the correct metric for quantile models.
    # For regression models this is None (MAE/RMSE remain the primary metrics).
    alpha = getattr(model, 'alpha', None)
    if alpha is not None:
        def _pinball(y_true: Union[pd.Series, np.ndarray],
                     y_pred: Union[pd.Series, np.ndarray]) -> float:
            e = np.asarray(y_true) - np.asarray(y_pred)
            return float(np.where(e >= 0, alpha * e, (alpha - 1) * e).mean())

        metrics['test_pinball']  = round(_pinball(y_test,  y_pred_test),  4)
        metrics['train_pinball'] = round(_pinball(y_train, y_pred_train), 4)
        logger.info(f"  Pinball(α={alpha}) → test={metrics['test_pinball']:.4f}, "
                    f"train={metrics['train_pinball']:.4f}")
    else:
        metrics['test_pinball']  = None
        metrics['train_pinball'] = None

    return metrics

def save_model_artifact(model: Any, metrics: Dict[str, Any], 
                        feature_cols: List[str], 
                        target: str,
                        key_stats: Dict[str, str],
                        categorical_cols: List[str],
                        filepath: str,
                        save_mode: str = "local",
                        scaler: Any = None, 
                        encoder: OneHotEncoder | None = None) -> None:
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
        encoder: optional OneHotEncoder object
    """
    # Define full filepath
    full_path = os.path.join(filepath, f"{target}_model.pkl")
    logger.info(f"Saving model artifact to {full_path}...")

    # Package everything needed for prediction
    artifact = {
        'model': model,
        'encoder': encoder,
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
    
    # Normalise legacy artifacts (bare model objects saved without a dict wrapper)
    if not isinstance(artifact, dict):
        artifact = {'model': artifact}

    if artifact.get('model') is None:
        raise ValueError(
            f"Artifact missing 'model' key. Found keys: {list(artifact.keys())}"
        )

    logger.info(f"✅ Artifact loaded successfully from {model_path}")
    return artifact