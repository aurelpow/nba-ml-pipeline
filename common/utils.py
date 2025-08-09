"""
This module contains the common variables used in the NBA Stats Data Pipeline.
"""
import os 
import pandas as pd
from google.cloud import bigquery


# Define the names of the files to be used in the databases folder.
AdvancedBoxscoreFileName: str = "nba_boxscore_advanced" 
BoxscoreFileName: str = "nba_boxscore_basic"
PlayersFileName: str = "nba_players_df"
TeamsFileName: str = "nba_teams_df"
FutureGamesFileName: str = "nba_future_games_df"
PredictionsFileName: str = 'nba_points_predictions_df'

# Define the path to the databases folder.
databases_path: str = "databases/"


def load_data(FileName: str, mode: str ) -> pd.DataFrame:
    """
    Load data either locally or to BigQuery, depending on mode
    Args:
        FileName (str): The name of the file to load.
        mode (str): 'local' or 'bq' (default: 'bq')
        Returns:
            pd.DataFrame: The loaded DataFrame.
    """
    if mode == "local":
        path = f"{databases_path}{FileName}.csv"
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                return df
            except Exception as e:
                print(f"Error loading local file {path}: {e}")
            return pd.DataFrame()
    elif mode == "bq":
        try:
            client = bigquery.Client()
            table_id = f"ml-nba-project.nba_dataset.{FileName}"
            df_existing = client.list_rows(table_id).to_dataframe()
            print(f"✅ Loaded {len(df_existing)} rows from {table_id}")
            return df_existing
        except Exception as e:
            print(f"❌ Could not load existing data from BigQuery: {e}")
            return pd.DataFrame()

def save_database(df, table_name: str, mode: str = "bq"):
    """
    Save a DataFrame either locally or to BigQuery, depending on mode.

    Args:
        df (pd.DataFrame): Data to save
        table_name (str): Table or file name
        mode (str): 'local' or 'bq' (default: 'bq')
    """
    if mode == "local":
        path = f"databases/{table_name}.csv"
        df.to_csv(path, index=False)
        print(f"✅ Saved locally to: {path}")
    elif mode == "bq":
        client = bigquery.Client()
        table_id = f"ml-nba-project.nba_dataset.{table_name}"
        job = client.load_table_from_dataframe(
            df,
            table_id,
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        )
        job.result()
        print(f"✅ Saved to BigQuery: {table_id}")
    else:
        raise ValueError("Invalid mode: choose 'local' or 'bq'")