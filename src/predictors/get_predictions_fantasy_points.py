# Import necessary libraries
import logging
import datetime
import pandas as pd
import numpy as np
from typing import Dict, Any
from common.singleton_meta import SingletonMeta
from common.io_utils import (BoxscoreFileName, AdvancedBoxscoreFileName, 
                          PlayersFileName, PredictionsFileName, ScheduleFileName,
                           load_data, save_database)
from common.model_utils import load_model_artifact
from common.constants import key_stats_fantasy, categorical_cols_fantasy, target_variable_fantasy, rolling_windows_fantasy
from common.feature_engineering import (
    merge_data, preprocess_data, create_historical_features, 
    normalize_features, compute_rolling_stats, encode_categorical_features,
    get_feature_cols, get_volatility, get_final_df, get_rest_days
)
from src.targets.fantasy_points import compute_fantasy_points

class PredictionsFantasyPoints(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA player statistics for fantasy points predictions.
    """

    def __init__(self, save_mode: str, date: str, model_path: str, target: str) -> None:
        """
        Initialize the NBA player predictions for fantasy points object.
            Args:
                save_mode (str): The mode to save data, either 'local' or 'bq' (google bigquery). 
                date (datetime.date): The date to start fetching stats from. Format: YYYY-MM-DD.
                model_path (str): The path to the trained model for predictions.
                target (str): The target variable for predictions ('points').
        """
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.date: datetime.date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        self.model_path: str = model_path
        self.SAVE_MODE: str = save_mode
        self.target: str = target

    def read_data(self) -> Dict[str, pd.DataFrame]:
        """
        Function to read necessary data from storage.
        Returns:
            Dict[str, pd.DataFrame]: A dictionary containing the loaded dataframes.
        """
        # Load data
        box: pd.DataFrame = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
        adv: pd.DataFrame = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
        players: pd.DataFrame = load_data(PlayersFileName, mode=self.SAVE_MODE)
        schedule: pd.DataFrame = load_data(ScheduleFileName, mode=self.SAVE_MODE)

        return {BoxscoreFileName: box, AdvancedBoxscoreFileName: adv, 
                PlayersFileName: players, ScheduleFileName: schedule}

    def get_future_games_players(self, data_map: dict) -> pd.DataFrame:
        """
        Get future games with player information for the specified date.
        Args:
            data_map (dict): A dictionary containing the loaded dataframes.
        Returns:
            pd.DataFrame: A DataFrame containing future games with player info.
        """
        # Extract schedule and players data
        all_schedule_df: pd.DataFrame = data_map[ScheduleFileName]
        players_df: pd.DataFrame = data_map[PlayersFileName]
        
        # Filter schedule for the specific date
        all_schedule_df["gameDate"] = pd.to_datetime(all_schedule_df["gameDate"]).dt.date
        specific_games_df: pd.DataFrame = all_schedule_df[all_schedule_df["gameDate"] == self.date]

        # Handle case with no games
        if specific_games_df.empty:
            print(f"No games found for the selected date: {self.date}. Ending process.")
            exit(0)

        # Prepare players data
        players_unique: pd.DataFrame = players_df[['person_id','player_slug', 'team_id', 'position']].drop_duplicates()

        # Cross join players with specific games
        specific_games_df: pd.DataFrame = pd.concat([
            specific_games_df.merge(players_unique, left_on='homeTeam_teamId', right_on='team_id'),
            specific_games_df.merge(players_unique, left_on='awayTeam_teamId', right_on='team_id')
        ], ignore_index=True)
        
        # Add opponent team id column
        specific_games_df['opponent'] = np.where(
            specific_games_df['team_id'] == specific_games_df['homeTeam_teamId'],
            specific_games_df['awayTeam_teamId'],
            specific_games_df['homeTeam_teamId']
        )

        # Add position group column
        specific_games_df['position_group'] = specific_games_df['position'].map(
            lambda x: 'G' if x in ('G', 'G-F') else 'F' if x in ('F', 'F-G', 'F-C') else 'C' if x in ('C', 'C-F') else x
        )
        # Additional columns needed for feature engineering
        specific_games_df['is_home'] = specific_games_df['team_id'] == specific_games_df['homeTeam_teamId']
        specific_games_df['season'] = specific_games_df['gameId'].astype(str).str[1:3].astype(int) + 2000
        # Convert game_date to datetime
        specific_games_df['game_date'] = pd.to_datetime(specific_games_df['gameDate'])

        # Calculate rest days
        team_last_game: dict = {}
        past_schedule: pd.DataFrame = all_schedule_df[all_schedule_df["gameDate"] < self.date].sort_values("gameDate")
        
        # For each team, find the last game date before the prediction date
        for team_id in specific_games_df['team_id'].unique():
            team_games: pd.DataFrame = past_schedule[
                (past_schedule['homeTeam_teamId'] == team_id) | 
                (past_schedule['awayTeam_teamId'] == team_id)
            ]
            if not team_games.empty:
                last_date: pd.Timestamp = team_games.iloc[-1]['gameDate']
                days_diff: int = (self.date - last_date).days
                team_last_game[team_id]= min(days_diff, 7)
            else:
                team_last_game[team_id]= 3
        
        specific_games_df['rest_days'] = specific_games_df['team_id'].map(team_last_game)

        return specific_games_df

    def transform_data(self, data_map: dict, model: Any) -> tuple:
        """
        Function to transform data for predictions.
        Args:
            data_map (dict): A dictionary containing the loaded dataframes.
            model (Any): The trained model for predictions.
        Returns:
            tuple: A tuple containing the transformed future games DataFrame and the feature matrix for predictions.
        """
        # Load historical data
        box: pd.DataFrame = data_map[BoxscoreFileName]
        adv: pd.DataFrame = data_map[AdvancedBoxscoreFileName]

        # Filter historical data to be strictly before prediction date
        box: pd.DataFrame = box[pd.to_datetime(box['game_date']).dt.date < self.date]
        adv: pd.DataFrame = adv[pd.to_datetime(adv['game_date']).dt.date < self.date]
        
        # Merge & Preprocess Historical
        df_hist: pd.DataFrame = merge_data(box, adv, data_map[PlayersFileName])
        df_hist: pd.DataFrame = preprocess_data(df_hist)
        
        # Calculate Fantasy Points for Historical Data
        df_hist: pd.DataFrame = compute_fantasy_points(df_hist)

        # Create Historical Features
        df_hist: pd.DataFrame = create_historical_features(df_hist, target_col=target_variable_fantasy)
        
        # Calculate Rest Days
        rest_days_df: pd.DataFrame = get_rest_days(players_df=data_map[PlayersFileName],
                                              boxscore_df=box,
                                              date=self.date
                                              )

        # Merge rest days into historical data
        df_hist = df_hist.merge(rest_days_df, on=['personId'], how='left')
        # Normalize and Compute Rolling Stats
        df_hist: pd.DataFrame = normalize_features(df_hist, key_stats_fantasy)
        df_hist: pd.DataFrame = compute_rolling_stats(df_hist, key_stats_fantasy, windows=rolling_windows_fantasy)
        
        # Prepare Future Data
        future_games: pd.DataFrame = self.get_future_games_players(data_map)
        
        # Get future columns
        features_list: list[str] = get_feature_cols(
            key_stats=key_stats_fantasy,
            rolling_periods=rolling_windows_fantasy)

        # Encode Categoricals
        encoded_df, encoded_feature_names = encode_categorical_features(df=df_hist, 
                                                                categorical_cols=categorical_cols_fantasy)
        
        volatility_df = get_volatility(df_historical=df_hist,
                                       target_variable=target_variable_fantasy)
        
        # Get final df
        final_df: pd.DataFrame = get_final_df(
            encoded_df=encoded_df,
            volatility_df=volatility_df,
            future_games=future_games,
            model=model,
            feature_names=features_list,
            encoded_feature_names=encoded_feature_names
        )

        return final_df

    def persist_data(self, predictions_df: pd.DataFrame) -> None:
        """
        Function to persist predictions data.
        Args:
            predictions_df (pd.DataFrame): A DataFrame containing the predictions.
        """
        self.logger.info(f"Persisting fantasy points predictions data into {PredictionsFileName}...")
        # Save the combined DataFrame locally or to BigQuery
        save_database( df=predictions_df,
                       table_name=PredictionsFileName,
                        mode= self.SAVE_MODE, 
                        write_disposition="WRITE_APPEND",
                        autodetect_schema=True
                        )
        self.logger.info(f"Fantasy points predictions data persisted successfully into {PredictionsFileName}.")

    def run(self) -> pd.DataFrame:
        """
        Function to run the fantasy points predictions process.
        Returns:
            pd.DataFrame: A DataFrame containing the fantasy points predictions.
        """
        # Load Model
        self.logger.info(f"Loading model from path: {self.model_path}...")
        model: Any = load_model_artifact(model_path=self.model_path,
                                            target=self.target,
                                             mode=self.SAVE_MODE
                                             )
        
        # Load Data
        self.logger.info("Loading necessary data for predictions...")
        data_map: dict = self.read_data()
        
        # Transform Data
        self.logger.info("Transforming data for predictions...")
        transformed_df: pd.DataFrame = self.transform_data(data_map=data_map, model=model)

        # Persist Data
        self.logger.info("Persisting predictions data...")
        self.persist_data(predictions_df=transformed_df)