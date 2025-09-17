"""
Centralized configuration with environment separation.

Loads from `.env` files depending on APP_ENV (dev|prod|test). Defaults to prod.
Exposes a simple `settings` object with typed attributes used across the app.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    # Lazy import to keep optional in runtime environments
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore


def _load_env_files() -> None:
    """
    Load environment variables from .env files based on APP_ENV.
    Precedence: real env vars > .env.<env> > .env
    """
    if load_dotenv is None:
        return

    # Always load base .env if present (lower precedence than real env vars)
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"), override=False)

    app_env = os.getenv("APP_ENV", "prod").lower()
    env_file = f".env.{app_env}"
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), env_file), override=False)


_load_env_files()


@dataclass(frozen=True)
class Settings:
    # General
    app_env: str = os.getenv("APP_ENV", "prod")

    # Data sink
    save_mode: str = os.getenv("SAVE_MODE", "bq")  # bq|local

    # GCP
    gcp_project_id: str = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", "ml-nba-project"))
    bigquery_dataset: str = os.getenv("BIGQUERY_DATASET", "nba_dataset")

    # Model registry
    # e.g. gs://your-bucket/models or local path like ml_dev/models
    model_registry_uri: str = os.getenv("MODEL_REGISTRY_URI", "ml_dev/models")

    # Default model filename used for inference when not specified
    model_filename: str = os.getenv("MODEL_FILENAME", "best_lgbm_model.pkl")

    # Optional network proxies for nba_api
    proxy_user: str | None = os.getenv("NBA_PROXY_USER")
    proxy_pass: str | None = os.getenv("NBA_PROXY_PASS")


settings = Settings()

