"""Unified prediction module for NBA player predictions.

Supports making predictions for different targets (points, fantasy_points)
using a consistent pipeline pattern.
"""

import logging
import datetime
import pandas as pd
import numpy as np
from typing import Dict, Any

from common.singleton_meta import SingletonMeta
from common.io_utils import (
    BoxscoreFileName, AdvancedBoxscoreFileName, 
    PlayersFileName, PredictionsFileName, ScheduleFileName,
    load_data, save_predictions
)
from common.model_utils import load_model_artifact
from common.constants import TARGET_CONFIGS
from common.feature_engineering import (
    merge_data, preprocess_data, create_historical_features, 
    normalize_features, compute_rolling_stats, encode_categorical_features,
    get_feature_cols, get_volatility, get_final_df, get_rest_days
)

logger = logging.getLogger(__name__)


class UnifiedPredictor(metaclass=SingletonMeta):
    """Unified predictor for both points and fantasy points predictions."""

    def __init__(
        self,
        target: str,
        save_mode: str,
        date: str,
        model_path: str
    ) -> None:
        """
        Initialize the unified predictor.
        
        Args:
            target: Target variable ('points' or 'fantasy_points')
            save_mode: Save mode ('local' or 'bq')
            date: Prediction date in YYYY-MM-DD format
            model_path: Path to trained model (file or directory)
        """
        # Validate target
        if target not in TARGET_CONFIGS:
            available_targets = list(TARGET_CONFIGS.keys())
            raise ValueError(f"Invalid target: {target}. Available targets: {available_targets}")
        
        self.target = target
        self.save_mode = save_mode
        self.date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        self.model_path = model_path
        
        # Load target-specific configuration
        config = TARGET_CONFIGS[target]
        self.key_stats = config['key_stats']
        self.categorical_cols = config['categorical_cols']
        self.target_variable = config['target_variable']
        self.rolling_windows = config['rolling_windows']
        self.measure_prediction = config['measure_prediction']
        self.measure_volatility = config['measure_volatility']
        
        # Handle target computation function (lazy import to avoid circular dependencies)
        if config['target_computer_fn']:
            if config['target_computer_fn'] == 'compute_fantasy_points':
                from src.targets.fantasy_points import compute_fantasy_points
                self.target_computer_fn = compute_fantasy_points
            else:
                self.target_computer_fn = None
        else:
            self.target_computer_fn = None
        
        logger.info(f"Initialized UnifiedPredictor for target: {target}")

    def read_data(self) -> Dict[str, pd.DataFrame]:
        """
        Read necessary data from storage.
        
        Returns:
            Dictionary containing loaded dataframes
        """
        logger.info("Loading data for predictions...")
        box = load_data(BoxscoreFileName, mode=self.save_mode)
        adv = load_data(AdvancedBoxscoreFileName, mode=self.save_mode)
        players = load_data(PlayersFileName, mode=self.save_mode)
        schedule = load_data(ScheduleFileName, mode=self.save_mode)

        return {
            BoxscoreFileName: box,
            AdvancedBoxscoreFileName: adv,
            PlayersFileName: players,
            ScheduleFileName: schedule
        }

    def get_future_games_players(self, data_map: dict) -> pd.DataFrame:
        """
        Get future games with player information for the specified date.
        
        Args:
            data_map: Dictionary containing loaded dataframes
            
        Returns:
            DataFrame with future games and player info
        """
        all_schedule_df = data_map[ScheduleFileName]
        players_df = data_map[PlayersFileName]
        
        # Filter schedule for the specific date
        all_schedule_df["gameDate"] = pd.to_datetime(all_schedule_df["gameDate"]).dt.date
        specific_games_df = all_schedule_df[all_schedule_df["gameDate"] == self.date]

        # Handle case with no games
        if specific_games_df.empty:
            logger.warning(f"No games found for the selected date: {self.date}")
            raise ValueError(f"No games scheduled for {self.date}")

        # Prepare players data
        players_unique = players_df[['person_id', 'player_slug', 'team_id', 'position']].drop_duplicates()

        # Cross join players with specific games
        specific_games_df = pd.concat([
            specific_games_df.merge(players_unique, left_on='homeTeam_teamId', right_on='team_id'),
            specific_games_df.merge(players_unique, left_on='awayTeam_teamId', right_on='team_id')
        ], ignore_index=True)
        
        # Add opponent team id column
        specific_games_df['opponent'] = np.where(
            specific_games_df['team_id'] == specific_games_df['homeTeam_teamId'],
            specific_games_df['awayTeam_teamId'],
            specific_games_df['homeTeam_teamId']
        )

        # Add position group column (needed for fantasy)
        specific_games_df['position_group'] = specific_games_df['position'].map(
            lambda x: 'G' if x in ('G', 'G-F') else 'F' if x in ('F', 'F-G', 'F-C') else 'C' if x in ('C', 'C-F') else x
        )
        
        # Additional columns needed for feature engineering
        specific_games_df['is_home'] = specific_games_df['team_id'] == specific_games_df['homeTeam_teamId']
        specific_games_df['season'] = specific_games_df['gameId'].astype(str).str[1:3].astype(int) + 2000
        specific_games_df['game_date'] = pd.to_datetime(specific_games_df['gameDate'])

        logger.info(f"Found {len(specific_games_df)} player-game combinations for {self.date}")
        return specific_games_df

    def transform_data(self, data_map: dict, model: Any) -> pd.DataFrame:
        """
        Transform data for predictions.
        
        Args:
            data_map: Dictionary containing loaded dataframes
            model: Trained model
            
        Returns:
            DataFrame with predictions
        """
        logger.info("Transforming data for predictions...")
        
        # Load historical data
        box = data_map[BoxscoreFileName]
        adv = data_map[AdvancedBoxscoreFileName]

        # Filter historical data to be strictly before prediction date
        box = box[pd.to_datetime(box['game_date']).dt.date < self.date]
        adv = adv[pd.to_datetime(adv['game_date']).dt.date < self.date]
        
        # Merge & Preprocess Historical
        df_hist = merge_data(box, adv, data_map[PlayersFileName])
        df_hist = preprocess_data(df_hist)
        
        # Compute target if custom function provided (fantasy points)
        if self.target_computer_fn:
            logger.info(f"Computing {self.target_variable}...")
            df_hist = self.target_computer_fn(df_hist)

        # Create Historical Features
        df_hist = create_historical_features(df_hist, target_col=self.target_variable)
        
        # Calculate Rest Days
        rest_days_df = get_rest_days(
            players_df=data_map[PlayersFileName],
            boxscore_df=box,
            date=self.date
        )

        # Merge rest days into historical data
        df_hist = df_hist.merge(rest_days_df, on=['personId'], how='left')
        
        # Normalize and Compute Rolling Stats
        df_hist = normalize_features(df_hist, self.key_stats)
        df_hist = compute_rolling_stats(df_hist, self.key_stats, windows=self.rolling_windows)
        
        # Prepare Future Data
        future_games = self.get_future_games_players(data_map)
        
        # Get feature columns
        features_list = get_feature_cols(
            key_stats=self.key_stats,
            rolling_periods=self.rolling_windows
        )

        # Encode Categoricals
        encoded_df, encoded_feature_names = encode_categorical_features(
            df=df_hist,
            categorical_cols=self.categorical_cols
        )
        
        # Get volatility
        volatility_df = get_volatility(
            df_historical=df_hist,
            target_variable=self.target_variable
        )
        
        # Get final predictions DataFrame
        final_df = get_final_df(
            encoded_df=encoded_df,
            volatility_df=volatility_df,
            future_games=future_games,
            model=model,
            feature_names=features_list,
            encoded_feature_names=encoded_feature_names,
            measure_prediction=self.measure_prediction,
            measure_volatility=self.measure_volatility
        )

        return final_df

    def persist(self, predictions_df: pd.DataFrame) -> None:
        """
        Save predictions to storage.
        
        Args:
            predictions_df: DataFrame with predictions
        """
        logger.info(f"Persisting {self.target} predictions...")
        save_predictions(
            df=predictions_df,
            table_name=PredictionsFileName,
            mode=self.save_mode
        )
        logger.info("Predictions persisted successfully!")

    def run(self) -> pd.DataFrame:
        """
        Execute complete prediction pipeline: read → transform → predict → persist.
        
        Returns:
            DataFrame with predictions
        """
        try:
            logger.info(f"Starting prediction pipeline for {self.target}...")
            
            # 1. Load Model
            logger.info(f"Loading model from: {self.model_path}...")
            model = load_model_artifact(
                model_path=self.model_path,
                target=self.target,
                mode=self.save_mode
            )
            
            # 2. Read Data
            data_map = self.read_data()
            
            # 3. Transform Data & Make Predictions
            predictions_df = self.transform_data(data_map=data_map, model=model)

            # 4. Persist Results
            self.persist(predictions_df=predictions_df)
            
            logger.info("Prediction pipeline completed successfully!")
            return predictions_df
            
        except Exception as e:
            logger.error(f"Prediction pipeline failed: {str(e)}")
            raise
