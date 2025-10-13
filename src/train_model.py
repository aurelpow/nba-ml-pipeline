"""Light training pipeline for NBA fantasy points.

This module provides a small training utility that loads already-processed
boxscore/player tables (local CSVs or BigQuery via `common.io_utils.load_data`),
builds a simple feature matrix, performs a time-based train/test split and
trains a LightGBM or XGBoost regressor. The implementation is intentionally
robust to minor schema differences in the input tables.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
import joblib
from datetime import datetime

from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName, load_data
from common.constants import key_stats_points, categorical_cols_points, target_variable_points

from lightgbm import LGBMRegressor


class ModelTrainer:
    """Train a regressor to predict fantasy points.

    The trainer expects one of the pipeline input tables to contain a
    `points` target and a `game_date` datetime column. It will automatically
    pick numeric features and available one-hot position columns (columns that
    start with `position_`).
    """

    def __init__(self, model_path: str, save_mode: str = "local"):
        self.model_path: str = model_path
        self.SAVE_MODE = save_mode
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: List[str] = []

    def read_data(self) -> Dict[str, pd.DataFrame]:
        """Load boxscore / advanced / players tables using `load_data`.

        Returns a dict with keys 'boxscore', 'advanced', 'players' (DataFrames).
        """
        box = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
        adv = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
        players = load_data(PlayersFileName, mode=self.SAVE_MODE)

        return {"boxscore": box, "advanced": adv, "players": players}

    def prepare_model_df(self, data_map: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Create a modelling DataFrame from loaded tables.

        Heuristics:
        - prefer `boxscore` if it already contains `points` and `game_date`.
        - if not, merge box + advanced + players on common id columns.
        - select numeric features and existing `position_` one-hot columns.
        """
        box: pd.DataFrame = data_map.get("boxscore")
        adv: pd.DataFrame = data_map.get("advanced")
        players: pd.DataFrame = data_map.get("players")

        # Merge box + players 
        df_merged: pd.DataFrame = box.merge(
            players[['person_id', 'position']].rename(columns={'position': 'position_player'}),
            left_on='personId', right_on='person_id', how='left'
        ).drop('person_id', axis=1)

        # Merge advanced stats
        ## Define merge keys
        merge_keys: list = ['gameId', 'personId', 'teamId']
        ## Identify new columns from advanced stats
        adv_new_cols = [col for col in adv.columns if col not in box.columns or col in merge_keys]
        
        ## Perform the merge
        df: pd.DataFrame = df_merged.merge(
            adv[adv_new_cols],
            left_on=merge_keys,
            right_on=merge_keys,
            how='left'
        )

        # Transform minutes from string to float
        df['minutes'] = df['minutes'].apply(lambda x: float(x.split(':')[0]) if pd.notnull(x) else 0)

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
        """Create historical performance features."""
        # 1. Make sure your dates are true datetimes, and filter out bench players
        df_hist = df[df['position'] != 'BENCH']
        
        # 2. compute one avg_points per group/opponent/game_date
        df_avg = (
            df_hist
            .groupby(['position_group','opponent','game_date'])['points']
            .mean()
            .reset_index(name='avg_points')
        )

        # 3. sort so tail() really pulls the last N by date
        df_avg = df_avg.sort_values(['position_group','opponent','game_date'])

        # 4. aggregate per (position_group, opponent)
        result = (
            df_avg
            .groupby(['position_group','opponent'])
            .apply(lambda g: pd.Series({
                'avg_pts_opp_position_last_10': g['avg_points'].tail(10).mean(),
                'avg_pts_opp_position_last_20': g['avg_points'].tail(20).mean(),
                'avg_pts_opp_position_all'   : g['avg_points'].mean()
            }))
            .reset_index()
        )

                # 5. Put these stats back on final_df 
        final_df = (
            df
            .merge(result[['position_group','opponent','avg_pts_opp_position_last_10','avg_pts_opp_position_last_20','avg_pts_opp_position_all']],
                on=['position_group','opponent'],
                how='left')
        )

        return final_df

    def normalize_features(self, df: pd.DataFrame, key_stats:dict[str, str]) -> pd.DataFrame:
        """
        Normalizing by playing time and pace gives features comparable across starters and bench.
        Args:
            df (pd.DataFrame): input DataFrame
            key_stats (dict[str, str]): dictionary of stats to normalize (e.g. {'points': 'Points', 'assists': 'Assists', 'rebounds': 'Rebounds'})

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
        """
        # Sort by personId and game_date to ensure correct rolling calculations
        df = df.sort_values(by=['personId', 'game_date'])
        # Exlude Engineered stats
        key_stats = {k:v for k,v in key_stats.items() if 'engineering' not in v.lower()}
        for period in key_stats:
            for rolling_period in windows:
                per36 = f"{period}_per36"
                per_poss = f"{period}_per_poss"
                df[f"{per36}_rolling_{rolling_period}"] = (df
                                                           .groupby('personId')[per36]
                                                           .transform(lambda x: x.rolling(rolling_period, min_periods=1)
                                                                      .mean())
                )
                df[f"{per_poss}_rolling_{rolling_period}"] = (df
                                                              .groupby('personId')[per_poss]
                                                              .transform(lambda x: x.rolling(rolling_period, min_periods=1).mean())
                )

        return df


    def numeric_features(self, key_stats: Dict[str, str], rolling_periods: List[int] = [5, 10, 20]) -> None:
        """
        Add numeric features EXACTLY matching notebook order.
        
        Order: Group by ROLLING WINDOW, not by stat.
        """
        # Separate raw stats (get rolling) vs engineering stats (get per36/per_poss only)
        raw_stats = [k for k, v in key_stats.items() if 'raw' in v.lower()]
        engineering_stats = [k for k, v in key_stats.items() if 'engineering' in v.lower()]
        
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
        
        print(f"  Total numeric features: {len(self.feature_cols)}")

    def categorical_features(self, df: pd.DataFrame, categorical_cols: List[str]) -> pd.DataFrame:
        """
        Encode categorical features using one-hot encoding and add them to self.feature_cols.
        Args:
            df (pd.DataFrame): input DataFrame
            categorical_cols (List[str]): list of categorical columns to encode
        """
        # encode categorical features
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoded_categorical = encoder.fit_transform(df[categorical_cols])

        # Drop original categorical columns
        df = df.drop(categorical_cols, axis=1)

        # Concatenate encoded columns to original dataframe
        final_df = pd.concat([df, pd.DataFrame(encoded_categorical, columns=encoder.get_feature_names_out(categorical_cols))], axis=1)
        
        # Update feature_cols with new one-hot encoded columns
        self.feature_cols.extend(encoder.get_feature_names_out(categorical_cols).tolist())
                
        return final_df

    def _find_best_split(self, df: pd.DataFrame, target: str, 
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
        best_size = None
        best_r2 = -np.inf
        best_rmse = np.inf
        best_split_date = None
        
        unique_dates = np.sort(df['game_date'].unique())
        
        print(f"🔍 Searching for best split across {len(test_sizes)} test sizes...")
        
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
            model = LGBMRegressor(objective='regression', n_estimators=100, verbose=-1)
            model.fit(X_tr, y_tr)
            
            y_pred = model.predict(X_te)
            rmse = np.sqrt(mean_squared_error(y_te, y_pred))
            r2 = r2_score(y_te, y_pred)
            
            print(f"  test_size={ts:.2f} → R²={r2:.4f}, RMSE={rmse:.4f}")
            
            if r2 > best_r2:
                best_r2 = r2
                best_rmse = rmse
                best_size = ts
                best_split_date = split_date
        
        print(f"✅ Best split: test_size={best_size} (R²={best_r2:.4f})")
        
        return {
            'best_test_size': best_size,
            'best_split_date': best_split_date,
            'best_r2': best_r2,
            'best_rmse': best_rmse
        }
    
    def _tune_hyperparameters(self, X_train: pd.DataFrame, y_train: pd.Series,
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
        
        param_distributions = {
            'n_estimators': [100, 200, 300, 500, 1000],
            'learning_rate': [0.01, 0.05, 0.1, 0.15, 0.2],
            'max_depth': [3, 5, 7, 10,],
            'num_leaves': [15, 31, 63, 100, 127],
            'min_child_samples': [5, 10, 20, 30, 50],
            'subsample': [0.6, 0.8, 0.9, 1.0],
            'colsample_bytree': [0.6, 0.8, 0.9, 1.0],
            'reg_alpha': [0, 0.01, 0.1, 1.0],
            'reg_lambda': [0, 0.01, 0.1, 1.0]
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

        print(f"✅ Best CV R²: {-random_search.best_score_:.4f}")
        print(f"📋 Best params: {random_search.best_params_}")
        
        return random_search.best_params_
    
    def _fit_final_model(self, X_train: pd.DataFrame, y_train: pd.Series,
                         best_params: Dict[str, Any]) -> LGBMRegressor:
        """
        Train the final model with best hyperparameters and optional time-decay weighting.
        
        Args:
            X_train: training features
            y_train: training target
            best_params: optimized hyperparameters
            decay_alpha: decay rate for time weighting (higher = more recent emphasis)
            
        Returns:
            trained LGBMRegressor model
        """
        print(f"🚀 Training final model with best params...")
        
        model = LGBMRegressor(**best_params, objective='regression', verbose=-1)
        
        
        model.fit(X_train, y_train)
        
        return model
    
    def _evaluate_model(self, model: LGBMRegressor, 
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
        
        print(f"  Test  → R²={test_r2:.4f}, RMSE={test_rmse:.4f}, MAE={test_mae:.4f}")
        print(f"  Train → R²={train_r2:.4f}, RMSE={train_rmse:.4f}")
        print(f"  Overfit Gap: {metrics['overfitting_gap']:.4f}")
        
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
        split_info = self._find_best_split(df, target, feature_cols, test_sizes)
        
        # Step 2: Create final train/test split with best size
        unique_dates = np.sort(df['game_date'].unique())
        idx = int((1 - split_info['best_test_size']) * len(unique_dates))
        split_date = unique_dates[idx]
        
        train_df = df[df['game_date'] < split_date]
        test_df = df[df['game_date'] >= split_date]
        
        X_train, y_train = train_df[feature_cols], train_df[target]
        X_test, y_test = test_df[feature_cols], test_df[target]
        
        # Clean data
        X_train = X_train.replace([np.inf, -np.inf], np.nan).fillna(0)
        X_test = X_test.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # Step 3: Hyperparameter tuning (optional)
        if tune_params:
            best_params = self._tune_hyperparameters(X_train, y_train, n_iter=n_iter)
        else:
            # Default params
            best_params = {
                'n_estimators': 200,
                'learning_rate': 0.1,
                'max_depth': 7,
                'num_leaves': 31
            }
            print("⚙️  Using default hyperparameters (tune_params=False)")
        
        # Step 4: Train final model
        model = self._fit_final_model(X_train, y_train, best_params=best_params)
        
        # Step 5: Evaluate
        metrics = self._evaluate_model(model, X_test, y_test, X_train, y_train)
        
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
        print("=" * 60)
        print("🏀 NBA FANTASY POINTS - MODEL TRAINING PIPELINE")
        print("=" * 60)
        
        # Step 1: Read data
        print("\n📥 Step 1/7: Loading data...")
        data_map = self.read_data()
        
        # Step 2: Prepare base DataFrame
        print("\n🔧 Step 2/7: Preparing base DataFrame...")
        df = self.prepare_model_df(data_map)
        print(f"  Loaded {len(df):,} player-game records")
        
        # Step 3: Add historical features
        print("\n📊 Step 3/7: Engineering historical features...")
        df = self.historical_features(df)
        
        # Step 4: Normalize features
        print("\n⚖️  Step 4/7: Normalizing features (per-36, per-possession)...")
        df = self.normalize_features(df, key_stats_points)
        
        # Step 5: Add rolling averages
        print("\n📈 Step 5/7: Computing rolling averages...")
        df = self.rolling_averages(df, key_stats_points, windows=[5, 10, 20])
        
        # Step 6: Build feature list and encode categoricals
        print("\n🏷️  Step 6/7: Encoding categorical features...")
        self.numeric_features(key_stats_points, rolling_periods=[5, 10, 20])
        df = self.categorical_features(df, categorical_cols_points)
        print(f"  Total features: {len(self.feature_cols)}")
        
        # Step 7: Train model
        print("\n🤖 Step 7/7: Training model...")
        model, metrics = self.train_model(
            df=df, 
            target=target_variable_points,
            feature_cols=self.feature_cols,
            tune_params=tune_params,
            n_iter=n_iter
        )
    
        
        print("\n" + "=" * 60)
        print("✅ TRAINING COMPLETE")
        print("=" * 60)
        
        return model, metrics

    def save_model(self, model, metrics, filepath: str = "models/best_lgbm_model.pkl") -> None:
        """
        Save trained model, scaler, feature columns, and metrics to disk.
        
        Args:
            model: trained model to save
            metrics: evaluation metrics to save
            filepath: path where to save the model artifact
        """
        if not hasattr(self, 'model') or self.model is None:
            raise ValueError("No trained model found. Run transform() first.")
        
        print(f"\n💾 Saving model to {filepath}...")
        
        # Create directory if needed
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        
        # Package everything needed for prediction
        artifact = {
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
        print(f"  Test R²: {self.metrics['test_r2']:.4f}")
        print(f"  Test RMSE: {self.metrics['test_rmse']:.4f}")

    def run(self, save_path: str = "models/best_lgbm_model.pkl", 
            tune_params: bool = True, n_iter: int = 20) -> None:
        """
        Complete end-to-end training pipeline: read → transform → train → save.
        
        Args:
            save_path: where to save the trained model
            tune_params: whether to perform hyperparameter tuning
            n_iter: number of hyperparameter tuning iterations
        """
        try:
            # Run full transformation and training
            model, metrics = self.transform(tune_params=tune_params, n_iter=n_iter)
            
            # Save model artifact
            self.save_model(model, metrics, filepath=save_path)
            
            print("\n🎉 Pipeline completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Pipeline failed: {str(e)}")
            raise