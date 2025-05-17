import pandas as pd
import joblib
import datetime

from common.utils import TeamsFileName, BoxscoreFileName, databases_path, PlayersFileName

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_absolute_error
import os


class NbaMLTrainer:
    """
    A class to train and save a machine learning model for NBA data.
    """
    def __init__(self, season: str,  model_dir="models"):
        self.model_dir = model_dir
        self.window_sizes = [3, 5, 10] # Rolling window sizes for features 
        self.features = [
            # Player form
            'minutes', 'points', 'reboundsTotal', 'assists',
            'steals', 'blocks', 'turnovers',
            'fieldGoalsMade', 'freeThrowsMade',
            'fieldGoalsMissed', 'freeThrowsMissed',
            'rolling_5_points', 'rolling_5_assists',
            'rolling_5_reboundsTotal', 'rolling_5_steals',
            'rolling_5_blocks', 'rolling_5_turnovers',
            'rolling_5_fieldGoalsMade', 'rolling_5_freeThrowsMade',
            'rolling_5_fieldGoalsMissed', 'rolling_5_freeThrowsMissed',
            'rolling_5_minutes',
            
            # Context
            'opp_fp_allowed', 'pos_opp_fp_allowed', 'season_avg_fp',
            'days_rest', 'is_home',
            
            # Position
            'POSITION_player',
        ]
        self.target = 'FP'
        self.current_season = season


        def _Load_data(self) -> dict:
            """
            Load the player, team and boxscore data from the specified file path.
            Args:
                file_path (str): The path to the CSV file containing the data.
                Returns:
                    dict: A dictionary containing the loaded data.
            """
            boxscore_df = pd.read_csv(f"{databases_path}{BoxscoreFileName}.csv")
            teams_df = pd.read_csv(f"{databases_path}{TeamsFileName}.csv")
            players_df = pd.read_csv(f"{databases_path}{PlayersFileName}_{self.current_season}.csv")

            return {
                'boxscore': boxscore_df,
                'teams': teams_df,
                'players': players_df
            }
    
    def _preprocess_data(self, data_loaded: dict) -> pd.DataFrame:
        """
        Preprocess the loaded data to prepare it for training.
        Args:
            data_Loaded (dict): A dictionary containing the loaded data.
            Returns:
                pd.DataFrame: A DataFrame containing the preprocessed data.
        """
        boxscore_df = data_loaded['boxscore']
        players_df = data_loaded['players']

        # Merge the DataFrames
        df: pd.DataFrame = boxscore_df.merge(
            players_df[['PERSON_ID', 'PLAYER_SLUG', 'POSITION', 'HEIGHT']],
            left_on='personId',
            right_on='PERSON_ID',
            how='left'
            ).drop('PERSON_ID', axis=1)
        
        # Handle missing values
        df['minutes'] = df['minutes'].apply(lambda x: float(x.split(':')[0]) if pd.notnull(x) else 0)
        df['position'] = df['position'].fillna('BENCH')
        df: pd.DataFrame = df[df['comment'].isna() | df['minutes'].notna()]  # Remove DNP rows

        # Simply position from the player metadata
        # Use only the first letter of POSITION to define position (e.g., "C-F" -> "C", "F-C" -> "F")
        df['POSITION_player'] = df['POSITION'].apply(
            lambda x: x[0] if isinstance(x, str) and len(x) > 0 else np.nan
        )
        # Change column date type to datetime 
        df['game_date'] = pd.to_datetime(df['game_date'])
        # Add a season column based on the game_id 
        df['season'] = df['game_id'].astype(str).str[1:3].astype(int) + 2000

        # Calculate missed shots columns first
        df['fieldGoalsMissed'] = df['fieldGoalsAttempted'] - df['fieldGoalsMade']
        df['threePointersMissed'] = df['threePointersAttempted'] - df['threePointersMade']
        df['freeThrowsMissed'] = df['freeThrowsAttempted'] - df['freeThrowsMade']

        #  Calculate Fantasy Points (FP) using the provided formula
        df['FP'] = (df['points'] + 
                df['fieldGoalsMade'] +
                df['threePointersMade'] +
                df['freeThrowsMade'] +
                df['assists'] + 
                df['reboundsTotal'] +
                df['steals'] +
                df['blocks']) - \
            (df['fieldGoalsMissed'] + 
                df['threePointersMissed'] + 
                df['freeThrowsMissed'] + 
                df['turnovers'])

        # Feature engineering
        df['is_home'] = df['teamId'] == df['home_team_id']
        df['opponent'] = np.where(df['is_home'], df['visitor_team_id'], df['home_team_id'])

        # Select relevant columns
        keep_cols = ['game_id', 'game_date', 'season', 'personId', 'teamId', 'opponent',
                    'POSITION_player', 'minutes', 'is_home', 'points', 'reboundsTotal', 
                    'assists', 'steals', 'blocks', 'turnovers','fieldGoalsMade', 'freeThrowsMade',
                    'fieldGoalsMissed', 'freeThrowsMissed', 'FP']
        df: pd.DataFrame = df[keep_cols]

        return df
    
    def _add_advanced_features_eng(self, model_data: pd.DataFrame) -> pd.DataFrame:
        # Sort the DataFrame by 'personID' and 'game_date' 
        df: pd.DataFrame = model_data.sort_values(['personId', 'game_date'])

        # Create a list with the columns to be used for rolling calculations
        stats: list = ['points', 'assists', 'fieldGoalsMade','freeThrowsMade','reboundsTotal', 
            'steals','blocks',
            'fieldGoalsMissed',
            'freeThrowsMissed', 'turnovers',
            'minutes']
        
        for window in self.window_sizes:
            for stat in stats:
                # Create rolling features for each statistic
                df[f'rolling_{window}_{stat}'] = df.groupby('personId')[stat].transform(
                    lambda x: x.rolling(window=window, min_periods=1).mean()
                )
        
        # Days since last game 
        df['days_rest'] = df.groupby('personId')['game_date'].diff().dt.days.fillna(5)


        # Add opponent defensive stats
        # Only use games where players played more than 15 minutes for opponent defense stats
        opp_defense: pd.DataFrame = df[df['minutes'] > 15].groupby('opponent')['FP'].mean().rename('opp_fp_allowed')
        df: pd.DataFrame = df.merge(opp_defense, left_on='opponent', right_index=True)

        # Position-specific opponent stats (again, only for >15 min)
        pos_opp_defense: pd.DataFrame = df[df['minutes'] > 15].groupby(['opponent', 'POSITION_player'])['FP'].mean().rename('pos_opp_fp_allowed')
        df: pd.DataFrame = df.merge(pos_opp_defense, left_on=['opponent', 'POSITION_player'], right_index=True)

        # Season averages
        season_avg: pd.DataFrame = df.groupby(['personId', 'season'])['FP'].mean().rename('season_avg_fp')
        df: pd.DataFrame = df.merge(season_avg, left_on=['personId', 'season'], right_index=True)
        return df 

    def data_preparation(self, model_df:pd.DataFrame) -> dict:

        #filter out players with low minutes played
        model_df: pd.DataFrame = model_df[model_df['minutes'] > 15].copy()
        # Sort by game_date first
        model_df: pd.DataFrame = model_df.sort_values('game_date')
        # Get unique sorted dates
        unique_dates: list = model_df['game_date'].unique()
        split_date: list = unique_dates[int(0.8 * len(unique_dates))]

        # Split the data into train and test sets based on the split date
        train: pd.DataFrame = model_df[model_df['game_date'] < split_date]
        test: pd.DataFrame = model_df[model_df['game_date'] >= split_date]

        # Separate features and target variable
        X_train, y_train = train[self.features], train[self.target]
        X_test, y_test = test[self.features], test[self.target]

        return {
            'model_df': model_df,
            'X_train': X_train,
            'y_train' : y_train,
            'X_test' : X_test, 
            'y_test': y_test
        }

    def _build_pipeline(self, data_modeled: dict) -> Pipeline:
        """
        Build the machine Learning pipeline.
        Args:
            data_modeled (dict): A dictionnary containing the preprocessed data.
        Returns:
            Pipeline: A scikit-learn pipeline object.
        """
        # Load the data 
        model_df: pd.DataFrame = data_modeled['model_df']

        # Create a list of the categorical features by checking if they are of type 'object' or 'category'
        categorical_features: list = [col for col in self.features if model_df[col].dtype == 'object' or model_df[col].dtype == 'category']

        # Create a list of numeric features by excluding the categorical feature
        numeric_features = [f for f in self.features if f not in categorical_features]
        
        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', StandardScaler(), numeric_features),
                ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features)
            ])
        
        return Pipeline([
            ('preprocessor', self.preprocessor),
            ('model', XGBRegressor(
                objective='reg:squarederror',
                n_estimators=437,
                learning_rate=0.07,
                max_depth=3,
                subsample=0.76,
                colsample_bytree = 0.87,
                min_child_weight = 7,
                reg_lambda = 0.85,
                reg_alpha = 0.52,
                random_state=59
            ))
        ])
    
    def _train_model(self, pipeline: Pipeline, data_modeled: dict) -> None:
        """
        Train the machine learning model using the provided pipeline and data.
        Args:
            pipeline (Pipeline): The machine learning pipeline.
            data_modeled (dict): A dictionary containing the preprocessed data.
        """ 
        # Load the data 
        X_train: pd.DataFrame = data_modeled['X_train']
        y_train: pd.Series = data_modeled['y_train']

        # Train the model
        pipeline.fit(X_train, y_train)

        # Save the model
        joblib.dump(pipeline, os.path.join(self.model_dir, f"nba_model_{self.current_season}.joblib"))