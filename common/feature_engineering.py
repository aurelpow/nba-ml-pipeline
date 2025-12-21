import pandas as pd
import numpy as np
import datetime
from typing import List, Dict, Tuple, Any
from sklearn.preprocessing import OneHotEncoder
from common.utils import parse_minutes

def merge_data(box: pd.DataFrame, adv: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """
    Merge boxscore, advanced stats, and players data.
    
    Args:
        box (pd.DataFrame): Basic boxscore data.
        adv (pd.DataFrame): Advanced boxscore data.
        players (pd.DataFrame): Players data.
        
    Returns:
        pd.DataFrame: Merged DataFrame.
    """
    # Merge boxscore df + players 
    df_merged = box.merge(
        players[['person_id', 'position']].rename(columns={'position': 'position_player'}),
        left_on='personId', right_on='person_id', how='left'
    ).drop('person_id', axis=1)

    # Merge advanced stats with boxscore + players
    ## a) Define merge keys for box + adv
    merge_keys = ['gameId', 'personId', 'teamId']
    
    ## b) Identify new columns from advanced stats
    adv_new_cols = [col for col in adv.columns if col not in box.columns or col in merge_keys]
    
    ## c) Perform the merge
    df = df_merged.merge(
        adv[adv_new_cols],
        left_on=merge_keys,
        right_on=merge_keys,
        how='left'
    )
    
    return df

def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Preprocess the data: parse minutes, handle positions, dates, season, home/away.
    
    Args:
        df (pd.DataFrame): Merged DataFrame.
        
    Returns:
        pd.DataFrame: Preprocessed DataFrame.
    """
    # Transform minutes from string to float
    if 'minutes' in df.columns and df['minutes'].dtype == 'object':
        df['minutes'] = df['minutes'].apply(parse_minutes)

    # fill NaN values in 'position' with 'BENCH'
    if 'position' in df.columns:
        df['position'] = df['position'].fillna('BENCH')
    
    # Create a new column 'position_group' based on 'POSITION' and 'position' 
    if 'position' in df.columns and 'position_player' in df.columns:
        df['position_group'] = df.apply(
            lambda x: 'G' if x['position'] in ('G', 'BENCH') and x['position_player'] in ('G', 'G-F') else
                    'F' if x['position'] in ('F', 'BENCH') and x['position_player'] in ('F', 'F-G', 'F-C') else
                    'C' if x['position'] in ('C', 'BENCH') and x['position_player'] in ('C', 'C-F') else x['position'],
            axis=1
        )
        
        # Filter out players where position_group is still 'BENCH' (likely missing player info or deep bench)
        df = df[df['position_group'] != 'BENCH']

    # Remove rows with no minutes (DNP)
    if 'minutes' in df.columns:
        df = df[df['minutes'].notna()]

    # Change column date type to datetime 
    if 'game_date' in df.columns:
        df['game_date'] = pd.to_datetime(df['game_date'])
    
    # Add a season column based on the game_id 
    if 'gameId' in df.columns:
        df['season'] = df['gameId'].astype(str).str[1:3].astype(int) + 2000

    # Feature engineering
    if 'teamId' in df.columns and 'home_team_id' in df.columns and 'visitor_team_id' in df.columns:
        df['is_home'] = df['teamId'] == df['home_team_id']
        df['opponent'] = np.where(df['is_home'], df['visitor_team_id'], df['home_team_id'])

    # Calculate rest days
    if 'teamId' in df.columns and 'game_date' in df.columns:
        df = df.sort_values(['teamId', 'game_date'])
        df['rest_days'] = df.groupby('teamId')['game_date'].diff().dt.days
        df['rest_days'] = df['rest_days'].fillna(3) # Default to 3 days rest for first game
        df['rest_days'] = df['rest_days'].clip(upper=7) # Cap at 7 days

    return df

def create_historical_features(df: pd.DataFrame, target_col: str = 'points') -> pd.DataFrame:
    """
    Create historical performance features based on position group opponent and game date (time aware).
    
    Args:
        df (pd.DataFrame): The input DataFrame already prepared with basic features.
        target_col (str): The target column to compute historical averages for (e.g., 'points' or 'fantasy_points').
        
    Returns:
        pd.DataFrame: The DataFrame with historical features added.
    """
    # Filter out bench players and copy to avoid SettingWithCopyWarning
    df_hist = df[df['position'] != 'BENCH'].copy()

    # Compute historical mean points per (position_group, opponent, game_date)
    # Use dynamic target column name for the aggregation
    avg_col_name = f'avg_{target_col}_opp_position'
    
    # Include season in the grouping for the base aggregation to ensure we have it for the next steps
    df_avg = (
        df_hist
        .groupby(['position_group', 'opponent', 'game_date', 'season'], as_index=False)[target_col]
        .mean()
        .rename(columns={target_col: 'avg_target'})
    )

    # sort chronologically per group (oldest -> newest)
    df_avg = df_avg.sort_values(['position_group', 'opponent', 'game_date'], ascending=[True, True, True]).reset_index(drop=True)

    # Compute rolling averages shifted by 1 to avoid data leakage
    
    # For last 10 and 20, we keep the cross-season logic (group by position and opponent only)
    grp_cross_season = df_avg.groupby(['position_group', 'opponent'])['avg_target']
    
    # For 'all', we want it to be season-specific as requested
    grp_season = df_avg.groupby(['position_group', 'opponent', 'season'])['avg_target']
    
    col_10 = f'{avg_col_name}_last_10'
    col_20 = f'{avg_col_name}_last_20'
    col_all = f'{avg_col_name}_all'
    
    df_avg[col_10] = grp_cross_season.apply(lambda x: x.shift(1).rolling(10, min_periods=1).mean()).reset_index(level=[0,1], drop=True)
    df_avg[col_20] = grp_cross_season.apply(lambda x: x.shift(1).rolling(20, min_periods=1).mean()).reset_index(level=[0,1], drop=True)
    
    # Use the season-specific group for the expanding mean
    # Note: reset_index(level=[0,1,2], drop=True) because grouping has 3 keys
    df_avg[col_all] = grp_season.apply(lambda x: x.shift(1).expanding().mean()).reset_index(level=[0,1,2], drop=True)

    # Merge back by date so each row only sees past info
    final_df = df.merge(
        df_avg[['position_group', 'opponent', 'game_date',
                col_10, col_20, col_all]],
        on=['position_group', 'opponent', 'game_date'],
        how='left'
    )

    # Fill NaN for first occurrences
    final_df[[col_10, col_20, col_all]] = final_df[[col_10, col_20, col_all]].fillna(0)
    
    return final_df

def normalize_features(df: pd.DataFrame, key_stats: Dict[str, str]) -> pd.DataFrame:
    """
    Normalizing by playing time and pace gives features comparable across starters and bench.
    
    Args:
        df (pd.DataFrame): input DataFrame
        key_stats (Dict[str, str]): dictionary of stats to normalize
        
    Returns:
        pd.DataFrame: The DataFrame with normalized features added.
    """
    for stat in key_stats:
        if stat in df.columns:
            per36 = f"{stat}_per36"
            df[per36] = df[stat] / df['minutes'] * 36

    # And per-possession metrics
    for stat in key_stats:
        if stat in df.columns:
            ppp = f"{stat}_per_poss"
            df[ppp] = df[stat] / df['possessions'] 

    return df

def compute_rolling_stats(df: pd.DataFrame, key_stats: Dict[str, str], windows: List[int] = [5,10,20]) -> pd.DataFrame:
    """
    Compute rolling averages for key stats over specified windows.
    
    Args:
        df (pd.DataFrame): input DataFrame
        key_stats (Dict[str, str]): dictionary of stats to compute rolling averages for
        windows (List[int]): list of window sizes (in number of games)
        
    Returns:
        pd.DataFrame: The DataFrame with rolling average features added.
    """
    # Sort by personId and game_date to ensure correct rolling calculations
    df = df.sort_values(by=['personId', 'game_date'], ascending=[True, True]).copy()
    
    # Exclude Engineered stats
    raw_stats = {k:v for k,v in key_stats.items() if 'engineering' not in v.lower()}
    
    new_features = {}
    
    for period in raw_stats:
        for rolling_period in windows:
            per36 = f"{period}_per36"
            per_poss = f"{period}_per_poss"
            
            if per36 in df.columns:
                new_features[f"{per36}_rolling_{rolling_period}"] = (df
                                                           .groupby('personId')[per36]
                                                           .transform(lambda x: x.shift(1).rolling(rolling_period, min_periods=1)
                                                                      .mean())
                )
            if per_poss in df.columns:
                new_features[f"{per_poss}_rolling_{rolling_period}"] = (df
                                                              .groupby('personId')[per_poss]
                                                              .transform(lambda x: x.shift(1).rolling(rolling_period, min_periods=1)
                                                                         .mean())
                )
            
            # Also compute raw rolling stats (CRITICAL for volume stats like minutes)
            if period in df.columns:
                new_features[f"{period}_rolling_{rolling_period}"] = (df
                                                           .groupby('personId')[period]
                                                           .transform(lambda x: x.shift(1).rolling(rolling_period, min_periods=1)
                                                                      .mean())
                )

    if new_features:
        df = pd.concat([df, pd.DataFrame(new_features, index=df.index)], axis=1)

    return df

def encode_categorical_features(df: pd.DataFrame, categorical_cols: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    """
    Encode categorical features using one-hot encoding.
    
    Args:
        df (pd.DataFrame): input DataFrame
        categorical_cols (List[str]): list of categorical columns to encode
        
    Returns:
        Tuple[pd.DataFrame, List[str], OneHotEncoder]: 
            - DataFrame with one-hot encoded categorical features added
            - List of new feature names
            - Fitted encoder
    """
    # encode categorical features
    encoder: OneHotEncoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    encoded_categorical: np.ndarray = encoder.fit_transform(df[categorical_cols])
    
    feature_names: Any = encoder.get_feature_names_out(categorical_cols).tolist()

    # Drop original categorical columns
    df = df.drop(categorical_cols, axis=1)

    # Concatenate encoded columns to original dataframe
    final_df: pd.DataFrame = pd.concat([df, pd.DataFrame(encoded_categorical, 
                                           columns=feature_names, 
                                           index=df.index)], axis=1)
    
    return final_df, feature_names

def get_feature_cols(key_stats: Dict[str, str], rolling_periods: List[int] = [5, 10, 20]) -> List[str]:
    """
    Generate the list of feature columns based on key stats and rolling periods.
    
    Args:
        key_stats (Dict[str, str]): dictionary of stats
        rolling_periods (List[int]): list of rolling window sizes
        
    Returns:
        List[str]: List of feature column names
    """
    feature_cols = []
    
    # Separate raw stats (get rolling) vs engineering stats (get per36/per_poss only)
    raw_stats = [k for k, v in key_stats.items() if 'raw' in v.lower()]
    engineering_stats = [k for k, v in key_stats.items() if 'engineering' in v.lower()]
    
    # 1) Add rolling features GROUPED BY WINDOW (matching notebook)
    for window in rolling_periods:
        # First add all _per36_rolling_X for this window
        for stat in raw_stats:
            feature_cols.append(f"{stat}_per36_rolling_{window}")
        
        # Then add all _per_poss_rolling_X for this window
        for stat in raw_stats:
            feature_cols.append(f"{stat}_per_poss_rolling_{window}")

        # Then add all raw rolling stats (e.g. minutes_rolling_5)
        for stat in raw_stats:
            feature_cols.append(f"{stat}_rolling_{window}")
    
    # 2) Add historical averages (engineering stats) - per36 first, then per_poss
    for stat in engineering_stats:
        feature_cols.append(f"{stat}_per36")
    
    for stat in engineering_stats:
        feature_cols.append(f"{stat}_per_poss")

    # Add rest_days as a feature
    feature_cols.append('rest_days')

    return feature_cols

def get_rest_days(players_df: pd.DataFrame,
                  boxscore_df: pd.DataFrame,
                  date: datetime.date) -> pd.DataFrame:
    """
    Calculate rest days for each players up to a given date.
    Args:
        df (pd.DataFrame): input DataFrame
    Returns:
        pd.DataFrame: DataFrame with rest_days column added
    """

    # Get unique players 
    players_unique: pd.DataFrame = players_df[['person_id', 'team_id']].drop_duplicates()

    # Get last game date for each player
    last_games: pd.DataFrame = (
        boxscore_df[pd.to_datetime(boxscore_df['game_date']).dt.date  < date]
        .sort_values('game_date')
        .groupby('personId')
        .tail(1)[['personId', 'game_date']]
        .rename(columns={'game_date': 'last_game_date'})
    )

    # Merge to get last game date per player
    rest_days_df: pd.DataFrame = players_unique.merge(
        last_games,
        left_on='person_id',
        right_on='personId',
        how='left'
    )

    # Calculate rest days
    rest_days_df['rest_days'] = (pd.to_datetime(date) - pd.to_datetime(rest_days_df['last_game_date'])).dt.days
    rest_days_df['rest_days'] = rest_days_df['rest_days'].fillna(7)  # Default to 7 days if no last game
    
    return rest_days_df[['personId', 'rest_days']]

def get_volatility(df_historical: pd.DataFrame, 
                           target_variable: str) -> pd.DataFrame:
    """
    Calculate fantasy points volatility (std dev over last 20 games).
    Args:
        df_historical (pd.DataFrame): input DataFrame
        target_variable (str): target variable for volatility calculation
    Returns:
        pd.DataFrame: DataFrame with personId and fantasy_volatility columns
    """
    
    # Calculate volatility (std dev of fantasy points over last 10 games)
    # We need to do this on the full history before taking the tail
    df_hist_sorted: pd.DataFrame = df_historical.sort_values(['personId', 'game_date'])
    df_hist_sorted['fantasy_volatility'] = df_hist_sorted.groupby('personId')[target_variable].transform(
            lambda x: x.rolling(20, min_periods=5).std()
        )
    
    # Get latest volatility values
    volatility_df: pd.DataFrame = (
        df_hist_sorted.sort_values('game_date')
        .groupby('personId')
        .tail(1)[['personId', 'fantasy_volatility']]
    )

    return volatility_df
    
def get_final_df(
             encoded_df: pd.DataFrame, 
             volatility_df: pd.DataFrame,
             future_games: pd.DataFrame,
             model: Any,
             feature_names: List[str],
             encoded_feature_names: List[str],
             measure_prediction: int,
             measure_volatility: int) -> pd.DataFrame:
    """
    Prepare final DataFrame for prediction.
    Args:
        encoded_df (pd.DataFrame): DataFrame with encoded historical data
        volatility_df (pd.DataFrame): DataFrame with volatility data
        future_games (pd.DataFrame): DataFrame with future games data
        model (Any): Trained model for prediction
        feature_names (List[str]): List of feature names to select
        encoded_feature_names (List[str]): List of encoded feature names to select
        measure_prediction (int): Measure code for predictions (e.g., MEASURE_PREDICTED_POINTS)
        measure_volatility (int): Measure code for volatility (e.g., MEASURE_POINTS_VOLATILITY)
    Returns:
        pd.DataFrame: Final DataFrame ready for prediction.
    """
    # Get final feature names (including encoded)
    final_features: List[str] = feature_names + encoded_feature_names

    # Get latest stats
    latest_stats: pd.DataFrame = encoded_df.sort_values('game_date').groupby('personId').tail(1)
    
    # Merge volatility into latest stats
    latest_stats: pd.DataFrame = latest_stats.merge(
        volatility_df,
        on='personId',
        how='left'
    )
    # Merge 
    cols_to_merge: list[str] = [c for c in final_features if c in latest_stats.columns]
    cols_to_merge.append('personId')
    cols_to_merge.append('fantasy_volatility')
    
    # Also add rest_days if it exists in latest_stats (but not in final_features list)
    if 'rest_days' in latest_stats.columns and 'rest_days' not in cols_to_merge:
        cols_to_merge.append('rest_days')

    # Select only relevant features
    future_games_long: pd.DataFrame = future_games.merge(
        latest_stats[cols_to_merge],
        left_on='person_id',
        right_on='personId',
        how='inner'
    )

    # Predict - check for rest_days and add it if needed
    available_features = [f for f in final_features if f in future_games_long.columns]
    
    # If rest_days is in final_features but not in future_games_long, add it
    if 'rest_days' in final_features and 'rest_days' not in future_games_long.columns:
        # This shouldn't happen if we merged correctly above, but as a fallback
        future_games_long['rest_days'] = 3  # default value
    
    X_pred: pd.DataFrame = future_games_long[final_features].fillna(0)
    # DEBUG: Compare with model's expected features
    if hasattr(model, 'feature_name_'):
        model_features = model.feature_name_
        print(f"\n🔍 Feature comparison:")
        print(f"   Model expects: {len(model_features)} features")
        print(f"   We have: {len(X_pred.columns)} features")
        
        # Find missing and extra features
        missing = set(model_features) - set(X_pred.columns)
        extra = set(X_pred.columns) - set(model_features)
        
        if missing:
            print(f"\n❌ MISSING features (in model but not in X_pred):")
            for feat in sorted(missing):
                print(f"   - {feat}")
        
        if extra:
            print(f"\n➕ EXTRA features (in X_pred but not in model):")
            for feat in sorted(extra):
                print(f"   - {feat}")
        
        # Reorder X_pred to match model's expected feature order
        X_pred = X_pred.reindex(columns=model_features, fill_value=0)
        print(f"\n✅ Reordered X_pred to match model features")
    
    predictions: Any = model.predict(X_pred)
    
    # Create base DataFrame
    base_df = pd.DataFrame({
        'gameId': future_games_long['gameId'].values,
        'gameDate': future_games_long['gameDate'].values,
        'teamId': future_games_long['team_id'].values,
        'opponentId': future_games_long['opponent'].values,
        'personId': future_games_long['personId'].values,
        'player_slug': future_games_long['player_slug'].values,
    })
    
    # Create predictions rows (narrow format)
    predictions_rows = base_df.copy()
    predictions_rows['Measure'] = measure_prediction
    predictions_rows['Predictions'] = np.round(predictions, 1)
    
    # Create volatility rows (narrow format)
    volatility_rows = base_df.copy()
    volatility_rows['Measure'] = measure_volatility
    volatility_rows['Predictions'] = np.round(future_games_long['fantasy_volatility'].fillna(0), 1)
    
    # Combine both measures
    predictions_df = pd.concat([predictions_rows, volatility_rows], ignore_index=True)
    
    return predictions_df