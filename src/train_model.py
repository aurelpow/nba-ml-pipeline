"""Light training pipeline for NBA fantasy points.

This module provides a small training utility that loads already-processed
boxscore/player tables (local CSVs or BigQuery via `common.io_utils.load_data`),
builds a simple feature matrix, performs a time-based train/test split and
trains a LightGBM or XGBoost regressor. The implementation is intentionally
robust to minor schema differences in the input tables.
"""

import logging 
import os
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
import joblib
from datetime import datetime

from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName, load_data, save_database, MetricsFileName
from common.utils import  parse_minutes
from common.constants import key_stats_points, categorical_cols_points, target_variable_points

from lightgbm import LGBMRegressor


class ModelTrainer:
    """Train a regressor to predict fantasy points.

    The trainer expects one of the pipeline input tables to contain a
    `points` target and a `game_date` datetime column. It will automatically
    pick numeric features and available one-hot position columns (columns that
    start with `position_`).
    """

    def __init__(self, model_path: str, save_mode: str = "local") -> None:
        """
        Initialize the model trainer.
        Args:
        model_path (str): path to save or load the model
        save_mode (str): mode for saving the model (local or cloud)
        """
        self.logger = logging.getLogger(__name__)
        self.model_path: str = model_path
        self.SAVE_MODE = save_mode
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: List[str] = []
        self.logger.info("ModelTrainer initialized.")

    def read_data(self) -> Dict[str, pd.DataFrame]:
        """
        Load boxscore / advanced / players tables using `load_data`.

        Returns:
            Dictionary with keys 'boxscore', 'advanced', 'players' (DataFrames).
        """
        box = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
        adv = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
        players = load_data(PlayersFileName, mode=self.SAVE_MODE)

        return {BoxscoreFileName: box,
                AdvancedBoxscoreFileName: adv,
                PlayersFileName: players}

    def prepare_model_df(self, data_map: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Create a modelling DataFrame from loaded tables.
        Args:
            data_map (Dict[str, pd.DataFrame]): dictionary with dataframes
        Return:
            pd.DataFrame: The prepared modelling DataFrame.
        """
        # Read data
        box: pd.DataFrame = data_map.get(BoxscoreFileName)
        adv: pd.DataFrame = data_map.get(AdvancedBoxscoreFileName)
        players: pd.DataFrame = data_map.get(PlayersFileName)

        # Merge boxscore df + players 
        df_merged: pd.DataFrame = box.merge(
            players[['person_id', 'position']].rename(columns={'position': 'position_player'}),
            left_on='personId', right_on='person_id', how='left'
        ).drop('person_id', axis=1)

        # Merge advanced stats with boxscore + players
        ## a) Define merge keys for box + adv
        merge_keys: list = ['gameId', 'personId', 'teamId']
        
        ## b) Identify new columns from advanced stats
        adv_new_cols = [col for col in adv.columns if col not in box.columns or col in merge_keys]
        
        ## c) Perform the merge
        df: pd.DataFrame = df_merged.merge(
            adv[adv_new_cols],
            left_on=merge_keys,
            right_on=merge_keys,
            how='left'
        )

        # Transform minutes from string to float using common.utils.parse_minutes
        df['minutes'] = df['minutes'].apply(parse_minutes)

        # fill NaN values in 'position' with 'BENCH'
        df['position'] = df['position'].fillna('BENCH')
        
        # Create a new column 'position_group' based on 'POSITION' and 'position' 
        df['position_group'] = df.apply(
            lambda x: 'G' if x['position'] in ('G', 'BENCH') and x['position_player'] in ('G', 'G-F') else
                    'F' if x['position'] in ('F', 'BENCH') and x['position_player'] in ('F', 'F-G', 'F-C') else
                    'C' if x['position'] in ('C', 'BENCH') and x['position_player'] in ('C', 'C-F') else x['position'],
            axis=1
        )

        # Remove rows
        df: pd.DataFrame = df[df['minutes'].notna()]  # Remove DNP rows

        # Change column date type to datetime 
        df['game_date'] = pd.to_datetime(df['game_date'])
        
        # Add a season column based on the game_id 
        df['season'] = df['gameId'].astype(str).str[1:3].astype(int) + 2000

        # Feature engineering
        df['is_home'] = df['teamId'] == df['home_team_id']
        df['opponent'] = np.where(df['is_home'], df['visitor_team_id'], df['home_team_id'])

        return df
    
    def historical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create historical performance features based on position group opponent and game date.(time aware)
        Args:
            df (pd.DataFrame): The input DataFrame already prepared with basic features.
        Return:
            pd.DataFrame: The DataFrame with historical features added.
        """
        # Filter out bench players and copy to avoid SettingWithCopyWarning
        df_hist = df[df['position'] != 'BENCH'].copy()

        # Compute historical mean points per (position_group, opponent, game_date)
        df_avg = (
            df_hist
            .groupby(['position_group', 'opponent', 'game_date'], as_index=False)['points']
            .mean()
            .rename(columns={'points': 'avg_points'})
        )

        # sort chronologically per group (oldest -> newest)
        df_avg = df_avg.sort_values(['position_group', 'opponent', 'game_date'], ascending=[True, True, True]).reset_index(drop=True)

        # Compute rolling averages shifted by 1 to avoid data leakage
        grp = df_avg.groupby(['position_group', 'opponent'])['avg_points']
        df_avg['avg_pts_opp_position_last_10'] = grp.apply(lambda x: x.shift(1).rolling(10, min_periods=1).mean()).reset_index(level=[0,1], drop=True)
        df_avg['avg_pts_opp_position_last_20'] = grp.apply(lambda x: x.shift(1).rolling(20, min_periods=1).mean()).reset_index(level=[0,1], drop=True)
        df_avg['avg_pts_opp_position_all'] = grp.apply(lambda x: x.shift(1).expanding().mean()).reset_index(level=[0,1], drop=True)


        # Merge back by date so each row only sees past info
        final_df = df.merge(
            df_avg[['position_group', 'opponent', 'game_date',
                    'avg_pts_opp_position_last_10',
                    'avg_pts_opp_position_last_20',
                    'avg_pts_opp_position_all']],
            on=['position_group', 'opponent', 'game_date'],
            how='left'
        )

        # Fill NaN for first occurrences
        final_df[['avg_pts_opp_position_last_10',
                  'avg_pts_opp_position_last_20',
                  'avg_pts_opp_position_all']] = final_df[[
                      'avg_pts_opp_position_last_10',
                      'avg_pts_opp_position_last_20',
                      'avg_pts_opp_position_all']].fillna(0)
        
        # Check the result for a specific opponent and position group (distinct rows only)
        specific_result = (
            final_df[
            (final_df['opponent'] == 1610612747) &
            (final_df['position_group'] == 'G')
            ]
            .sort_values('game_date')
            .reset_index(drop=True)
        )

        return final_df

    def normalize_features(self, df: pd.DataFrame, key_stats:dict[str, str]) -> pd.DataFrame:
        """
        Normalizing by playing time and pace gives features comparable across starters and bench.
        Args:
            df (pd.DataFrame): input DataFrame
            key_stats (dict[str, str]): dictionary of stats to normalize (e.g. {'points': 'Points', 'assists': 'Assists', 'rebounds': 'Rebounds'})
        Returns:
            pd.DataFrame: The DataFrame with normalized features added.
        """
        for stat in key_stats:
            per36: str = f"{stat}_per36"
            df[per36] = df[stat] / df['minutes'] * 36

        # And per-possession metrics
        for stat in key_stats:
            ppp: str = f"{stat}_per_poss"
            df[ppp] = df[stat] / df['possessions'] 

        return df

    def rolling_averages(self, df: pd.DataFrame, key_stats: dict[str, str], windows: List[int] = [5, 10, 20]) -> pd.DataFrame:
        """
        Compute rolling averages for key stats over specified windows.
        Args:
            df (pd.DataFrame): input DataFrame
            key_stats (dict[str, str]): dictionary of stats to compute rolling averages for
            windows (List[int]): list of window sizes (in number of games)
        Returns:
            pd.DataFrame: The DataFrame with rolling average features added.
        """
        # Sort by personId and game_date to ensure correct rolling calculations
        df: pd.DataFrame = df.sort_values(by=['personId', 'game_date'], ascending=[True, True]).copy()
        # Exclude Engineered stats
        raw_stats: dict = {k:v for k,v in key_stats.items() if 'engineering' not in v.lower()}
        for period in raw_stats:
            for rolling_period in windows:
                per36: str = f"{period}_per36"
                per_poss: str = f"{period}_per_poss"
                df[f"{per36}_rolling_{rolling_period}"] = (df
                                                           .groupby('personId')[per36]
                                                           .transform(lambda x: x.rolling(rolling_period, min_periods=1)
                                                                      .mean())
                )
                df[f"{per_poss}_rolling_{rolling_period}"] = (df
                                                              .groupby('personId')[per_poss]
                                                              .transform(lambda x: x.rolling(rolling_period, min_periods=1)
                                                                         .mean())
                )

        return df


    def numeric_features(self, key_stats: Dict[str, str], rolling_periods: List[int] = [5, 10, 20]) -> None:
        """
        Add numeric features EXACTLY matching notebook order
        Args:
            key_stats (Dict[str, str]): dictionary of stats to include
            rolling_periods (List[int]): list of rolling window sizes
        Returns:
            None: updates self.feature_cols in place
        """
        # Separate raw stats (get rolling) vs engineering stats (get per36/per_poss only)
        raw_stats: dict = [k for k, v in key_stats.items() if 'raw' in v.lower()]
        engineering_stats: dict = [k for k, v in key_stats.items() if 'engineering' in v.lower()]
        
        print(f"  Raw stats: {len(raw_stats)}, Engineering stats: {len(engineering_stats)}")
        
        # 1) Add rolling features GROUPED BY WINDOW (matching notebook)
        for window in rolling_periods:
            # First add all _per36_rolling_X for this window
            for stat in raw_stats:
                self.feature_cols.append(f"{stat}_per36_rolling_{window}")
            
            # Then add all _per_poss_rolling_X for this window
            for stat in raw_stats:
                self.feature_cols.append(f"{stat}_per_poss_rolling_{window}")
        
        # 2) Add historical averages (engineering stats) - per36 first, then per_poss
        for stat in engineering_stats:
            self.feature_cols.append(f"{stat}_per36")
        
        for stat in engineering_stats:
            self.feature_cols.append(f"{stat}_per_poss")
        
        print(f"Total numeric features: {len(self.feature_cols)}")

    def categorical_features(self, df: pd.DataFrame, categorical_cols: List[str]) -> pd.DataFrame:
        """
        Encode categorical features using one-hot encoding and add them to self.feature_cols.
        Args:
            df (pd.DataFrame): input DataFrame
            categorical_cols (List[str]): list of categorical columns to encode
        Returns:
            pd.DataFrame: The DataFrame with one-hot encoded categorical features added.
        """
        # encode categorical features
        encoder: OneHotEncoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoded_categorical: np.ndarray = encoder.fit_transform(df[categorical_cols])

        # Drop original categorical columns
        df: pd.DataFrame = df.drop(categorical_cols, axis=1)

        # Concatenate encoded columns to original dataframe
        final_df: pd.DataFrame = pd.concat([df, pd.DataFrame(encoded_categorical, columns=encoder.get_feature_names_out(categorical_cols))], axis=1)
        
        # Update feature_cols with new one-hot encoded columns
        self.feature_cols.extend(encoder.get_feature_names_out(categorical_cols).tolist())
                
        return final_df

    @staticmethod
    def _find_best_split( df: pd.DataFrame, target: str, 
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
        print(f"🔍 Searching for best split across {len(test_sizes)} test sizes...")
        for ts in test_sizes:
            idx: int = int((1 - ts) * len(unique_dates))
            split_date: Any = unique_dates[idx]
            
            train_df: pd.DataFrame = df[df['game_date'] < split_date]
            test_df: pd.DataFrame = df[df['game_date'] >= split_date]
            
            X_tr, y_tr = train_df[feature_cols], train_df[target]
            X_te, y_te = test_df[feature_cols], test_df[target]
            
            # Clean data
            X_tr: pd.DataFrame = X_tr.replace([np.inf, -np.inf], np.nan).fillna(0)
            X_te: pd.DataFrame = X_te.replace([np.inf, -np.inf], np.nan).fillna(0)
            
            # Quick baseline model for split evaluation
            model: LGBMRegressor = LGBMRegressor(objective='regression', n_estimators=100, verbose=-1)
            model.fit(X_tr, y_tr)
            
            y_pred: np.ndarray = model.predict(X_te)
            rmse: Any = np.sqrt(mean_squared_error(y_te, y_pred))
            r2: float = r2_score(y_te, y_pred)
            
            print(f"  test_size={ts:.2f} → R²={r2:.4f}, RMSE={rmse:.4f}")
            
            if r2 > best_r2:
                best_r2: float = r2
                best_rmse: float = rmse
                best_size: float = ts
                best_split_date: Any = split_date
        
        print(f"✅ Best split: test_size={best_size} (R²={best_r2:.4f})")
        
        return {
            'best_test_size': best_size,
            'best_split_date': best_split_date,
            'best_r2': best_r2,
            'best_rmse': best_rmse
        }
    
    @staticmethod
    def _tune_hyperparameters( X_train: pd.DataFrame, y_train: pd.Series,
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
        print(f"🎯 Tuning hyperparameters ({n_iter} iterations, {cv_splits}-fold TimeSeriesCV)...")
        
        param_distributions: dict = {
            'n_estimators': [100, 200, 300, 500, 1000],
            'learning_rate': [0.01, 0.05, 0.1, 0.15, 0.2],
            'max_depth': [3, 5, 7, 10],
            'num_leaves': [15, 31, 63, 100, 127],
            'min_child_samples': [5, 10, 20, 30, 50],
            'subsample': [0.6, 0.8, 0.9, 1.0],
            'colsample_bytree': [0.6, 0.8, 0.9, 1.0],
            'reg_alpha': [0, 0.01, 0.1, 1.0],
            'reg_lambda': [0, 0.01, 0.1, 1.0]
        }
        
        # Time-series aware cross-validation
        tscv: TimeSeriesSplit = TimeSeriesSplit(n_splits=cv_splits)

        lgbm: LGBMRegressor = LGBMRegressor(objective='regression', verbose=-1, random_state=42)

        random_search: RandomizedSearchCV = RandomizedSearchCV(
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

        print(f"✅ Best CV RMSE: {-random_search.best_score_:.4f}")
        print(f"📋 Best params: {random_search.best_params_}")
        
        return random_search.best_params_
    
    @staticmethod
    def _fit_final_model( X_train: pd.DataFrame, y_train: pd.Series,
                         best_params: Dict[str, Any]) -> LGBMRegressor:
        """
        Train the final model with best hyperparameters and optional time-decay weighting.
        
        Args:
            X_train: training features
            y_train: training target
            best_params: optimized hyperparameters            
        Returns:
            trained LGBMRegressor model
        """
        print(f"🚀 Training final model with best params...")
        
        model: LGBMRegressor = LGBMRegressor(**best_params, objective='regression', verbose=-1)
        
        
        model.fit(X_train, y_train)
        
        return model
    
    @staticmethod
    def _evaluate_model(model: LGBMRegressor, 
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
        print(f"📊 Evaluating model performance...")
        
        # Test set predictions
        y_pred_test: np.ndarray = model.predict(X_test)
        test_r2: float = r2_score(y_test, y_pred_test)
        test_rmse: float = np.sqrt(mean_squared_error(y_test, y_pred_test))
        test_mae: float = mean_absolute_error(y_test, y_pred_test)
        
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
        
        return metrics
    
    def train_model(self, df: pd.DataFrame, target: str, 
                   feature_cols: List[str],
                   test_sizes: List[float] = [0.15, 0.20, 0.25],
                   tune_params: bool = True,
                   n_iter: int = 20) -> Tuple[LGBMRegressor, Dict[str, Any]]:
        """
        Complete training pipeline: find best split, tune hyperparameters, train, evaluate.
        
        Args:
            df: preprocessed DataFrame
            target: target variable name
            feature_cols: list of feature columns
            test_sizes: candidate test sizes for split search
            tune_params: whether to perform hyperparameter tuning
            n_iter: number of random search iterations
            
        Returns:
            (trained_model, metrics_dict)
        """
        # Step 1: Find optimal train/test split
        split_info: dict = self._find_best_split(df, target, feature_cols, test_sizes)
        
        # Step 2: Create final train/test split with best size
        unique_dates: np.ndarray = np.sort(df['game_date'].unique())
        idx: int = int((1 - split_info['best_test_size']) * len(unique_dates))
        split_date: Any = unique_dates[idx]
        
        train_df: pd.DataFrame = df[df['game_date'] < split_date]
        test_df: pd.DataFrame = df[df['game_date'] >= split_date]

        X_train, y_train = train_df[feature_cols], train_df[target]
        X_test, y_test = test_df[feature_cols], test_df[target]
        
        # Clean data
        X_train: pd.DataFrame = X_train.replace([np.inf, -np.inf], np.nan).fillna(0)
        X_test: pd.DataFrame = X_test.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Step 3: Hyperparameter tuning (optional)
        if tune_params:
            best_params: dict = self._tune_hyperparameters(X_train, y_train, n_iter=n_iter)
        else:
            # Default params
            best_params: dict = {
                'n_estimators': 200,
                'learning_rate': 0.1,
                'max_depth': 7,
                'num_leaves': 31
            }
            print("⚙️  Using default hyperparameters (tune_params=False)")
        
        # Step 4: Train final model
        model: LGBMRegressor = self._fit_final_model(X_train, y_train, best_params=best_params)
        
        # Step 5: Evaluate
        metrics: dict = self._evaluate_model(model, X_test, y_test, X_train, y_train)
        
        # Combine all info
        metrics.update({
            'split_date': split_date,
            'test_size': split_info['best_test_size'],
            'best_params': best_params,
            'timestamp': datetime.now().isoformat()
        })
        
        return model, metrics
    

    def transform(self, tune_params: bool = True, n_iter: int = 20) -> Tuple[LGBMRegressor, Dict[str, Any]]:
        """
        Full data transformation and feature engineering pipeline.
        
        Args:
            tune_params: whether to perform hyperparameter tuning
            n_iter: number of hyperparameter search iterations
            
        Returns:
            (trained_model, metrics_dict)
        """
        self.logger.info("Starting data transformation and model training...")
        
        # Step 1: Read data
        self.logger.info("Loading data...")
        data_map: Dict[str, pd.DataFrame] = self.read_data()
        
        # Step 2: Prepare base DataFrame
        self.logger.info("Preparing base DataFrame...")
        df: pd.DataFrame = self.prepare_model_df(data_map)

        
        # Step 3: Add historical features
        self.logger.info("Engineering historical features...")
        df: pd.DataFrame = self.historical_features(df)
        
        # Step 4: Normalize features
        self.logger.info("Normalizing features (per-36, per-possession)...")
        df: pd.DataFrame = self.normalize_features(df, key_stats_points)
        
        # Step 5: Add rolling averages
        self.logger.info("Computing rolling averages...")
        df: pd.DataFrame = self.rolling_averages(df, key_stats_points, windows=[5, 10, 20])
        
        # Step 6: Build feature list and encode categoricals
        self.logger.info("Encoding categorical features...")
        self.numeric_features(key_stats_points, rolling_periods=[5, 10, 20])
        df: pd.DataFrame = self.categorical_features(df, categorical_cols_points)
        
        # Step 7: Train model
        self.logger.info("Training model...")
        model, metrics = self.train_model(
            df=df, 
            target=target_variable_points,
            feature_cols=self.feature_cols,
            tune_params=tune_params,
            n_iter=n_iter
        )
            
        return model, metrics

    def save_model(self, model, metrics, filepath) -> None:
        """
        Save trained model, scaler, feature columns, and metrics to disk.
        
        Args:
            model: trained model to save
            metrics: evaluation metrics to save
            filepath: path where to save the model artifact
        """
        if model is None:
            raise ValueError("No trained model found. Run transform() first.")
        
        self.logger.info(f"Saving model artifact to {filepath}...")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.logger.info(f"Directory {os.path.dirname(filepath)} is ready.")
        
        # Package everything needed for prediction
        artifact: dict = {
            'model': model,
            'scaler': self.scaler,
            'feature_cols': self.feature_cols,
            'metrics': metrics,
            'target': target_variable_points,
            'key_stats': key_stats_points,
            'categorical_cols': categorical_cols_points,
            'training_date': datetime.now().isoformat()
        }
        
        joblib.dump(artifact, filepath)
        print(f"✅ Model saved successfully")
        print(f"  Test R²: {metrics['test_r2']:.4f}")
        print(f"  Test RMSE: {metrics['test_rmse']:.4f}")

        # Save metrics to database
        # First transform metrics to DataFrame
        metrics_df = pd.DataFrame([metrics])
        
        save_database(df= metrics_df,
                      table_name=MetricsFileName, 
                      mode=self.SAVE_MODE,
                      write_disposition="WRITE_APPEND")
        
        return None
    
    def run(self, 
            tune_params: bool = True, n_iter: int = 20) -> None:
        """
        Complete end-to-end training pipeline: read → transform → train → save.
        
        Args:
            save_path: where to save the trained model
            tune_params: whether to perform hyperparameter tuning
            n_iter: number of hyperparameter tuning iterations
        """
        try:
            self.logger.info("Starting full training pipeline...")
            # Run full transformation and training
            model, metrics = self.transform(tune_params=tune_params, n_iter=n_iter)
            self.logger.info("Model training completed.")

            self.logger.info("Saving model artifact...")
            # Save model artifact
            self.save_model(model, metrics, filepath=self.model_path)
            self.logger.info("Model artifact saved.")

            self.logger.info("Pipeline completed successfully!")

        except Exception as e:
            self.logger.error(f"Pipeline failed: {str(e)}")
            raise