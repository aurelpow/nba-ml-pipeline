import pandas as pd

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
    required_cols: list[str] = ['points', 'reboundsTotal', 'assists', 'steals', 'blocks', 'turnovers', 
                     'fieldGoalsMade', 'fieldGoalsAttempted', 
                     'threePointersMade', 'threePointersAttempted', 
                     'freeThrowsMade', 'freeThrowsAttempted']
    
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column for fantasy points calculation: {col}")
            
    # Calculate Missed Shots
    field_goals_missed: pd.Series = df['fieldGoalsAttempted'] - df['fieldGoalsMade']
    three_pointers_missed: pd.Series = df['threePointersAttempted'] - df['threePointersMade']
    free_throws_missed: pd.Series = df['freeThrowsAttempted'] - df['freeThrowsMade']
    
    # Calculate Fantasy Points
    df['fantasy_points'] = (
        df['points'] + 
        df['reboundsTotal'] + 
        df['assists'] + 
        df['steals'] + 
        df['blocks'] + 
        df['fieldGoalsMade'] + 
        df['threePointersMade'] + 
        df['freeThrowsMade'] - 
        df['turnovers'] - 
        field_goals_missed - 
        three_pointers_missed - 
        free_throws_missed
    )
    
    return df
