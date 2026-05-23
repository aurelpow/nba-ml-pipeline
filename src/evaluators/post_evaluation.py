import logging
import os
from typing import Dict
import numpy as np
import pandas as pd
import requests

from src.targets.fantasy_points import compute_fantasy_points
from common.utils import parse_minutes
from common.constants import (
    CONFIDENCE_TIER_BLUE,
    CONFIDENCE_TIER_GREEN,
    EVAL_MAE_THRESHOLDS,
    MEASURE_PREDICTED_FANTASY_POINTS,
)
from common.raw_columns import *
from common.io_utils import (
    BoxscoreFileName,
    EvaluationDetailFileName,
    EvaluationFileName,
    PredictionsFileName,
    save_database,
    load_data,
    delete_rows_by_evaluation_date,
)
from common.singleton_meta import SingletonMeta

logger = logging.getLogger(__name__)


class PostGameEvaluator(metaclass=SingletonMeta):
    def __init__(
        self,
        date: str | None = None,
        save_mode: str = "bq",
        min_sample_size: int = 0,
        webhook_url: str | None = None,
    ):
        if date is None:
            date = (pd.Timestamp.today() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        self.date = date
        self.save_mode = save_mode
        self.min_sample_size = min_sample_size
        self._webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def read_data(self) ->  Dict[str, pd.DataFrame]:
        """Load Measure=2 (fantasy) predictions for self.date."""
        
        logger.info(f"Loading data...")

        box: pd.DataFrame = load_data(BoxscoreFileName, mode=self.save_mode)
        
        predictions: pd.DataFrame = load_data(PredictionsFileName, mode=self.save_mode)

        return {"boxscore": box,
                 "predictions": predictions}

    def _filter_boxscore(self, box: pd.DataFrame) -> pd.DataFrame:
        """
        Filter boxscore to rows for self.date where minutes > 0 (i.e. player actually played).
        This ensures we only evaluate on players who had a chance to earn fantasy points. 
        Args:
            - box: raw boxscore dataframe with all dates and players
        Returns:
            - box_filtered: filtered dataframe for evaluation
        """

        minutes_float: pd.Series = box[minutes_col].apply(parse_minutes)
        box_filtered: pd.DataFrame = box[
            (pd.to_datetime(box[game_date_col]).dt.strftime("%Y-%m-%d") == self.date) &
            (minutes_float > 0)
        ]

        logger.info(f"Loaded {len(box_filtered)} boxscore rows, mode {self.save_mode} for {self.date}")
        return box_filtered
    
    def _filter_predictions(self, predictions: pd.DataFrame) -> pd.DataFrame:
        """ 
        Filter predictions to rows for self.date and Measure=2 (fantasy points).
        Args:
            - predictions: raw predictions dataframe with all dates, measures, and players
        Returns:
            - predictions_filtered: filtered dataframe for evaluation
        """
        predictions_filtered: pd.DataFrame = predictions[
            (pd.to_datetime(predictions[game_date_col_alt]).dt.strftime("%Y-%m-%d") == self.date) &
            (predictions[measure_col] == MEASURE_PREDICTED_FANTASY_POINTS)
        ]
        logger.info(f"Loaded {len(predictions_filtered)} predictions for {self.date}")
        return predictions_filtered
    
    def _calculate_fantasy_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate fantasy points for each player-game in the boxscore dataframe using the compute_fantasy_points function.
        Args:
            - df: filtered boxscore dataframe for self.date with minutes > 0
        Returns:
            - df: dataframe with fantasy points calculated in 'fantasy_points' column
        """
        # Use the compute_fantasy_points function to calculate fantasy points based on boxscore stats
        df: pd.DataFrame = compute_fantasy_points(df)
        return df

    def _merge(self, predictions: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
        """Inner-join predictions to actuals on person_id; drop incomplete rows.
        Args:
            - predictions: filtered predictions dataframe for self.date and Measure=2
            - actuals: filtered boxscore dataframe for self.date with minutes > 0
        Returns:
            - merged: dataframe with predictions and actual ttfl_score, ready for metric computation
        """
        if predictions.empty or actuals.empty:
            logger.warning("Empty predictions or actuals — cannot merge.")
            return pd.DataFrame()

        merged = predictions.merge(
            actuals[[person_id_col_alt, fantasy_points_col]],   # boxscore uses person_id
            left_on=person_id_col_alt,                      # predictions use personId
            right_on=person_id_col_alt,                         # actuals use person_id
            how="inner",
        )
        merged = merged.dropna(subset=[predictions_col, fantasy_points_col])
        logger.info(f"Merged {len(merged)} player-game rows for evaluation")
        return merged

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _assign_tier(self, confidence: float) -> str:
        if confidence >= CONFIDENCE_TIER_GREEN:
            return "Green"
        if confidence >= CONFIDENCE_TIER_BLUE:
            return "Blue"
        return "Orange"

    def _compute_metrics(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Compute evaluation metrics (MAE, RMSE, Bias, Correlation) for each confidence tier and overall (Global).
        Also prepare a detailed dataframe with player-level errors for further analysis.
        Args:
            - df: merged dataframe with predictions and actual fantasy points, plus confidence scores
            Returns:
            - aggregated_df: dataframe with metrics aggregated by confidence tier and overall
            - detail_df: dataframe with player-level predictions, actuals, errors, and confidence for detailed analysis
        """
        # Create 'tier' column based on confidence, and calculate error and absolute error
        df = df.copy() # Avoid SettingWithCopyWarning
        df["tier"] = df["confidence"].apply(self._assign_tier)
        df["error"] = df[fantasy_points_col] - df[predictions_col]
        df["abs_error"] = df["error"].abs()

        # Prepare detailed dataframe with player-level errors and confidence for further analysis
        detail_df = pd.DataFrame(
            {
                "evaluation_date": self.date,
                game_date_col: self.date,
                "game_id": df[game_id_col].astype(str),     # source "gameId" from predictions → output "game_id"
                person_id_col: df[person_id_col_alt],      # source "personId" → output "person_id"
                player_slug_col: df[player_slug_col],
                "prediction": df[predictions_col],
                "actual": df[fantasy_points_col],
                "error": df["error"],
                "abs_error": df["abs_error"],
                "tier": df["tier"],
                "confidence": df["confidence"],
            }
        )

        tiers = sorted(df["tier"].unique().tolist()) + ["Global"]
        rows = []

        for tier in tiers:
            tier_df = df if tier == "Global" else df[df["tier"] == tier]

            if len(tier_df) < self.min_sample_size:
                logger.warning(
                    f"Tier {tier}: {len(tier_df)} players < min_sample_size={self.min_sample_size}. Skipping."
                )
                continue

            if tier_df.empty:
                continue

            mae = tier_df["abs_error"].mean()
            rmse = np.sqrt((tier_df["error"] ** 2).mean())
            corr = tier_df[predictions_col].corr(tier_df[fantasy_points_col])
            threshold = EVAL_MAE_THRESHOLDS.get(tier)

            rows.append(
                {
                    "evaluation_date": self.date,
                    "tier": tier,
                    "n_players": len(tier_df),
                    "mae": round(mae, 4),
                    "rmse": round(rmse, 4),
                    "bias": round(tier_df["error"].mean(), 4),
                    "pct_within_5": round((tier_df["abs_error"] <= 5).mean() * 100, 2),
                    "pct_within_10": round(
                        (tier_df["abs_error"] <= 10).mean() * 100, 2
                    ),
                    "pct_within_15": round(
                        (tier_df["abs_error"] <= 15).mean() * 100, 2
                    ),
                    "correlation": round(corr, 4),
                    "alert_triggered": bool(threshold is not None and mae > threshold),
                }
            )

        return pd.DataFrame(rows), detail_df

    # ------------------------------------------------------------------
    # Discord alert
    # ------------------------------------------------------------------

    def _send_discord_alert(self, aggregated_df: pd.DataFrame) -> None:
        if not self._webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not set — skipping Discord alert")
            return

        tier_colors = {"Green": 0x2ECC71, "Blue": 0x3498DB, "Orange": 0xE67E22}

        breaching = aggregated_df[
            aggregated_df["alert_triggered"] & (aggregated_df["tier"] != "Global")
        ]

        for _, row in breaching.iterrows():
            tier = row["tier"]
            embed = {
                "title": f"⚠️ TTFL Model Alert — {tier} Tier",
                "description": f"MAE exceeded threshold for **{self.date}**",
                "color": tier_colors.get(tier, 0x95A5A6),
                "fields": [
                    {"name": "Tier", "value": tier, "inline": True},
                    {"name": "MAE", "value": f"{row['mae']:.2f}", "inline": True},
                    {
                        "name": "Threshold",
                        "value": str(EVAL_MAE_THRESHOLDS[tier]),
                        "inline": True,
                    },
                    {
                        "name": "Players",
                        "value": str(int(row["n_players"])),
                        "inline": True,
                    },
                    {"name": "RMSE", "value": f"{row['rmse']:.2f}", "inline": True},
                    {"name": "Bias", "value": f"{row['bias']:+.2f}", "inline": True},
                ],
                "footer": {"text": "TTFLab · NBA ML Pipeline"},
            }
            try:
                resp = requests.post(
                    self._webhook_url, json={"embeds": [embed]}, timeout=10
                )
                resp.raise_for_status()
                logger.info(
                    f"✅ Discord alert sent for {tier} tier (MAE={row['mae']:.2f})"
                )
            except Exception as exc:
                logger.error(f"❌ Discord alert failed for {tier}: {exc}")


    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Execute the post-game evaluation process:
        1. Load and filter data
        2. Calculate fantasy points from boxscore
        3. Merge predictions with actual fantasy points
        4. Compute metrics by confidence tier
        5. Save results to BigQuery or CSV
        6. Send Discord alert if any tier breaches MAE thresholds
        """
        try:
            logger.info(f"Starting post-game evaluation for {self.date}")

            # 1.1 Load data
            data_map: Dict[str, pd.DataFrame] = self.read_data()

            if data_map["boxscore"].empty or data_map["predictions"].empty:
                logger.warning(f"No data available for {self.date} — evaluation skipped.")
                return

            # 1.2 Filter and prepare data
            box_filtered: pd.DataFrame = self._filter_boxscore(data_map["boxscore"])
            predictions_filtered: pd.DataFrame = self._filter_predictions(data_map["predictions"])

            # 2. Calculate fantasy points for actuals
            actuals_score: pd.DataFrame = self._calculate_fantasy_score(box_filtered)
            
            # 3. Merge
            merged_df: pd.DataFrame = self._merge(predictions=predictions_filtered,
                                                  actuals= actuals_score)

            if merged_df.empty:
                logger.warning(f"No matched data for {self.date} — evaluation skipped.")
                return
            
            # 4. Compute metrics and save results
            aggregated_df, detail_df = self._compute_metrics(merged_df)

            if aggregated_df.empty:
                logger.warning("No metrics computed — evaluation skipped.")
                return

            # 5. Save results and send alerts (idempotent: delete before append).
            #    Local mode overwrites the CSV in save_database, so the
            #    BigQuery delete-by-evaluation_date only applies in bq mode.
            if self.save_mode == "bq":
                for table in [EvaluationFileName, EvaluationDetailFileName]:
                    delete_rows_by_evaluation_date(table, self.date)
            save_database(  df = aggregated_df,
                            table_name = EvaluationFileName,
                            mode=self.save_mode,
                            write_disposition="WRITE_APPEND",
                            skip_dedup=True,
                            )
            save_database(  df = detail_df,
                            table_name = EvaluationDetailFileName,
                            mode=self.save_mode,
                            write_disposition="WRITE_APPEND",
                            skip_dedup=True,
                            )
            self._send_discord_alert(aggregated_df)

        except Exception as e:
            logger.error(f"Prediction pipeline failed: {str(e)}")
            raise