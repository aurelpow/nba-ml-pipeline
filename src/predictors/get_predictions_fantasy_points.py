import datetime
import pandas as pd
import numpy as np
from typing import Dict
from common.singleton_meta import SingletonMeta
from common.io_utils import (BoxscoreFileName, AdvancedBoxscoreFileName, 
                          PlayersFileName, ScheduleFileName,
                          load_model_artifact, load_data, save_database)
from common.utils import extract_season, parse_minutes
from common.constants import key_stats_fantasy, categorical_cols_fantasy, target_variable_fantasy, rolling_windows_fantasy
from common.feature_engineering import (
    merge_data, preprocess_data, create_historical_features, 
    normalize_features, compute_rolling_stats, encode_categorical_features,
    get_feature_cols
)
from sklearn.preprocessing import OneHotEncoder

class PredictionsFantasyPoints(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA player statistics for fantasy points predictions.
    """

    def __init__(self, save_mode: str, date: str, model_path: str) -> None:
        self.date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        self.model_path = model_path
        self.SAVE_MODE = save_mode

    def read_data(self) -> Dict[str, pd.DataFrame]:
        box = load_data(BoxscoreFileName, mode=self.SAVE_MODE)
        adv = load_data(AdvancedBoxscoreFileName, mode=self.SAVE_MODE)
        players = load_data(PlayersFileName, mode=self.SAVE_MODE)
        schedule = load_data(ScheduleFileName, mode=self.SAVE_MODE)
        return {BoxscoreFileName: box, AdvancedBoxscoreFileName: adv, 
                PlayersFileName: players, ScheduleFileName: schedule}

    def get_future_games_players(self, data_map: dict) -> pd.DataFrame:
        all_schedule_df = data_map[ScheduleFileName]
        players_df = data_map[PlayersFileName]

        all_schedule_df["gameDate"] = pd.to_datetime(all_schedule_df["gameDate"]).dt.date
        specific_games_df = all_schedule_df[all_schedule_df["gameDate"] == self.date]

        if specific_games_df.empty:
            print(f"No games found for the selected date: {self.date}. Ending process.")
            exit(0)

        players_unique = players_df[['person_id','player_slug', 'team_id', 'position']].drop_duplicates()

        specific_games_df = pd.concat([
            specific_games_df.merge(players_unique, left_on='homeTeam_teamId', right_on='team_id'),
            specific_games_df.merge(players_unique, left_on='awayTeam_teamId', right_on='team_id')
        ], ignore_index=True)
        
        specific_games_df['opponent'] = np.where(
            specific_games_df['team_id'] == specific_games_df['homeTeam_teamId'],
            specific_games_df['awayTeam_teamId'],
            specific_games_df['homeTeam_teamId']
        )

        # Add position group (reusing logic from preprocess_data would be better but this is specific to future games structure)
        # Actually, preprocess_data expects 'position_player' which comes from merge.
        # Here we have 'position' from players_unique.
        specific_games_df['position_group'] = specific_games_df['position'].map(
            lambda x: 'G' if x in ('G', 'G-F') else 'F' if x in ('F', 'F-G', 'F-C') else 'C' if x in ('C', 'C-F') else x
        )

        specific_games_df['is_home'] = specific_games_df['team_id'] == specific_games_df['homeTeam_teamId']
        specific_games_df['season'] = specific_games_df['gameId'].astype(str).str[1:3].astype(int) + 2000
        specific_games_df['game_date'] = pd.to_datetime(specific_games_df['gameDate'])

        # Calculate rest days
        team_last_game = {}
        past_schedule = all_schedule_df[all_schedule_df["gameDate"] < self.date].sort_values("gameDate")
        
        for team_id in specific_games_df['team_id'].unique():
            team_games = past_schedule[
                (past_schedule['homeTeam_teamId'] == team_id) | 
                (past_schedule['awayTeam_teamId'] == team_id)
            ]
            if not team_games.empty:
                last_date = team_games.iloc[-1]['gameDate']
                days_diff = (self.date - last_date).days
                team_last_game[team_id] = min(days_diff, 7)
            else:
                team_last_game[team_id] = 3
        
        specific_games_df['rest_days'] = specific_games_df['team_id'].map(team_last_game)

        return specific_games_df

    def run(self) -> pd.DataFrame:
        # 1. Load Model
        artifact = load_model_artifact(self.model_path, mode=self.SAVE_MODE)
        model = artifact['model']
        feature_cols = artifact['feature_cols']
        
        # 2. Load Data
        data_map = self.read_data()
        
        # 3. Prepare Historical Data
        # Filter historical data to be strictly before prediction date
        box = data_map[BoxscoreFileName]
        box = box[pd.to_datetime(box['game_date']).dt.date < self.date]
        adv = data_map[AdvancedBoxscoreFileName]
        adv = adv[pd.to_datetime(adv['game_date']).dt.date < self.date]
        
        # Merge & Preprocess Historical
        df_hist = merge_data(box, adv, data_map[PlayersFileName])
        df_hist = preprocess_data(df_hist)
        
        # Feature Engineering on Historical
        # Note: We need to compute the target for historical data to generate historical features
        from src.targets.fantasy_points import compute_fantasy_points
        df_hist = compute_fantasy_points(df_hist)
        
        df_hist = create_historical_features(df_hist, target_col=target_variable_fantasy)
        df_hist = normalize_features(df_hist, key_stats_fantasy)
        df_hist = compute_rolling_stats(df_hist, key_stats_fantasy, windows=rolling_windows_fantasy)
        
        # 4. Prepare Future Data
        future_games = self.get_future_games_players(data_map)
        
        # 5. Encode Categoricals
        # Fit encoder on historical data
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoder.fit(df_hist[categorical_cols_fantasy])
        encoded_feature_names = encoder.get_feature_names_out(categorical_cols_fantasy).tolist()
        
        # Transform future data
        future_encoded = encoder.transform(future_games[categorical_cols_fantasy])
        future_encoded_df = pd.DataFrame(future_encoded, columns=encoded_feature_names, index=future_games.index)
        future_games = pd.concat([future_games.drop(categorical_cols_fantasy, axis=1), future_encoded_df], axis=1)
        
        # 6. Merge Latest Stats to Future Games
        # Get latest stats for each player
        latest_stats = df_hist.sort_values('game_date').groupby('personId').tail(1)
        
        # Calculate volatility (std dev of fantasy points over last 10 games)
        # We need to do this on the full history before taking the tail
        df_hist_sorted = df_hist.sort_values(['personId', 'game_date'])
        df_hist_sorted['fantasy_volatility'] = df_hist_sorted.groupby('personId')[target_variable_fantasy].transform(
            lambda x: x.rolling(10, min_periods=5).std()
        )
        
        # Get the latest volatility for each player
        # reset_index() might not be needed if personId is the index after groupby, but let's be safe
        # If groupby('personId') is used, personId becomes the index. tail(1) keeps it as index.
        # So reset_index() moves personId back to a column.
        latest_volatility = df_hist_sorted.groupby('personId')['fantasy_volatility'].tail(1).reset_index()
        
        # However, if the original df_hist_sorted index was not personId, reset_index() might keep the original index 
        # and personId might still be a column or index depending on how groupby was called.
        # Let's inspect what groupby(...).tail(1) returns. It returns a DataFrame with the same index as original.
        # So we need to ensure we have personId available for merge.
        
        latest_volatility = df_hist_sorted.sort_values('game_date').groupby('personId').tail(1)[['personId', 'fantasy_volatility']]
        
        latest_stats = latest_stats.merge(latest_volatility, on='personId', how='left')

        # Columns to merge (numeric features)
        numeric_feats = get_feature_cols(key_stats_fantasy, rolling_periods=rolling_windows_fantasy)
        # Remove encoded cols from numeric_feats if they are there (get_feature_cols doesn't include them)
        
        # Merge
        # We need to be careful not to duplicate columns.
        # latest_stats has all features.
        cols_to_merge = [c for c in numeric_feats if c in latest_stats.columns]
        cols_to_merge.append('personId')
        cols_to_merge.append('fantasy_volatility') # Add volatility to merge
        
        future_games_long = future_games.merge(
            latest_stats[cols_to_merge],
            left_on='person_id',
            right_on='personId',
            how='inner'
        )
        
        # 7. Predict
        X_pred = future_games_long[feature_cols].fillna(0)
        predictions = model.predict(X_pred)
        
        predictions_df = pd.DataFrame({
            'gameId': future_games_long['gameId'].values,
            'gameDate': future_games_long['gameDate'].values,
            'teamId': future_games_long['team_id'].values,
            'opponentId': future_games_long['opponent'].values,
            'personId': future_games_long['personId'].values,
            'player_slug': future_games_long['player_slug'].values,
            'predictedFantasyPoints': np.round(predictions, 1),
            'fantasyVolatility': np.round(future_games_long['fantasy_volatility'].fillna(0), 1) # Add to output
        })
        
        # Show 20 highest predictions
        top_predictions = predictions_df.sort_values(by='predictedFantasyPoints', ascending=False).head(20)
        print("Top 20 Fantasy Points Predictions:")
        print(top_predictions)
        # Save
        filename = f"fantasy_points_predictions_{self.date}.csv"
        if self.SAVE_MODE == 'local':
            predictions_df.to_csv(f"databases/{filename}", index=False)
        else:
            save_database(predictions_df, "nba_fantasy_predictions", mode=self.SAVE_MODE, write_disposition="WRITE_APPEND")
            
        return predictions_df
