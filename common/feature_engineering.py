import pandas as pd
import numpy as np
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

def encode_categorical_features(df: pd.DataFrame, categorical_cols: List[str]) -> Tuple[pd.DataFrame, List[str], OneHotEncoder]:
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
    encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    encoded_categorical = encoder.fit_transform(df[categorical_cols])
    
    feature_names = encoder.get_feature_names_out(categorical_cols).tolist()

    # Drop original categorical columns
    df = df.drop(categorical_cols, axis=1)

    # Concatenate encoded columns to original dataframe
    final_df = pd.concat([df, pd.DataFrame(encoded_categorical, 
                                           columns=feature_names, 
                                           index=df.index)], axis=1)
    
    return final_df, feature_names, encoder

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
        
    return feature_cols
