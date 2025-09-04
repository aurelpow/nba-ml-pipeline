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
from typing import Optional, Iterable
from google.api_core.exceptions import NotFound, BadRequest

# Define the names of the files to be used in the databases folder.
AdvancedBoxscoreFileName: str = "nba_boxscore_advanced" 
BoxscoreFileName: str = "nba_boxscore_basic"
PlayersFileName: str = "nba_players_df"
TeamsFileName: str = "nba_teams_df"
FutureGamesFileName: str = "nba_future_games_df"
PredictionsFileName: str = 'nba_points_predictions_df'
ScheduleFileName: str = 'nba_schedule_df' 

# Define the path to the databases folder.
databases_path: str = "databases/"
PROJECT_ID = "ml-nba-project"
DATASET_ID = "nba_dataset"

def _table_ref(table_name: str) -> str:
    return f"{PROJECT_ID}.{DATASET_ID}.{table_name}"

from google.cloud import bigquery
from google.api_core.exceptions import NotFound
import pandas as pd
from typing import Iterable

def _delete_rows_by_game_id(client: bigquery.Client, table_id: str, game_ids: Iterable) -> int:
    game_ids = list({str(gid) for gid in game_ids if pd.notna(gid)})
    if not game_ids:
        return 0

    # ✅ Check if table exists
    try:
        client.get_table(table_id)
    except NotFound:
        # Table doesn't exist, return 0
        print(f"Table {table_id} not found, skipping deletion")
        return 0

    query = f"""
    DELETE FROM `{table_id}`
    WHERE gameId IN UNNEST(@game_ids)
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("game_ids", "STRING", game_ids)
            ]
        ),
    )
    job.result()
    return getattr(job, "num_dml_affected_rows", 0) or 0


def save_database(
    df: pd.DataFrame,
    table_name: str,
    mode: str = "bq",
    write_disposition: str = "WRITE_TRUNCATE",
    autodetect_schema: bool = True,
) -> None:
    """
    Save a DataFrame either locally or to BigQuery.
    - If df has gameId column: delete matching rows before append
    - Else: overwrite table (default WRITE_TRUNCATE)
    """
    if df is None or df.empty:
        print("⚠️ DataFrame empty; nothing to save.")
        return

    # Add aud_modification_date column (datetime)
    df["aud_modification_date"] = pd.Timestamp.now(tz="Europe/Madrid")

    if mode == "local":
        path = f"databases/{table_name}.csv"
        df.to_csv(path, index=False)
        print(f"✅ Saved locally to: {path}")
        return

    if mode != "bq":
        raise ValueError("Invalid mode: choose 'local' or 'bq'")

    client = bigquery.Client()
    table_id = _table_ref(table_name)

    has_game_id = "gameId" in df.columns

    if has_game_id and write_disposition == "WRITE_APPEND":
        unique_ids = df["gameId"].astype(str).dropna().unique().tolist()
        deleted = _delete_rows_by_game_id(client, table_id, unique_ids)
        print(f"🧹 Deleted {deleted} rows in {table_id} for {len(unique_ids)} gameId(s).")

        load_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            autodetect=autodetect_schema,
        )
    else:
        load_config = bigquery.LoadJobConfig(
            write_disposition=write_disposition,
            autodetect=autodetect_schema,
        )

    job = client.load_table_from_dataframe(df, table_id, job_config=load_config)
    try:
        job.result()
    except BadRequest as e:
        print(f"❌ BigQuery load failed: {e}")
        for err in getattr(job, "errors", []) or []:
            print(f" - {err.get('message')}")
        raise

    print(f"✅ Saved {len(df):,} row(s) to {table_id} "
          f"({'APPEND after delete-by-key' if has_game_id else load_config.write_disposition})")

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