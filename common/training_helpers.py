"""Helper functions for training pipelines - implements read/transform/persist pattern."""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any, Optional

from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName, MetricsFileName, load_data, save_database
from common.feature_engineering import (
    merge_data, preprocess_data, create_historical_features,
    normalize_features, compute_rolling_stats, encode_categorical_features,
    get_feature_cols
)
from common.model_utils import (
    find_best_split, tune_hyperparameters, train_model,
    evaluate_model, save_model_artifact
)

logger = logging.getLogger(__name__)


def read_training_data(save_mode: str = "local") -> Dict[str, pd.DataFrame]:
    """
    Read all required data for training.
    
    Args:
        save_mode: Data source mode ('local' or 'bq')
        
    Returns:
        Dictionary with boxscore, advanced, and players dataframes
    """
    logger.info("Loading training data...")
    box = load_data(BoxscoreFileName, mode=save_mode)
    adv = load_data(AdvancedBoxscoreFileName, mode=save_mode)
    players = load_data(PlayersFileName, mode=save_mode)
    
    return {
        BoxscoreFileName: box,
        AdvancedBoxscoreFileName: adv,
        PlayersFileName: players
    }


def transform_data(
    data_map: Dict[str, pd.DataFrame],
    target_variable: str,
    key_stats: Dict[str, str],
    categorical_cols: List[str],
    rolling_windows: List[int],
    target_computer_fn=None
) -> Tuple[pd.DataFrame, List[str], List[str], Any]:
    """
    Transform raw data into ML-ready features.
    
    Args:
        data_map: Dictionary with raw dataframes
        target_variable: Name of target column ('points' or 'fantasy_points')
        key_stats: Dictionary of statistics to use as features
        categorical_cols: List of categorical columns
        rolling_windows: List of rolling window sizes
        target_computer_fn: Optional function to compute custom target
        
    Returns:
        Tuple of (transformed_df, feature_columns, encoded_columns, encoder)
    """
    logger.info("Transforming data...")
    
    # 1. Merge & Preprocess
    logger.info("Merging and preprocessing data...")
    df = merge_data(
        data_map[BoxscoreFileName],
        data_map[AdvancedBoxscoreFileName],
        data_map[PlayersFileName]
    )
    df = preprocess_data(df)
    
    # 2. Compute target if custom function provided
    if target_computer_fn:
        logger.info(f"Computing {target_variable}...")
        df = target_computer_fn(df)
    
    # 3. Feature Engineering
    logger.info("Engineering features...")
    df = create_historical_features(df, target_col=target_variable)
    df = normalize_features(df, key_stats)
    df = compute_rolling_stats(df, key_stats, windows=rolling_windows)
    
    # 4. Encode Categoricals
    logger.info("Encoding categorical features...")
    df, encoded_cols, encoder = encode_categorical_features(df, categorical_cols)
    
    # 5. Define Feature Columns
    feature_cols = get_feature_cols(key_stats, rolling_periods=rolling_windows)
    
    # Add rest_days if available (fantasy models use it)
    if 'rest_days' in df.columns and 'rest_days' not in feature_cols:
        feature_cols.append('rest_days')
    
    feature_cols.extend(encoded_cols)
    logger.info(f"Total features: {len(feature_cols)}")
    
    return df, feature_cols, encoded_cols, encoder 


def split_train_test(
    df: pd.DataFrame,
    target_variable: str,
    feature_cols: List[str]
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, Dict[str, Any]]:
    """
    Perform time-based train/test split.
    
    Args:
        df: Transformed dataframe
        target_variable: Name of target column
        feature_cols: List of feature column names
        
    Returns:
        Tuple of (X_train, X_test, y_train, y_test, split_info)
    """
    logger.info("Performing train/test split...")
    split_info = find_best_split(df, target_variable, feature_cols)
    
    # Create final split
    unique_dates = np.sort(df['game_date'].unique())
    idx = int((1 - split_info['best_test_size']) * len(unique_dates))
    split_date = unique_dates[idx]
    
    train_df = df[df['game_date'] < split_date]
    test_df = df[df['game_date'] >= split_date]
    
    X_train = train_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    y_train = train_df[target_variable]
    X_test = test_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
    y_test = test_df[target_variable]
    
    split_info['split_date'] = split_date
    
    return X_train, X_test, y_train, y_test, split_info


def train_and_evaluate(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    tune_params: bool = True,
    n_iter: int = 20,
    default_params: Optional[Dict[str, Any]] = None
) -> Tuple[Any, Dict[str, Any]]:
    """
    Train model with optional hyperparameter tuning.
    
    Args:
        X_train: Training features
        y_train: Training target
        X_test: Test features
        y_test: Test target
        tune_params: Whether to perform hyperparameter tuning
        n_iter: Number of tuning iterations
        default_params: Default hyperparameters if not tuning
        
    Returns:
        Tuple of (trained_model, metrics_dict)
    """
    logger.info("Training model...")
    
    # Hyperparameter tuning or use defaults
    if tune_params:
        # Forward alpha from default_params so the tuner uses the correct
        # objective (quantile vs regression) and scoring (pinball vs RMSE).
        alpha = (default_params or {}).get('alpha', None)
        best_params = tune_hyperparameters(X_train, y_train, n_iter=n_iter, alpha=alpha)
        # Carry fixed params (objective, alpha) that are not part of the search space.
        # Using `default_params and key in default_params` lets Pylance narrow the type
        # to Dict[str, Any] inside the branch, avoiding the Optional subscript error.
        for key in ('objective', 'alpha'):
            if default_params and key in default_params:
                best_params.setdefault(key, default_params[key])
    else:
        best_params = default_params
        logger.info("Using provided hyperparameters (tune_params=False)")

    # Guard: best_params must not be None before training.
    # This can only happen if tune_params=False and default_params was not provided.
    if best_params is None:
        raise ValueError(
            "No hyperparameters available: set tune_params=True or provide default_params."
        )

    # Train final model
    model = train_model(X_train, y_train, best_params)
    
    # Evaluate
    metrics = evaluate_model(model, X_test, y_test, X_train, y_train)
    metrics['best_params'] = best_params
    
    return model, metrics


def persist_model(
    model: Any,
    metrics: Dict[str, Any],
    feature_cols: List[str],
    target_variable: str,
    key_stats: Dict[str, str],
    categorical_cols: List[str],
    model_path: str,
    save_mode: str = "local", 
    encoder: Any = None
) -> None:
    """
    Save trained model and metadata.
    
    Args:
        model: Trained model object
        metrics: Model performance metrics
        feature_cols: List of feature column names
        target_variable: Name of target column
        key_stats: Dictionary of statistics used
        categorical_cols: List of categorical columns
        model_path: Path to save model
        save_mode: Save mode ('local' or 'bq')
        encoder: Fitted encoder object (optional)
    """
    logger.info("Persisting model artifact...")
    save_model_artifact(
        model=model,
        metrics=metrics,
        feature_cols=feature_cols,
        target=target_variable,
        key_stats=key_stats,
        categorical_cols=categorical_cols,
        filepath=model_path,
        save_mode=save_mode,
        encoder=encoder
    )
    logger.info("Model saved successfully!")
    
    # Save metrics to database
    logger.info("Saving training metrics to database...")
    
    # Add target variable to metrics
    metrics['target_variable'] = target_variable
    # Convert metrics to DataFrame
    metrics_df = pd.DataFrame([metrics])

    save_database(
        df=metrics_df,
        table_name=MetricsFileName,
        mode=save_mode,
        write_disposition="WRITE_APPEND"
    )
    logger.info("Training metrics persisted successfully!")
