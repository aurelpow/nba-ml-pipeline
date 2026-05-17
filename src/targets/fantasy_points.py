import pandas as pd
from common.raw_columns import *

def compute_fantasy_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute Fantasy Points based on TTFL (TrashTalk Fantasy League) formula.
    
    Formula:
    FantasyPoints = PTS + REB + AST + STL + BLK + FGM + 3PM + FTM 
                    - TOV - (FGA - FGM) - (3PA - 3PM) - (FTA - FTM)
    
    Args:
        df (pd.DataFrame): DataFrame containing basic boxscore stats.
        
    Returns:
        pd.DataFrame: DataFrame with 'fantasy_points' column added.
    """
    # Ensure required columns exist
    required_cols: list[str] = [points_col, rebounds_total_col, assists_col, steals_col, blocks_col, turnovers_col, 
                     field_goals_made_col, field_goals_attempted_col, 
                     three_pointers_made_col, three_pointers_attempted_col, 
                     free_throws_made_col, free_throws_attempted_col]
    
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column for fantasy points calculation: {col}")
            
    # Calculate Missed Shots
    field_goals_missed: pd.Series = df[field_goals_attempted_col] - df[field_goals_made_col]
    three_pointers_missed: pd.Series = df[three_pointers_attempted_col] - df[three_pointers_made_col]
    free_throws_missed: pd.Series = df[free_throws_attempted_col] - df[free_throws_made_col]
    
    # Calculate Fantasy Points
    df[fantasy_points_col] = (
        df[points_col] + 
        df[rebounds_total_col] + 
        df[assists_col] + 
        df[steals_col] + 
        df[blocks_col] + 
        df[field_goals_made_col] + 
        df[three_pointers_made_col] + 
        df[free_throws_made_col] - 
        df[turnovers_col] - 
        field_goals_missed - 
        three_pointers_missed - 
        free_throws_missed
    )
    
    return df