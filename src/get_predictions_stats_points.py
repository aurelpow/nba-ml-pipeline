import datetime
import pandas as pd
import numpy as np 

from sklearn.preprocessing import OneHotEncoder

from common.singleton_meta import SingletonMeta
from common.io_utils import (BoxscoreFileName, AdvancedBoxscoreFileName, 
                          PlayersFileName, ScheduleFileName,
                          PredictionsFileName, save_database,
                          load_model_artifact)
from common.utils import extract_season, parse_minutes

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
        self.keys_points_stats : list[str] = [
            'usagePercentage',
            'trueShootingPercentage',
            'effectiveFieldGoalPercentage',
            'offensiveRating',
            'freeThrowsMade',
            'threePointersMade',
            'fieldGoalsMade',
            'avg_pts_opp_position_all',
            'avg_pts_opp_position_last_10',
            'avg_pts_opp_position_last_20'
        ]
    
    def load_data(self) -> dict: 
        """
        Load the necessary data for predictions.
        This method should be implemented to fetch the required data.
        """
        if self.SAVE_MODE == "local":
            boxscore_df = pd.read_csv(f"databases/{BoxscoreFileName}.csv", low_memory=False)
            advanced_boxscore_df = pd.read_csv(f"databases/{AdvancedBoxscoreFileName}.csv", low_memory=False)
            players_df = pd.read_csv(f"databases/{PlayersFileName}.csv")
            scheduled_df = pd.read_csv(f"databases/{ScheduleFileName}.csv") 

            return {"simple_boxscore" : boxscore_df,
                    "advanced_boxscore" : advanced_boxscore_df,
                    "players" : players_df,
                    "schedule" : scheduled_df}
        elif self.SAVE_MODE == "bq":
            from common.io_utils import load_data
            boxscore_df = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
            advanced_boxscore_df = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
            players_df = load_data(PlayersFileName, mode=self.SAVE_MODE)
            schedule_df = load_data(ScheduleFileName, mode=self.SAVE_MODE)

            return {"simple_boxscore" : boxscore_df,
                    "advanced_boxscore" : advanced_boxscore_df,
                    "players" : players_df,
                    "schedule" : schedule_df}
    

    def get_future_games_players(self, data_map : dict):
        """
        Get future games with players who are playing in the future games.
        Args: 
            data_map (dict): A dictionary containing the loaded data.
            Returns:
                pd.DataFrame: A DataFrame with future games and players.
        """
        # Extract the future games and players DataFrame from the data map
        all_schedule_df: pd.DataFrame = data_map["schedule"]
        players_df: pd.DataFrame = data_map["players"]

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
        players_unique = players_df[['person_id','player_slug', 'team_id', 'position']].drop_duplicates()

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


    def get_historical_stats(self, df_map):
        """
        Fetch historical statistics for a given player.
        
        Args:
            player_id (int): The ID of the player to fetch stats for.
        
        Returns:
            pd.DataFrame: A DataFrame containing the player's historical stats.
        """
        # Extract dataframes from the map 
        boxscore_df: pd.DataFrame = df_map["simple_boxscore"]
        advanced_boxscore_df: pd.DataFrame = df_map["advanced_boxscore"]
        players_df: pd.DataFrame = df_map["players"]

        # From the boxscore remove rows with DNP or no minutes played
        boxscore_df: pd.DataFrame = boxscore_df[(boxscore_df['minutes'] == "0:00") | 
                                                        (boxscore_df['minutes'].notna())] 
        
        # From the Advanced boxscore remove rows with DNP or no minutes played
        advanced_boxscore_df: pd.DataFrame = advanced_boxscore_df[(boxscore_df['minutes'] == "0:00") | 
                                                        (advanced_boxscore_df['minutes'].notna())] 
        
        # Renam position column to avoid confusion with boxscore position column
        players_df: pd.DataFrame = players_df.rename(columns={'position': 'position_player'})

        # Merge player metadata (keep only relevant columns)
        full_df = boxscore_df.merge(
            players_df[['person_id', 'height', 'weight', 'position_player']],
            left_on='personId', right_on='person_id', how='left'
        ).drop('person_id', axis=1
        )

        # Merge advanced stats, keeping only new columns
        # Find columns in advanced_boxscore that are not in boxscore_df (except keys)
        merge_keys = ['gameId', 'personId', 'teamId']
        adv_new_cols = [col for col in advanced_boxscore_df.columns if col not in boxscore_df.columns or col in merge_keys]

        # Merge advanced stats with the full_df
        full_df = full_df.merge(
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
        df_to_process = historical_stats_df.copy()
        
        df_to_process['minutes'] = df_to_process['minutes'].apply(parse_minutes)
        
        # fill NaN values in 'position' witch 'BENCH'
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
        df = df_to_process[df_to_process['position'] != 'BENCH']

        # Compute one avg_points per group/opponent/game_date
        df_avg = (
            df
            .groupby(['position_group','opponent','game_date'])['points']
            .mean()
            .reset_index(name='avg_points')
        )
        # Sort so tail() really pulls the last N by date
        df_avg = df_avg.sort_values(['position_group','opponent','game_date'])

        # Aggregate per (position_group, opponent)
        result = (
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

    def normalize_numerical_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize the DataFrame by scaling numerical features.
        
        Args:
            df (pd.DataFrame): The DataFrame to normalize.
        
        Returns:
            pd.DataFrame: A normalized DataFrame.
        """
        
        # First, compute per-36 metrics useful for player points production
        for stat in self.keys_points_stats:
            per36 = f"{stat}_per36"
            df[per36] = df[stat] / df['minutes'] * 36

        # And per-possession metrics
        for stat in self.keys_points_stats:
            ppp = f"{stat}_per_poss"
            df[ppp] = df[stat] / df['possessions']

        # Rolling the per-36 and per-possesion metrics 
        rolling_periods = [5, 10, 20]
        
        # remove avg_pts oppsition columns from rolling calculations 
        feature_cols_rolling = [col for col in self.keys_points_stats if not col.startswith('avg_pts_opp_position')]

        # Create rolling averages for the per-36 and per-possession metrics
        for period in feature_cols_rolling:
            for rolling_period in rolling_periods:
                per36 = f"{period}_per36"
                per_poss = f"{period}_per_poss"
                df[f"{per36}_rolling_{rolling_period}"] = df.groupby('personId')[per36].transform(lambda x: x.rolling(rolling_period, min_periods=1).mean())
                df[f"{per_poss}_rolling_{rolling_period}"] = df.groupby('personId')[per_poss].transform(lambda x: x.rolling(rolling_period, min_periods=1).mean())       
            
        return df    

    @staticmethod
    def encode_categorical_data(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
        """
        Encode categorical features in the DataFrame. 
        Args:
            df (pd.DataFrame): The DataFrame to encode.
        Returns:
            pd.DataFrame: A DataFrame with encoded categorical features.
        """   
        # Create categorical features 
        categorical_feats = ['is_home', 'season']

        # Encode categorical features using one-hot encoding
            # prepare the encoder
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
            # fit and transform the data
        encoded_categorical = encoder.fit_transform(df[categorical_feats])

        # Get the new feature names after encoding
        encoded_feature_names = encoder.get_feature_names_out(categorical_feats)

        # remove original categorical features from the DataFrame
        df = df.drop(categorical_feats, axis=1)

        # put the encoded categorical features back into the DataFrame
        df = pd.concat([df, pd.DataFrame(encoded_categorical, columns=encoder.get_feature_names_out(categorical_feats))], axis=1)
    
        return df, encoded_feature_names
    
    def prepare_future_games_data(self,future_games_players_df : pd.DataFrame, encoded_data: pd.DataFrame, 
                                   feature_encoded_names)-> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare the future games data for predictions.
        Args:
            data_map (dict): A dictionary containing the loaded data.
        Returns:
            pd.DataFrame: A DataFrame with future games data ready for predictions.
        """
        # Get the latest stats for each player from final_df
        latest_stats = (
            encoded_data.sort_values('game_date')
            .groupby('personId')
            .tail(1)
        )

        # Define feature columns to merge
        numeric_feats = []
        rolling_periods = [5, 10, 20]
        feature_cols_rolling = [col for col in self.keys_points_stats if not col.startswith('avg_pts_opp_position')]
        for rolling_period in rolling_periods:  
            numeric_feats.extend([
                f"{s}_per36_rolling_{rolling_period}" for s in feature_cols_rolling
            ])
            numeric_feats.extend([
                f"{s}_per_poss_rolling_{rolling_period}" for s in feature_cols_rolling
            ])

        # Add the average points opponent position columns
        numeric_feats.extend([
            'avg_pts_opp_position_last_10_per36',
            'avg_pts_opp_position_last_20_per36',
            'avg_pts_opp_position_all_per36',
            'avg_pts_opp_position_last_10_per_poss',
            'avg_pts_opp_position_last_20_per_poss',
            'avg_pts_opp_position_all_per_poss'
        ])

        # Select only the necessary columns for prediction
        numeric_feats.extend(feature_encoded_names)

        # Merge stats into future_games_long without duplicating columns
        # Drop columns from latest_stats that already exist in future_games_players_df except the join key
        join_key = 'person_id'
        duplicate_cols = set(future_games_players_df.columns) & set(latest_stats.columns)
        duplicate_cols.discard(join_key)
        latest_stats_nodup = latest_stats.drop(columns=duplicate_cols, errors='ignore')

        future_games_long = future_games_players_df.merge(
            latest_stats_nodup,
            left_on='person_id',
            right_on='personId',
            how='inner'
        )

        print(list(future_games_long.columns))
        # Fill NaN values with 0 for prediction    
        X_pred = future_games_long[numeric_feats].fillna(0)

        return future_games_long ,X_pred

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

        # Make predictions using the model
        predictions = model.predict(X_pred)

        # Create a DataFrame with predictions
        predictions_df: pd.DataFrame = pd.DataFrame({
            'gameId': future_games_df['gameId'],
            'gameDate': future_games_df['gameDate'],
            'teamId': future_games_df['team_id'],
            'opponentId': future_games_df['opponent'],
            'personId': future_games_df['person_id'],
            'fullName' : future_games_df['player_slug'],
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
        
        # Encode categorical features and prepare the final dataframe for predictions
        encoded_dataframe, feature_encoded_names = self.encode_categorical_data(normalized_data)

        # Prepared dataframe 
        future_games_long_df, X_pred_df = self.prepare_future_games_data(future_games_players,
                                                                          encoded_dataframe, feature_encoded_names)
        
        return future_games_long_df, X_pred_df
    
    def run(self) -> pd.DataFrame:
        """
        Run the process to fetch and update NBA player statistics for points predictions.
        
        Returns:
            pd.DataFrame: A DataFrame with player statistics ready for predictions.
        """
        # Load the model
        model = load_model_artifact(self.model_path, mode=self.SAVE_MODE)
        
        # Load the data
        data_map = self.load_data()
        
        # Transform the data
        future_games_long_df, X_pred_df = self.transform_data(data_map)
        
        # Get predictions
        predictions_df = self.get_predictions(future_games_long_df, X_pred_df, model)

        # Save the predictions to a CSV file
        save_database(predictions_df,PredictionsFileName, 
                      mode=self.SAVE_MODE,
                      write_disposition="WRITE_APPEND")
        
        return predictions_df