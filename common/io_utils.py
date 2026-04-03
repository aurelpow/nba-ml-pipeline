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
PredictionsFileName: str = "nba_predictions_df"
ScheduleFileName: str = "nba_schedule_df"
MetricsFileName: str = "model_training_metrics_df"
# Availability subsystem
InjuryReportFileName: str = "nba_injury_report"  # raw parsed PDF rows
AvailabilityFileName: str = "nba_player_availability"  # enriched downstream table

# Define the path to the databases folder.
databases_path: str = "databases/"
PROJECT_ID = "ml-nba-project"
DATASET_ID = "nba_dataset"


def _table_ref(table_name: str) -> str:
    return f"{PROJECT_ID}.{DATASET_ID}.{table_name}"


def _delete_rows_by_game_id(
    client: bigquery.Client, table_id: str, game_ids: Iterable
) -> int:
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


def _delete_predictions_by_composite_key(
    client: bigquery.Client, table_id: str, df: pd.DataFrame
) -> int:
    """
    Delete existing predictions matching gameId + personId + Measure combination.
    This prevents duplicates when re-running predictions for the same games.
    """
    if df.empty:
        return 0

    # Check if table exists
    try:
        client.get_table(table_id)
    except NotFound:
        print(f"Table {table_id} not found, skipping deletion")
        return 0

    # Build composite keys from new predictions
    required_cols = ["gameId", "personId", "Measure"]
    if not all(col in df.columns for col in required_cols):
        print(f"⚠️ Missing required columns for deletion: {required_cols}")
        return 0

    # Create a temporary table with the keys to delete
    # Match BigQuery schema: gameId=STRING, personId=INTEGER, Measure=INTEGER
    keys_df = df[required_cols].drop_duplicates()
    keys_df["gameId"] = keys_df["gameId"].astype(str)
    keys_df["personId"] = keys_df["personId"].astype("Int64")  # Nullable integer
    keys_df["Measure"] = keys_df["Measure"].astype("Int64")

    temp_table_id = f"{table_id}_delete_keys_temp"

    # Upload keys to temp table with explicit schema matching target table
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("gameId", "STRING"),
            bigquery.SchemaField("personId", "INTEGER"),
            bigquery.SchemaField("Measure", "INTEGER"),
        ],
    )
    client.load_table_from_dataframe(
        keys_df, temp_table_id, job_config=job_config
    ).result()

    # Delete matching rows using JOIN
    query = f"""
    DELETE FROM `{table_id}` AS target
    WHERE EXISTS (
        SELECT 1 FROM `{temp_table_id}` AS keys
        WHERE target.gameId = keys.gameId
          AND target.personId = keys.personId
          AND target.Measure = keys.Measure
    )
    """
    job = client.query(query)
    job.result()

    # Clean up temp table
    client.delete_table(temp_table_id, not_found_ok=True)

    deleted_count = getattr(job, "num_dml_affected_rows", 0) or 0
    return deleted_count


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
        print(
            f"🧹 Deleted {deleted} rows in {table_id} for {len(unique_ids)} gameId(s)."
        )

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

    print(
        f"✅ Saved {len(df):,} row(s) to {table_id} "
        f"({'APPEND after delete-by-key' if has_game_id else load_config.write_disposition})"
    )


def save_predictions(df: pd.DataFrame, table_name: str, mode: str = "bq") -> None:
    """
    Save predictions with intelligent append logic.
    Deletes existing predictions for the same gameId + personId + Measure combination
    before appending new predictions. Works in both local and BigQuery modes.

    Args:
        df (pd.DataFrame): Predictions DataFrame with columns: gameId, personId, Measure, Predictions, etc.
        table_name (str): Table name (e.g., 'nba_predictions_df')
        mode (str): 'local' or 'bq'
    """
    if df is None or df.empty:
        print("⚠️ Predictions DataFrame empty; nothing to save.")
        return

    # Add audit timestamp
    df["aud_modification_date"] = pd.Timestamp.now(tz="Europe/Madrid")

    if mode == "local":
        # Local mode: load existing, filter out duplicates, append new
        path = f"databases/{table_name}.csv"

        if os.path.exists(path):
            existing_df = pd.read_csv(path, low_memory=False)

            # Remove existing predictions for same gameId + personId + Measure
            if not existing_df.empty and all(
                col in existing_df.columns for col in ["gameId", "personId", "Measure"]
            ):
                # Create composite key for filtering
                new_keys = (
                    df[["gameId", "personId", "Measure"]]
                    .astype(str)
                    .agg("_".join, axis=1)
                )
                existing_keys = (
                    existing_df[["gameId", "personId", "Measure"]]
                    .astype(str)
                    .agg("_".join, axis=1)
                )

                # Keep only rows from existing that don't match new predictions
                mask = ~existing_keys.isin(new_keys)
                filtered_existing = existing_df[mask]

                deleted_count = len(existing_df) - len(filtered_existing)
                print(
                    f"🧹 Removed {deleted_count} existing predictions for {len(new_keys.unique())} game-player-measure combinations."
                )

                # Concatenate filtered existing with new
                final_df = pd.concat([filtered_existing, df], ignore_index=True)
            else:
                # No existing data or missing columns
                final_df = df
        else:
            # No existing file
            final_df = df

        final_df.to_csv(path, index=False)
        print(
            f"✅ Saved {len(df):,} new prediction(s) to {path} (Total: {len(final_df):,} rows)"
        )
        return

    if mode != "bq":
        raise ValueError("Invalid mode: choose 'local' or 'bq'")

    # BigQuery mode
    client = bigquery.Client()
    table_id = _table_ref(table_name)

    # Delete existing predictions for same composite keys
    deleted = _delete_predictions_by_composite_key(client, table_id, df)
    print(f"🧹 Deleted {deleted} existing predictions for {len(df)} new prediction(s).")

    # Append new predictions
    load_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND", autodetect=True
    )

    job = client.load_table_from_dataframe(df, table_id, job_config=load_config)
    try:
        job.result()
    except BadRequest as e:
        print(f"❌ BigQuery load failed: {e}")
        for err in getattr(job, "errors", []) or []:
            print(f" - {err.get('message')}")
        raise

    print(
        f"✅ Saved {len(df):,} prediction(s) to {table_id} (APPEND after delete-by-composite-key)"
    )


def load_data(FileName: str, mode: str) -> pd.DataFrame:
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
                df: pd.DataFrame = pd.read_csv(path, low_memory=False)
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
    return pd.DataFrame()


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    m = re.match(r"^gs://([^/]+)/(.+)$", uri)
    if not m:
        raise ValueError(f"Invalid GCS URI: {uri}")
    return m.group(1), m.group(2)
