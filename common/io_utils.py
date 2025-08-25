"""
This module contains the common variables and functions used in the NBA Stats Data Pipeline to store and load data.
"""
import os
import re
import pandas as pd
from google.cloud import bigquery
from google.cloud import storage
import joblib
import tempfile

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
        path: str = f"{databases_path}{FileName}.csv"
        if os.path.exists(path):
            try:
                df: pd.DataFrame = pd.read_csv(path,low_memory=False)
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

def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    m = re.match(r"^gs://([^/]+)/(.+)$", uri)
    if not m:
        raise ValueError(f"Invalid GCS URI: {uri}")
    return m.group(1), m.group(2)
    
def load_model_artifact(model_path: str, mode: str):
    """
    Load a model artifact from either local disk or GCS.

    Args:
        model_path: local path or 'gs://bucket/obj'
        mode: 'local' or 'bq' (if 'bq' and path is gs://, downloads from GCS)

    Returns:
        The deserialized model (e.g., a LightGBM/Sklearn object via joblib)
    """
    mode = (mode or "").lower()
    is_gcs = isinstance(model_path, str) and model_path.startswith("gs://")

    # Local mode (or any non-gs path) -> direct load
    if mode == "local" or not is_gcs:
        return joblib.load(model_path)

    # GCS mode: download to a temp file then load
    bucket_name, blob_name = _parse_gcs_uri(model_path)
    client = storage.Client()  # uses default creds on Cloud Run Job
    blob = client.bucket(bucket_name).blob(blob_name)

    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        blob.download_to_filename(tmp_path)
        return joblib.load(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass