"""
This module contains the common variables used in the NBA Stats Data Pipeline.
"""
import os 
import pandas as pd


# Define the names of the files to be used in the databases folder.
AdvancedBoxscoreFileName = "nba_boxscore_advanced" 
BoxscoreFileName = "nba_boxscore_basic"
PlayersFileName = "nba_players_df"
TeamsFileName = "nba_teams_df"
FutureGamesFileName = "nba_future_games_df"
PredictionsFileName = 'nba_points_predictions_df'

# Define the path to the databases folder.
databases_path = "databases/"

def save_database_local(df_to_save: pd.DataFrame, df_to_save_name: str) -> None:
    """
    Save the DataFrame to an Excel file in the 'databases' folder.
    
    Args:
        df_to_save (pd.DataFrame): The DataFrame to save.
        df_to_save_name (str): The base name for the saved file.
    """
    # Append .xlsx extension if not already present.
    if not df_to_save_name.lower().endswith('.csv'):
        df_to_save_name = f"{df_to_save_name}.csv"
    file_path = f"databases/{df_to_save_name}"
    df_to_save.to_csv(file_path, index=False)
    print(f"Saved to database: {file_path}")


def load_existing_boxscores(FileName: str) -> pd.DataFrame:
    """
    Load already fetched df if available.
    
    Returns:
        pd.DataFrame: The existing DataFrame or an empty one.
    """
    file_path = f"{databases_path}{FileName}.csv"
    if os.path.exists(file_path):
        try:
            df_existing = pd.read_csv(file_path)
            return df_existing
        except Exception as e:
            print(f"Error loading existing boxscore file: {e}")
    return pd.DataFrame()
