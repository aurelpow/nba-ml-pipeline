import argparse
import os
from datetime import datetime
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import lightgbm as lgb

from common.config import settings
from common.io_utils import (
    load_data,
    save_model_artifact,
    log_run_to_bigquery,
    BoxscoreFileName,
    AdvancedBoxscoreFileName,
    PlayersFileName,
)
from src.get_predictions_stats_points import PredictionsStatsPoints


def build_features() -> tuple[pd.DataFrame, pd.Series]:
    """
    Reuse the feature engineering logic from inference to build a supervised dataset.
    Target: points from historical games.
    """
    df_map = {
        "simple_boxscore": load_data(BoxscoreFileName, mode=settings.save_mode),
        "advanced_boxscore": load_data(AdvancedBoxscoreFileName, mode=settings.save_mode),
        "players": load_data(PlayersFileName, mode=settings.save_mode),
        # schedule not required for training past games
    }

    # Minimal guard
    for k, v in df_map.items():
        if v is None or v.empty:
            raise RuntimeError(f"Missing training data for {k}. Populate data first.")

    # Fake date and model path just to construct the transformer; they are unused in feature building for training
    transformer = PredictionsStatsPoints(save_mode=settings.save_mode, date="2000-01-01", model_path="unused.pkl")

    # Build historical features
    hist = transformer.get_historical_stats(df_map)
    hist = transformer.prepare_data_model(hist)
    hist = transformer.normalize_numerical_data(hist)
    encoded, encoded_feature_names = PredictionsStatsPoints.encode_categorical_data(hist)

    # Select target and features for rows where target exists
    encoded = encoded.dropna(subset=["points"]).copy()

    # Define feature columns consistent with inference
    numeric_feats = []
    rolling_periods = [5, 10, 20]
    feature_cols_rolling = [
        c for c in transformer.keys_points_stats if not c.startswith("avg_pts_opp_position")
    ]
    for rp in rolling_periods:
        numeric_feats.extend([f"{s}_per36_rolling_{rp}" for s in feature_cols_rolling])
        numeric_feats.extend([f"{s}_per_poss_rolling_{rp}" for s in feature_cols_rolling])
    numeric_feats.extend([
        "avg_pts_opp_position_last_10_per36",
        "avg_pts_opp_position_last_20_per36",
        "avg_pts_opp_position_all_per36",
        "avg_pts_opp_position_last_10_per_poss",
        "avg_pts_opp_position_last_20_per_poss",
        "avg_pts_opp_position_all_per_poss",
    ])
    feature_cols = numeric_feats + list(encoded_feature_names)

    X = encoded[feature_cols].fillna(0)
    y = encoded["points"].astype(float)
    return X, y


def train(args: argparse.Namespace) -> None:
    X, y = build_features()
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    params = {
        "objective": "regression",
        "metric": ["l1", "l2"],
        "learning_rate": args.learning_rate,
        "num_leaves": args.num_leaves,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "min_data_in_leaf": 20,
        "verbose": -1,
    }

    lgb_train = lgb.Dataset(X_train, label=y_train)
    lgb_val = lgb.Dataset(X_val, label=y_val)
    model = lgb.train(
        params,
        lgb_train,
        valid_sets=[lgb_train, lgb_val],
        valid_names=["train", "valid"],
        num_boost_round=args.num_boost_round,
        early_stopping_rounds=50,
        verbose_eval=False,
    )

    # Evaluation
    y_pred = model.predict(X_val)
    mae = mean_absolute_error(y_val, y_pred)
    r2 = r2_score(y_val, y_pred)

    # Save model to registry
    registry = settings.model_registry_uri
    model_filename = args.model_filename or settings.model_filename
    if registry.startswith("gs://"):
        dest = f"{registry.rstrip('/')}/{model_filename}"
    else:
        dest = os.path.join(registry, model_filename)
    uri = save_model_artifact(model, dest)

    # Log run
    run_row = {
        "run_id": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "model_uri": uri,
        "params_learning_rate": args.learning_rate,
        "params_num_leaves": args.num_leaves,
        "params_num_boost_round": args.num_boost_round,
        "metric_mae": float(mae),
        "metric_r2": float(r2),
        "env": settings.app_env,
    }
    log_run_to_bigquery("model_runs", [run_row])

    print(f"Saved model to {uri}. MAE={mae:.3f} R2={r2:.3f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train LightGBM model for player points")
    parser.add_argument("--learning_rate", type=float, default=0.05)
    parser.add_argument("--num_leaves", type=int, default=64)
    parser.add_argument("--num_boost_round", type=int, default=1000)
    parser.add_argument("--model_filename", type=str, default=None)
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    train(args)

