import logging
import pandas as pd
from typing import Dict, Any, Tuple
import numpy as np
from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName, load_data
from common.constants import key_stats_fantasy, categorical_cols_fantasy, target_variable_fantasy, rolling_windows_fantasy
from common.feature_engineering import (
    merge_data, preprocess_data, create_historical_features, 
    normalize_features, compute_rolling_stats, encode_categorical_features,
    get_feature_cols
)
from common.model_utils import (
    find_best_split, tune_hyperparameters, train_model, 
    evaluate_model, save_model_artifact
)

from src.targets.fantasy_points import compute_fantasy_points

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

class FantasyModelTrainer:
    """Train a regressor to predict fantasy points."""

    def __init__(self, model_path: str, save_mode: str = "local") -> None:
        self.model_path = model_path
        self.SAVE_MODE = save_mode
        self.feature_cols = []
        self.scaler = None # Not used for Tree models usually, but kept for compatibility

    def run(self, tune_params: bool = True, n_iter: int = 12) -> None:
        """
        Complete end-to-end training pipeline.
        """
        try:
            logger.info("Starting Fantasy Points training pipeline...")
            
            # 1. Load Data
            logger.info("Loading data...")
            box = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
            adv = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
            players = load_data(PlayersFileName, mode=self.SAVE_MODE)
            
            # 2. Merge & Preprocess
            logger.info("Merging and preprocessing data...")
            df = merge_data(box, adv, players)
            df = preprocess_data(df)
            
            # 3. Compute Target (Fantasy Points)
            logger.info("Computing Fantasy Points...")
            df = compute_fantasy_points(df)
            target = target_variable_fantasy
            
            # 4. Feature Engineering
            logger.info("Engineering features...")
            df = create_historical_features(df, target_col=target)
            df = normalize_features(df, key_stats_fantasy)
            df = compute_rolling_stats(df, key_stats_fantasy, windows=rolling_windows_fantasy)
            
            # 5. Encode Categoricals
            logger.info("Encoding categorical features...")
            df, encoded_cols, _ = encode_categorical_features(df, categorical_cols_fantasy)
            
            # 6. Define Feature Columns
            self.feature_cols = get_feature_cols(key_stats_fantasy, rolling_periods=rolling_windows_fantasy)
            self.feature_cols.append('rest_days')
            self.feature_cols.extend(encoded_cols)
            logger.info(f"Total features: {len(self.feature_cols)}")
            
            # 7. Train/Test Split
            split_info = find_best_split(df, target, self.feature_cols)
            
            # Create final split
            unique_dates = np.sort(df['game_date'].unique())
            idx = int((1 - split_info['best_test_size']) * len(unique_dates))
            split_date = unique_dates[idx]
            
            train_df = df[df['game_date'] < split_date]
            test_df = df[df['game_date'] >= split_date]
            
            X_train = train_df[self.feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
            y_train = train_df[target]
            X_test = test_df[self.feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
            y_test = test_df[target]
            
            # 8. Hyperparameter Tuning
            if tune_params:
                best_params = tune_hyperparameters(X_train, y_train, n_iter=n_iter)
            else:
                best_params = {
                    'n_estimators': 2300,
                    'learning_rate': 0.004,
                    'max_depth': 10,
                    'num_leaves': 90,
                    'subsample': 0.8,
                    'colsample_bytree': 0.6,
                    'reg_alpha': 0.8,
                    'reg_lambda': 0.8,
                    'min_child_samples': 50
                }
            
            # 9. Train Final Model
            model = train_model(X_train, y_train, best_params)
            
            # 10. Evaluate
            metrics = evaluate_model(model, X_test, y_test, X_train, y_train)
            metrics.update({
                'split_date': split_date,
                'test_size': split_info['best_test_size'],
                'best_params': best_params
            })
            
            # 11. Save Artifact
            save_model_artifact(
                model=model,
                metrics=metrics,
                feature_cols=self.feature_cols,
                target=target,
                key_stats=key_stats_fantasy,
                categorical_cols=categorical_cols_fantasy,
                filepath=self.model_path
            )
            
            logger.info("Pipeline completed successfully!")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise

import numpy as np # Added missing import
