"""Light training pipeline for NBA points prediction.

This module provides a training utility that loads processed data,
builds a feature matrix, performs a time-based train/test split and
trains a LightGBM regressor.
"""

import logging 
from typing import Dict, List, Any
import pandas as pd
import numpy as np

from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName, load_data
from common.constants import key_stats_points, categorical_cols_points, target_variable_points

from common.feature_engineering import (
    merge_data, preprocess_data, create_historical_features, 
    normalize_features, compute_rolling_stats, encode_categorical_features,
    get_feature_cols
)
from common.model_utils import (
    find_best_split, tune_hyperparameters, train_model, 
    evaluate_model, save_model_artifact
)

class ModelTrainer:
    """Train a regressor to predict points."""

    def __init__(self, model_path: str, save_mode: str = "local") -> None:
        """
        Initialize the model trainer.
        Args:
        model_path (str): path to save or load the model
        save_mode (str): mode for saving the model (local or cloud)
        """
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        self.model_path: str = model_path
        self.SAVE_MODE = save_mode
        self.feature_cols: List[str] = []
        self.logger.info("ModelTrainer initialized.")

    def read_data(self) -> Dict[str, pd.DataFrame]:
        """
        Load necessary data tables for model training.
        Returns:
            Dict[str, pd.DataFrame]: dictionary with loaded dataframes
        """
        box = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
        adv = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
        players = load_data(PlayersFileName, mode=self.SAVE_MODE)

        return {BoxscoreFileName: box,
                AdvancedBoxscoreFileName: adv,
                PlayersFileName: players}

    def run(self, tune_params: bool = True, n_iter: int = 20) -> None:
        """
        Complete end-to-end training pipeline: read → transform → train → save.
        
        Args:
            tune_params: whether to perform hyperparameter tuning
            n_iter: number of hyperparameter tuning iterations
        """
        try:
            self.logger.info("Starting full training pipeline...")
            
            # 1. Load Data
            self.logger.info("Loading data...")
            data_map = self.read_data()
            box = data_map[BoxscoreFileName]
            adv = data_map[AdvancedBoxscoreFileName]
            players = data_map[PlayersFileName]
            
            # 2. Merge & Preprocess
            self.logger.info("Merging and preprocessing data...")
            df = merge_data(box, adv, players)
            df = preprocess_data(df)
            
            # 3. Feature Engineering
            self.logger.info("Engineering features...")
            df = create_historical_features(df, target_col='points')
            df = normalize_features(df, key_stats_points)
            df = compute_rolling_stats(df, key_stats_points, windows=[5, 10, 20])
            
            # 4. Encode Categoricals
            self.logger.info("Encoding categorical features...")
            df, encoded_cols, _ = encode_categorical_features(df, categorical_cols_points)
            
            # 5. Define Feature Columns
            self.feature_cols = get_feature_cols(key_stats_points, rolling_periods=[5, 10, 20])
            self.feature_cols.extend(encoded_cols)
            self.logger.info(f"Total features: {len(self.feature_cols)}")
            
            # 6. Train/Test Split
            target = target_variable_points
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
            
            # 7. Hyperparameter Tuning
            if tune_params:
                best_params = tune_hyperparameters(X_train, y_train, n_iter=n_iter)
            else:
                best_params = {
                    'n_estimators': 200,
                    'learning_rate': 0.1,
                    'max_depth': 7,
                    'num_leaves': 31
                }
                self.logger.info("⚙️  Using default hyperparameters (tune_params=False)")
            
            # 8. Train Final Model
            model = train_model(X_train, y_train, best_params)
            
            # 9. Evaluate
            metrics = evaluate_model(model, X_test, y_test, X_train, y_train)
            metrics.update({
                'split_date': split_date,
                'test_size': split_info['best_test_size'],
                'best_params': best_params
            })
            
            # 10. Save Artifact
            save_model_artifact(
                model=model,
                metrics=metrics,
                feature_cols=self.feature_cols,
                target=target,
                key_stats=key_stats_points,
                categorical_cols=categorical_cols_points,
                filepath=self.model_path,
                save_mode=self.SAVE_MODE
            )
            
            self.logger.info("Pipeline completed successfully!")

        except Exception as e:
            self.logger.error(f"Pipeline failed: {str(e)}")
            raise
