import datetime
import pandas as pd
import numpy as np 
from typing import Any, Dict

from sklearn.preprocessing import OneHotEncoder

from common.singleton_meta import SingletonMeta
from common.io_utils import (BoxscoreFileName, AdvancedBoxscoreFileName, 
                          PlayersFileName, ScheduleFileName,
                          PredictionsFileName, save_database,
                          load_model_artifact, load_data)
from common.utils import extract_season, parse_minutes
from common.constants import key_stats_points, categorical_cols_points

class PredictionsStatsPoints(metaclass = SingletonMeta):
    """
    A class to fetch and update NBA player statistics for points predictions.
    """

    def __init__(self, save_mode: str,  date: datetime.date, model_path: str) -> None:
        """
        Initialize the NBA player statistics data object.
            Args:
                date (datetime.date): The date to start fetching stats from. Format: YYYY-MM-DD.
                days_number (int): The number of days to fetch stats for.
                save_mode (str): The mode to save data, either 'local' or 'bq' (google bigquery). 
        """
        self.date: datetime.date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        self.model_path: str = model_path
        self.SAVE_MODE: str = save_mode

    

    def read_data(self) -> Dict[str, pd.DataFrame]:
        """
        Load the necessary data from storage.
        Returns:
            Dictionary mapping file names to DataFrames.
        """
        box: pd.DataFrame = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
        adv: pd.DataFrame = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
        players: pd.DataFrame = load_data(PlayersFileName, mode=self.SAVE_MODE)
        schedule: pd.DataFrame = load_data(ScheduleFileName, mode=self.SAVE_MODE)

        return {BoxscoreFileName: box,
                AdvancedBoxscoreFileName: adv,
                PlayersFileName: players, 
                ScheduleFileName: schedule}

    def get_future_games_players(self, data_map: dict) -> pd.DataFrame:
        """
        Get future games with players who are playing in the future games.
        Args: 
            data_map (dict): A dictionary containing the loaded data.

        Returns:
            pd.DataFrame: A DataFrame with future games and players.
        """
        # Extract the future games and players DataFrame from the data map
        all_schedule_df: pd.DataFrame = data_map[ScheduleFileName]
        players_df: pd.DataFrame = data_map[PlayersFileName]

        # Filter games to include only those on the specified date
            # First, convert gameDate column to datetime
        all_schedule_df["gameDate"] = pd.to_datetime(all_schedule_df["gameDate"]).dt.date
            # Then filter by the specified date
        specific_games_df:pd.DataFrame = all_schedule_df[all_schedule_df["gameDate"] == self.date]

        # If no games are found for the selected date end the process
        if specific_games_df.empty:
            print(f"No games found for the selected date: {self.date}. Ending process.")
            exit(0)

        # Get the unique player IDs from the future games DataFrame
        players_unique: pd.DataFrame = players_df[['person_id','player_slug', 'team_id', 'position']].drop_duplicates()

        # Filter the players DataFrame to include only players who are playing 
        specific_games_df: pd.DataFrame = pd.concat([
            specific_games_df.merge(players_unique, left_on='homeTeam_teamId', right_on='team_id'),
            specific_games_df.merge(players_unique, left_on='awayTeam_teamId', right_on='team_id')
        ], ignore_index=True)
        
        # Add opponent team ID 
        specific_games_df['opponent']  = np.where(
        specific_games_df['team_id'] == specific_games_df['homeTeam_teamId'],
        specific_games_df['awayTeam_teamId'],
        specific_games_df['homeTeam_teamId']
        )

        # Add position group based on the player df 'POSITION' column
        specific_games_df['position_group'] = specific_games_df['position'].map(lambda x: 'G' if x in ('G', 'G-F') 
                                                                            else 'F' if x in ('F', 'F-G', 'F-C') 
                                                                            else 'C' if x in ('C', 'C-F') 
                                                                            else x 
                                                                            )
        

        # Add categorical features like is_home and season 
        specific_games_df['is_home']= specific_games_df['team_id'] == specific_games_df['homeTeam_teamId']
        specific_games_df['season'] = specific_games_df['gameId'].astype(str).str[1:3].astype(int) + 2000

        # Change column date type to datetime 
        specific_games_df['game_date'] = pd.to_datetime(specific_games_df['gameDate'])

        return specific_games_df


    def get_historical_stats(self, df_map) -> pd.DataFrame:
        """
        Fetch historical statistics for a given player.
        
        Args:
            player_id (int): The ID of the player to fetch stats for.
        
        Returns:
            pd.DataFrame: A DataFrame containing the player's historical stats.
        """
        # Extract dataframes from the map 
        boxscore_df: pd.DataFrame = df_map[BoxscoreFileName]
        advanced_boxscore_df: pd.DataFrame = df_map[AdvancedBoxscoreFileName]
        players_df: pd.DataFrame = df_map[PlayersFileName]

        # Filter dataframes to include only games before the specified date
        boxscore_df: pd.DataFrame = boxscore_df[pd.to_datetime(boxscore_df['game_date']).dt.date < self.date]
        advanced_boxscore_df: pd.DataFrame = advanced_boxscore_df[pd.to_datetime(advanced_boxscore_df['game_date']).dt.date < self.date]

        # From the boxscore remove rows with DNP or no minutes played
        boxscore_df: pd.DataFrame = boxscore_df[(boxscore_df['minutes'] == "0:00") | 
                                                        (boxscore_df['minutes'].notna())] 
        
        # From the Advanced boxscore remove rows with DNP or no minutes played
        advanced_boxscore_df: pd.DataFrame = advanced_boxscore_df[(boxscore_df['minutes'] == "0:00") | 
                                                        (advanced_boxscore_df['minutes'].notna())] 
        
        # Renam position column to avoid confusion with boxscore position column
        players_df: pd.DataFrame = players_df.rename(columns={'position': 'position_player'})

        # Merge player metadata (keep only relevant columns)
        full_df: pd.DataFrame = boxscore_df.merge(
            players_df[['person_id', 'height', 'weight', 'position_player']],
            left_on='personId', right_on='person_id', how='left'
        ).drop('person_id', axis=1
        )

        # Merge advanced stats, keeping only new columns
        # Find columns in advanced_boxscore that are not in boxscore_df (except keys)
        merge_keys: list = ['gameId', 'personId', 'teamId']
        adv_new_cols: list = [col for col in advanced_boxscore_df.columns if col not in boxscore_df.columns or col in merge_keys]

        # Merge advanced stats with the full_df
        full_df: pd.DataFrame = full_df.merge(
            advanced_boxscore_df[adv_new_cols],
            on=merge_keys, how='left'
        )

        return full_df
    
    def prepare_data_model(self, historical_stats_df: pd.DataFrame):
        """
        Prepare the historical statistics DataFrame for model input.
        Args:
            historical_stats_df (pd.DataFrame): The DataFrame containing historical stats.
        Returns:
            pd.DataFrame: A DataFrame with the necessary features for the model.
        """
        
        #  Create a copy of the DataFrame for processing
        df_to_process: pd.DataFrame = historical_stats_df.copy()
        
        # Parse minutes from string to float using common.utils function
        df_to_process['minutes'] = df_to_process['minutes'].apply(parse_minutes)
        
        # fill NaN values in 'position' with 'BENCH'
        df_to_process['position'] = df_to_process['position'].fillna('bench')
        
        # Create a new column 'position_group' based on 'POSITION' and 'position' 
        df_to_process['position_group'] = df_to_process.apply(
            lambda x: 'G' if x['position'] in ('G', 'bench') and x['position_player'] in ('G', 'G-F') else
                    'F' if x['position'] in ('F', 'bench') and x['position_player'] in ('F', 'F-G', 'F-C') else
                    'C' if x['position'] in ('C', 'bench') and x['position_player'] in ('C', 'C-F') else x['position'],
            axis=1
        )
        
        # Change column date type to datetime 
        df_to_process['game_date'] = pd.to_datetime(df_to_process['game_date'])
        
        # Add a season column based on the game_id using the common function
        df_to_process['season'] = df_to_process['gameId'].apply(extract_season)
        
        # Feature engineering is_home and opponent columns
        df_to_process['is_home'] = df_to_process['teamId'] == df_to_process['home_team_id']
        df_to_process['opponent'] = np.where(df_to_process['is_home'], df_to_process['visitor_team_id'], df_to_process['home_team_id'])

        #  filter out bench players
        df: pd.DataFrame = df_to_process[df_to_process['position'] != 'BENCH']

        # Compute one avg_points per group/opponent/game_date
        df_avg: pd.DataFrame = (
            df
            .groupby(['position_group','opponent','game_date'])['points']
            .mean()
            .reset_index(name='avg_points')
        )
        # Sort so tail() really pulls the last N by date
        df_avg: pd.DataFrame = df_avg.sort_values(['game_date', 'position_group', 'opponent'], ascending=[True, True, True])

        # Aggregate per (position_group, opponent)
        result: pd.DataFrame = (
            df_avg.groupby(['position_group', 'opponent'])
            .agg(
                avg_pts_opp_position_last_10=('avg_points', lambda x: x.tail(10).mean()),
                avg_pts_opp_position_last_20=('avg_points', lambda x: x.tail(20).mean()),
                avg_pts_opp_position_all=('avg_points', 'mean')
            )
            .reset_index()
        )

        # Put these stats back on final_df 
        final_df: pd.DataFrame = (
            df_to_process
            .merge(result[['position_group','opponent','avg_pts_opp_position_last_10','avg_pts_opp_position_last_20','avg_pts_opp_position_all']],
                on=['position_group','opponent'],
                how='left')
        )

        return final_df 

    @staticmethod
    def normalize_numerical_data( df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize the DataFrame by scaling numerical features.
        
        Args:
            df (pd.DataFrame): The DataFrame to normalize.
        
        Returns:
            pd.DataFrame: A normalized DataFrame.
        """
        # List of key stats to normalize
        stats_to_compute: list = list(key_stats_points.keys())

        # First, compute per-36 metrics useful for player points production
        for stat in stats_to_compute:
            per36: str = f"{stat}_per36"
            df[per36] = df[stat] / df['minutes'] * 36

        # And per-possession metrics
        for stat in stats_to_compute:
            ppp: str = f"{stat}_per_poss"
            df[ppp] = df[stat] / df['possessions']

        # Rolling the per-36 and per-possession metrics
        rolling_periods: list = [5, 10, 20]

        # Filter out engineering stats (only normalize raw stats)
        feature_cols_rolling: list[str] = [k for k, v in key_stats_points.items() if 'engineering' not in v.lower()]
        
        # Sort chronologically so rolling is time-aware
        df = df.sort_values(['personId', 'game_date'], ascending=[True, True]).copy()

        # Create rolling averages for the per-36 and per-possession metrics
        for period in feature_cols_rolling:
            for rolling_period in rolling_periods:
                per36: str = f"{period}_per36"
                per_poss: str = f"{period}_per_poss"
                df[f"{per36}_rolling_{rolling_period}"] = df.groupby('personId')[per36].transform(lambda x: x.rolling(rolling_period, min_periods=1).mean())
                df[f"{per_poss}_rolling_{rolling_period}"] = df.groupby('personId')[per_poss].transform(lambda x: x.rolling(rolling_period, min_periods=1).mean())       
            
        return df

    @staticmethod
    def encode_categorical_data(df: pd.DataFrame) -> tuple[pd.DataFrame, list ]:
        """
        Encode categorical features in the DataFrame. 
        Args:
            df (pd.DataFrame): The DataFrame to encode.
        Returns:
            pd.DataFrame: A DataFrame with encoded categorical features.
        """   
        # Prepare the encoder
        encoder: OneHotEncoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        # Fit and transform the data
        encoded_categorical: np.ndarray = encoder.fit_transform(df[categorical_cols_points])

        # Get the new feature names after encoding
        encoded_feature_names: np.ndarray = encoder.get_feature_names_out(categorical_cols_points)

        # remove original categorical features from the DataFrame
        df: pd.DataFrame = df.drop(categorical_cols_points, axis=1)

        # put the encoded categorical features back into the DataFrame
        df: pd.DataFrame = pd.concat([df, pd.DataFrame(encoded_categorical, 
                                                       columns=encoder.get_feature_names_out(categorical_cols_points), 
                                                       index=df.index)], axis=1)
    
        return df, encoded_feature_names
    
    def prepare_future_games_data(self,future_games_players_df : pd.DataFrame, normalized_historical_data: pd.DataFrame, 
                                   feature_encoded_names)-> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare the future games data for predictions.
        Args:
            future_games_players_df (pd.DataFrame): The DataFrame with future games and players, encoded. 
            normalized_historical_data (pd.DataFrame): The DataFrame with normalized historical data.
            feature_encoded_names (list): List of encoded feature names.
        Returns:
            pd.DataFrame: A DataFrame with future games data ready for predictions.
        """
        # Get the latest stats for each player from final_df
        latest_stats: pd.DataFrame = (
            normalized_historical_data.sort_values('game_date')
            .groupby('personId')
            .tail(1)
        )

        # Define feature columns to merge
        final_features = []
        rolling_periods = [5, 10, 20]
        feature_cols_rolling = {k: v for k, v in key_stats_points.items() if 'engineering' not in v.lower()}
        for rolling_period in rolling_periods:  
            final_features.extend([
                f"{s}_per36_rolling_{rolling_period}" for s in feature_cols_rolling
            ])
            final_features.extend([
                f"{s}_per_poss_rolling_{rolling_period}" for s in feature_cols_rolling
            ])

        # Add historical averages (engineering stats) - per36 first, then per_poss
        engineering_stats: list = [k for k, v in key_stats_points.items() if 'engineering' in v.lower()]
        for stat in engineering_stats:
            final_features.append(f"{stat}_per36")
        
        for stat in engineering_stats:
            final_features.append(f"{stat}_per_poss")

        # Add encoded categorical feature names
        final_features.extend(feature_encoded_names)

        # Merge stats into future_games_long without duplicating columns
        # Drop columns from latest_stats that already exist in future_games_players_df except the join key
        join_key: str = 'person_id'
        duplicate_cols: set[str] = set(future_games_players_df.columns) & set(latest_stats.columns)
        duplicate_cols.discard(join_key)
        latest_stats_nodup: pd.DataFrame = latest_stats.drop(columns=duplicate_cols, errors='ignore')

        future_games_long: pd.DataFrame = future_games_players_df.merge(
            latest_stats_nodup,
            left_on='person_id',
            right_on='personId',
            how='inner'
        )

        # Fill NaN values with 0 for prediction    
        X_pred: pd.DataFrame = future_games_long[final_features].fillna(0)
        
        return future_games_long, X_pred

    def get_predictions(self,future_games_df ,X_pred : pd.DataFrame, model):
        """
        Predict points using the loaded model and transformed data.
        Args:
            transformed_data (pd.DataFrame): The DataFrame with transformed data ready for predictions.
            model: The loaded prediction model.
        Returns:
            pd.DataFrame: A DataFrame with predictions for each player.
        """
        # Ensure the model is loaded
        if model is None:
            raise ValueError("Model is not loaded. Please load the model before making predictions.")

        # Resolve predictor in case the loaded artifact is a dict wrapping the model
        predictor = model
        if isinstance(model, dict):
            # Try common keys
            for key in ('model', 'estimator', 'best_estimator_', 'regressor', 'clf', 'pipeline'):
                if key in model and hasattr(model[key], 'predict'):
                    predictor = model[key]
                    break
            else:
                # Fallback: any value with a predict method
                for value in model.values():
                    if hasattr(value, 'predict'):
                        predictor = value
                        break
                else:
                    raise AttributeError("Loaded model artifact is a dict without any object exposing a 'predict' method.")

        # Make predictions using the predictor
        predictions: np.ndarray = predictor.predict(X_pred)

        # Create a DataFrame with predictions
        predictions_df = pd.DataFrame({
            'gameId': future_games_df['gameId'].values,
            'gameDate': future_games_df['gameDate'].values,
            'teamId': future_games_df['team_id'].values,
            'opponentId': future_games_df['opponent'].values,
            'personId': future_games_df['person_id'].values,
            'fullName': future_games_df['player_slug'].values,
            'predictedPoints': predictions
        })
        
        return predictions_df

    def transform_data(self, data_map: dict):
        """
        Transform the loaded data into a format suitable for predictions.
        
        Args:
            data_map (dict): A dictionary containing the loaded data.
        
        Returns:
            pd.DataFrame: A DataFrame with transformed data ready for predictions.
        """
        # Get the list of players who are playing in the future games 
        future_games_players: pd.DataFrame = self.get_future_games_players(data_map) 

        # Get the historical statistics for the players
        historical_stats_df: pd.DataFrame = self.get_historical_stats(data_map)

        # Feature engineering to prepare the data for the model
        historical_data_model: pd.DataFrame = self.prepare_data_model(historical_stats_df)

        # Normalize numerical data
        normalized_data: pd.DataFrame = self.normalize_numerical_data(historical_data_model)
        
        # Encode categorical features for future games players
        future_encoded_dataframe, feature_encoded_names = self.encode_categorical_data(future_games_players)

        # Prepared dataframe 
        future_games_long_df, X_pred_df = self.prepare_future_games_data(future_encoded_dataframe,
                                                                          normalized_data, feature_encoded_names)
        
        return future_games_long_df, X_pred_df
    
    def run(self) -> pd.DataFrame:
        """
        Run the process to fetch and update NBA player statistics for points predictions.
        
        Returns:
            pd.DataFrame: A DataFrame with player statistics ready for predictions.
        """
        # Load the model
        model: Any = load_model_artifact(self.model_path, mode=self.SAVE_MODE)
        
        # Load the data
        data_map: dict = self.read_data()
        
        # Transform the data
        future_games_long_df, X_pred_df = self.transform_data(data_map)
        
        # Get predictions
        predictions_df: pd.DataFrame = self.get_predictions(future_games_long_df, X_pred_df, model)

        # Save the predictions to a CSV file
        save_database(predictions_df,PredictionsFileName, 
                      mode=self.SAVE_MODE,
                      write_disposition="WRITE_APPEND")
        
        return predictions_df