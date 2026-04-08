"""Unified training module for NBA player predictions.

Supports training models for different targets (points, fantasy_points)
using a consistent read/transform/persist pattern with configurable parameters.
"""

import logging
from typing import Dict, Any

from common.constants import (
    key_stats_points, categorical_cols_points, target_variable_points,
    key_stats_fantasy, categorical_cols_fantasy, target_variable_fantasy,
    rolling_windows_fantasy
)
from common.training_helpers import (
    read_training_data,
    transform_data,
    split_train_test,
    train_and_evaluate,
    persist_model
)

from src.targets.fantasy_points import compute_fantasy_points

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Default hyperparameters for each target
DEFAULT_PARAMS = {
    'points': {
        'n_estimators': 200,
        'learning_rate': 0.1,
        'max_depth': 7,
        'num_leaves': 31,
        'subsample': 0.8,
        'colsample_bytree': 0.8
    },
    'fantasy_points': {
        'objective': 'quantile',
        'alpha': 0.75,
        'n_estimators': 800,        # fewer trees, quantile loss converges differently
        'learning_rate': 0.02,      # faster than 0.007 — quantile loss is noisy
        'max_depth': 7,             # shallower — less variance on non-smooth loss
        'num_leaves': 50,           # down from 63
        'subsample': 0.7,
        'colsample_bytree': 0.6,
        'reg_alpha': 0.5,           # reduce L1 slightly
        'reg_lambda': 1.0,          # keep some L2
        'min_child_samples': 40,
    }
}


class UnifiedModelTrainer:
    """Unified trainer for both points and fantasy points prediction."""

    def __init__(
        self,
        target: str,
        model_path: str,
        save_mode: str = "local"
    ) -> None:
        """
        Initialize the unified trainer.
        
        Args:
            target: Target variable ('points' or 'fantasy_points')
            model_path: Path to save trained model
            save_mode: Save mode ('local' or 'bq')
        """
        if target not in ['points', 'fantasy_points']:
            raise ValueError(f"Invalid target: {target}. Must be 'points' or 'fantasy_points'")
        
        self.target = target
        self.save_mode = save_mode
        self.feature_cols = []
        # Use the provided path as-is
        self.model_path = model_path
        
        # Configure target-specific settings
        if target == 'points':
            self.key_stats = key_stats_points
            self.categorical_cols = categorical_cols_points
            self.target_variable = target_variable_points
            self.rolling_windows = [5, 10, 20]
            self.target_computer_fn = None
        else:  # fantasy_points
            self.key_stats = key_stats_fantasy
            self.categorical_cols = categorical_cols_fantasy
            self.target_variable = target_variable_fantasy
            self.rolling_windows = rolling_windows_fantasy
            self.target_computer_fn = compute_fantasy_points
        
        logger.info(f"Initialized UnifiedModelTrainer for target: {target}")

    def read(self) -> Dict[str, Any]:
        """
        Read training data.
        
        Returns:
            Dictionary with raw dataframes
        """
        return read_training_data(save_mode=self.save_mode)

    def transform(self, data_map: Dict[str, Any]) -> tuple:
        """
        Transform raw data into ML-ready features.
        
        Args:
            data_map: Dictionary with raw dataframes
            
        Returns:
            Tuple of (transformed_df, feature_cols, encoded_cols, encoder)
        """
        return transform_data(
            data_map=data_map,
            target_variable=self.target_variable,
            key_stats=self.key_stats,
            categorical_cols=self.categorical_cols,
            rolling_windows=self.rolling_windows,
            target_computer_fn=self.target_computer_fn
        )

    def persist(self, model: Any, metrics: Dict[str, Any], encoder: Any = None) -> None:
        """
        Save trained model and metadata.
        
        Args:
            model: Trained model object
            metrics: Model performance metrics
            encoder: Fitted encoder object (optional)
        """
        persist_model(
            model=model,
            metrics=metrics,
            feature_cols=self.feature_cols,
            target_variable=self.target_variable,
            key_stats=self.key_stats,
            categorical_cols=self.categorical_cols,
            model_path=self.model_path,
            save_mode=self.save_mode
        )

    def run(self, tune_params: bool = True, n_iter: int = 20) -> None:
        """
        Execute complete training pipeline: read → transform → train → persist.
        
        Args:
            tune_params: Whether to perform hyperparameter tuning
            n_iter: Number of tuning iterations
        """
        try:
            logger.info(f"Starting training pipeline for {self.target}...")
            
            # 1. Read data
            data_map = self.read()
            
            # 2. Transform data
            df, self.feature_cols, encoded_cols, self.encoder = self.transform(data_map)
            
            # 3. Split train/test
            X_train, X_test, y_train, y_test, split_info = split_train_test(
                df=df,
                target_variable=self.target_variable,
                feature_cols=self.feature_cols
            )
            
            # 4. Train and evaluate
            model, metrics = train_and_evaluate(
                X_train=X_train,
                y_train=y_train,
                X_test=X_test,
                y_test=y_test,
                tune_params=tune_params,
                n_iter=n_iter,
                default_params=DEFAULT_PARAMS[self.target]
            )
            
            # 5. Update metrics with split info
            metrics.update(split_info)
            
            # 6. Persist model
            self.persist(model=model, metrics=metrics, encoder=self.encoder)
            
            logger.info("Training pipeline completed successfully!")
            
        except Exception as e:
            logger.error(f"Training pipeline failed: {str(e)}")
            raise
