import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from common.singleton_meta import SingletonMeta
from src.evaluators.post_evaluation import PostGameEvaluator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATE = "2025-04-29"


def _make_evaluator(**kwargs) -> PostGameEvaluator:
    """Return a fresh evaluator, bypassing the Singleton for each test."""
    SingletonMeta._instances.pop(PostGameEvaluator, None)
    return PostGameEvaluator(date=DATE, save_mode="local", **kwargs)


def _make_boxscore_stats(**overrides) -> dict:
    """Minimal boxscore stats columns required by compute_fantasy_points."""
    base = {
        "points": 20,
        "reboundsTotal": 5,
        "assists": 5,
        "steals": 1,
        "blocks": 1,
        "turnovers": 2,
        "fieldGoalsMade": 8,
        "fieldGoalsAttempted": 15,
        "threePointersMade": 2,
        "threePointersAttempted": 5,
        "freeThrowsMade": 2,
        "freeThrowsAttempted": 3,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------

class TestAssignTier(unittest.TestCase):

    def setUp(self):
        self.ev = _make_evaluator()

    def test_green_at_boundary(self):
        self.assertEqual(self.ev._assign_tier(0.60), "Green")

    def test_green_above_boundary(self):
        self.assertEqual(self.ev._assign_tier(0.95), "Green")

    def test_blue_at_lower_boundary(self):
        self.assertEqual(self.ev._assign_tier(0.30), "Blue")

    def test_blue_just_below_green(self):
        self.assertEqual(self.ev._assign_tier(0.599), "Blue")

    def test_orange_just_below_blue(self):
        self.assertEqual(self.ev._assign_tier(0.299), "Orange")

    def test_orange_zero(self):
        self.assertEqual(self.ev._assign_tier(0.0), "Orange")


# ---------------------------------------------------------------------------
# _filter_boxscore
# ---------------------------------------------------------------------------

class TestFilterBoxscore(unittest.TestCase):

    def setUp(self):
        self.ev = _make_evaluator()
        self.box = pd.DataFrame({
            "game_date": [DATE, DATE, "2025-04-28", DATE],
            "minutes":   [30.0,  0.0,  25.0,        15.0],
            "person_id": [1,     2,    3,            4],
        })

    def test_keeps_correct_date_with_minutes(self):
        result = self.ev._filter_boxscore(self.box)
        self.assertSetEqual(set(result["person_id"]), {1, 4})

    def test_excludes_zero_minutes(self):
        result = self.ev._filter_boxscore(self.box)
        self.assertNotIn(2, result["person_id"].values)

    def test_excludes_wrong_date(self):
        result = self.ev._filter_boxscore(self.box)
        self.assertNotIn(3, result["person_id"].values)

    def test_empty_input_returns_empty(self):
        empty = pd.DataFrame(columns=["game_date", "minutes", "person_id"])
        self.assertTrue(self.ev._filter_boxscore(empty).empty)


# ---------------------------------------------------------------------------
# _filter_predictions
# ---------------------------------------------------------------------------

class TestFilterPredictions(unittest.TestCase):

    def setUp(self):
        self.ev = _make_evaluator()
        self.preds = pd.DataFrame({
            "gameDate":    [DATE,  DATE,  "2025-04-28", DATE],
            "Measure":     [2,     1,     2,            2],
            "person_id":   [1,     2,     3,            4],
            "Predictions": [50.0,  30.0,  40.0,         25.0],
            "confidence":  [0.7,   0.4,   0.5,          0.2],
            "player_slug": ["p1",  "p2",  "p3",         "p4"],
            "gameId":      ["g1",  "g2",  "g3",         "g4"],
        })

    def test_keeps_measure_2_and_correct_date(self):
        result = self.ev._filter_predictions(self.preds)
        self.assertSetEqual(set(result["person_id"]), {1, 4})

    def test_excludes_wrong_measure(self):
        result = self.ev._filter_predictions(self.preds)
        self.assertNotIn(2, result["person_id"].values)

    def test_excludes_wrong_date(self):
        result = self.ev._filter_predictions(self.preds)
        self.assertNotIn(3, result["person_id"].values)

    def test_empty_input_returns_empty(self):
        empty = pd.DataFrame(columns=["gameDate", "Measure", "person_id"])
        self.assertTrue(self.ev._filter_predictions(empty).empty)


# ---------------------------------------------------------------------------
# _calculate_fantasy_score
# ---------------------------------------------------------------------------

class TestCalculateFantasyScore(unittest.TestCase):

    def setUp(self):
        self.ev = _make_evaluator()

    def test_known_score(self):
        # POS: 20+5+5+1+1+8+2+2 = 44 / NEG: 2+7+3+1 = 13 → 31
        df = pd.DataFrame([_make_boxscore_stats()])
        result = self.ev._calculate_fantasy_score(df)
        self.assertIn("fantasy_points", result.columns)
        self.assertEqual(result["fantasy_points"].iloc[0], 31)

    def test_missing_stat_column_raises(self):
        df = pd.DataFrame({"points": [10]})
        with self.assertRaises(ValueError):
            self.ev._calculate_fantasy_score(df)


# ---------------------------------------------------------------------------
# _merge
# ---------------------------------------------------------------------------

class TestMerge(unittest.TestCase):

    def setUp(self):
        self.ev = _make_evaluator()
        self.predictions = pd.DataFrame({
            "personId":    [1,    2,    3],
            "gameId":      ["g1", "g2", "g3"],
            "player_slug": ["p1", "p2", "p3"],
            "Predictions": [50.0, 40.0, 25.0],
            "confidence":  [0.7,  0.4,  0.2],
        })
        # person 99 in actuals but not predictions; person 3 in predictions but not actuals
        self.actuals = pd.DataFrame({
            "personId":      [1,    2,    99],
            "fantasy_points": [55.0, 35.0, 20.0],
        })

    def test_inner_join_keeps_matching_only(self):
        merged = self.ev._merge(self.predictions, self.actuals)
        self.assertSetEqual(set(merged["personId"]), {1, 2})

    def test_unmatched_prediction_excluded(self):
        merged = self.ev._merge(self.predictions, self.actuals)
        self.assertNotIn(3, merged["personId"].values)

    def test_unmatched_actual_excluded(self):
        merged = self.ev._merge(self.predictions, self.actuals)
        self.assertNotIn(99, merged["personId"].values)

    def test_empty_predictions_returns_empty(self):
        self.assertTrue(self.ev._merge(pd.DataFrame(), self.actuals).empty)

    def test_empty_actuals_returns_empty(self):
        self.assertTrue(self.ev._merge(self.predictions, pd.DataFrame()).empty)

    def test_drops_rows_with_nan_prediction(self):
        preds = self.predictions.copy()
        preds.loc[0, "Predictions"] = np.nan
        merged = self.ev._merge(preds, self.actuals)
        self.assertNotIn(1, merged["personId"].values)

    def test_drops_rows_with_nan_actual(self):
        actuals = self.actuals.copy()
        actuals.loc[0, "fantasy_points"] = np.nan
        merged = self.ev._merge(self.predictions, actuals)
        self.assertNotIn(1, merged["personId"].values)


# ---------------------------------------------------------------------------
# _compute_metrics
# ---------------------------------------------------------------------------

def _make_merged_df() -> pd.DataFrame:
    """One player per tier, errors chosen so MAEs are below alert thresholds."""
    return pd.DataFrame({
        "personId":       [1,    2,    3],      # camelCase from predictions side
        "person_id":      [1,    2,    3],      # snake_case from actuals side (kept after left/right merge)
        "gameId":         ["g1", "g2", "g3"],
        "player_slug":    ["p1", "p2", "p3"],
        "Predictions":    [50.0, 40.0, 25.0],
        "fantasy_points": [55.0, 30.0, 20.0],  # errors: +5, -10, -5
        "confidence":     [0.7,   0.4,  0.1],  # Green, Blue, Orange
    })


class TestComputeMetrics(unittest.TestCase):

    def setUp(self):
        self.ev = _make_evaluator()

    def test_all_tiers_present(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        self.assertSetEqual(set(agg["tier"]), {"Green", "Blue", "Orange", "Global"})

    def test_green_mae(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Green"].iloc[0]
        self.assertAlmostEqual(row["mae"], 5.0)

    def test_blue_mae(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Blue"].iloc[0]
        self.assertAlmostEqual(row["mae"], 10.0)

    def test_global_n_players(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Global"].iloc[0]
        self.assertEqual(row["n_players"], 3)

    def test_green_bias(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Green"].iloc[0]
        self.assertAlmostEqual(row["bias"], 5.0)

    def test_green_pct_within_5(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Green"].iloc[0]
        self.assertAlmostEqual(row["pct_within_5"], 100.0)  # |5| <= 5

    def test_blue_pct_within_5(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Blue"].iloc[0]
        self.assertAlmostEqual(row["pct_within_5"], 0.0)    # |10| > 5

    def test_alert_triggered_above_threshold(self):
        # Green MAE threshold = 8; error of 25 should trigger alert
        df = pd.DataFrame({
            "personId":       [1],
            "person_id":      [1],
            "gameId":         ["g1"],
            "player_slug":    ["p1"],
            "Predictions":    [50.0],
            "fantasy_points": [75.0],
            "confidence":     [0.7],
        })
        agg, _ = self.ev._compute_metrics(df)
        row = agg.loc[agg["tier"] == "Green"].iloc[0]
        self.assertTrue(row["alert_triggered"])

    def test_alert_not_triggered_below_threshold(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        row = agg.loc[agg["tier"] == "Green"].iloc[0]
        self.assertFalse(row["alert_triggered"])  # MAE=5 < 8

    def test_global_alert_never_triggered(self):
        """Global has no threshold so alert must always be False."""
        df = pd.DataFrame({
            "personId":       [1],
            "person_id":      [1],
            "gameId":         ["g1"],
            "player_slug":    ["p1"],
            "Predictions":    [10.0],
            "fantasy_points": [100.0],
            "confidence":     [0.7],
        })
        agg, _ = self.ev._compute_metrics(df)
        row = agg.loc[agg["tier"] == "Global"].iloc[0]
        self.assertFalse(row["alert_triggered"])

    def test_detail_df_schema(self):
        _, detail = self.ev._compute_metrics(_make_merged_df())
        expected = {
            "evaluation_date", "game_date", "game_id", "person_id",
            "player_slug", "prediction", "actual", "error", "abs_error",
            "tier", "confidence",
        }
        self.assertTrue(expected.issubset(set(detail.columns)))

    def test_detail_df_row_count(self):
        _, detail = self.ev._compute_metrics(_make_merged_df())
        self.assertEqual(len(detail), 3)

    def test_min_sample_size_skips_single_player_tiers(self):
        ev = _make_evaluator(min_sample_size=2)
        agg, _ = ev._compute_metrics(_make_merged_df())
        # Each non-global tier has 1 player → skipped; only Global (3) survives
        tiers = set(agg["tier"])
        self.assertNotIn("Green", tiers)
        self.assertNotIn("Blue", tiers)
        self.assertNotIn("Orange", tiers)
        self.assertIn("Global", tiers)

    def test_rmse_larger_than_or_equal_mae(self):
        agg, _ = self.ev._compute_metrics(_make_merged_df())
        for _, row in agg.iterrows():
            self.assertGreaterEqual(row["rmse"], row["mae"])


# ---------------------------------------------------------------------------
# _send_discord_alert
# ---------------------------------------------------------------------------

def _make_breaching_agg() -> pd.DataFrame:
    return pd.DataFrame({
        "tier":            ["Green",  "Global"],
        "n_players":       [5,        10],
        "mae":             [15.0,     8.0],   # Green breaches threshold=8
        "rmse":            [16.0,     9.0],
        "bias":            [3.0,      1.0],
        "alert_triggered": [True,     False],
    })


def _make_ok_agg() -> pd.DataFrame:
    return pd.DataFrame({
        "tier":            ["Green",  "Global"],
        "n_players":       [5,        10],
        "mae":             [4.0,      5.0],
        "rmse":            [5.0,      6.0],
        "bias":            [1.0,      1.0],
        "alert_triggered": [False,    False],
    })


class TestSendDiscordAlert(unittest.TestCase):

    def setUp(self):
        SingletonMeta._instances.pop(PostGameEvaluator, None)

    def test_no_http_call_when_webhook_not_set(self):
        ev = _make_evaluator()
        ev._webhook_url = None
        with patch("src.evaluators.post_evaluation.requests.post") as mock_post:
            ev._send_discord_alert(_make_breaching_agg())
            mock_post.assert_not_called()

    def test_calls_webhook_once_for_single_breaching_tier(self):
        ev = _make_evaluator()
        ev._webhook_url = "https://fake.webhook/abc"
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.evaluators.post_evaluation.requests.post", return_value=mock_resp) as mock_post:
            ev._send_discord_alert(_make_breaching_agg())
            mock_post.assert_called_once()

    def test_no_call_when_no_tier_breaches(self):
        ev = _make_evaluator()
        ev._webhook_url = "https://fake.webhook/abc"
        with patch("src.evaluators.post_evaluation.requests.post") as mock_post:
            ev._send_discord_alert(_make_ok_agg())
            mock_post.assert_not_called()

    def test_global_tier_never_triggers_alert(self):
        ev = _make_evaluator()
        ev._webhook_url = "https://fake.webhook/abc"
        # Mark Global as alert_triggered=True; it must still be excluded
        agg = _make_breaching_agg().copy()
        agg.loc[agg["tier"] == "Global", "alert_triggered"] = True
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.evaluators.post_evaluation.requests.post", return_value=mock_resp) as mock_post:
            ev._send_discord_alert(agg)
            # Only Green should fire, not Global
            self.assertEqual(mock_post.call_count, 1)

    def test_failed_request_does_not_raise(self):
        ev = _make_evaluator()
        ev._webhook_url = "https://fake.webhook/abc"
        with patch(
            "src.evaluators.post_evaluation.requests.post",
            side_effect=Exception("Connection refused"),
        ):
            try:
                ev._send_discord_alert(_make_breaching_agg())
            except Exception:
                self.fail("_send_discord_alert raised on HTTP error")

    def test_embed_contains_tier_and_mae(self):
        ev = _make_evaluator()
        ev._webhook_url = "https://fake.webhook/abc"
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        with patch("src.evaluators.post_evaluation.requests.post", return_value=mock_resp) as mock_post:
            ev._send_discord_alert(_make_breaching_agg())
            payload = mock_post.call_args.kwargs["json"]
            embed_fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
            self.assertEqual(embed_fields["Tier"], "Green")
            self.assertEqual(embed_fields["MAE"], "15.00")


# ---------------------------------------------------------------------------
# run() — end-to-end with mocked I/O
# ---------------------------------------------------------------------------

def _make_full_boxscore() -> pd.DataFrame:
    rows = []
    for pid in [1, 2]:
        row = {"game_date": DATE, "minutes": 30.0, "personId": pid}
        row.update(_make_boxscore_stats())
        rows.append(row)
    return pd.DataFrame(rows)


def _make_full_predictions() -> pd.DataFrame:
    return pd.DataFrame({
        "gameDate":    [DATE,  DATE],
        "Measure":     [2,     2],
        "personId":    [1,     2],
        "Predictions": [50.0,  30.0],
        "confidence":  [0.7,   0.4],
        "player_slug": ["p1",  "p2"],
        "gameId":      ["g1",  "g2"],
    })


class TestRunIntegration(unittest.TestCase):

    def setUp(self):
        SingletonMeta._instances.pop(PostGameEvaluator, None)

    @patch("src.evaluators.post_evaluation.load_data")
    def test_run_skips_save_when_no_data(self, mock_load):
        mock_load.return_value = pd.DataFrame()
        ev = _make_evaluator()
        with patch("src.evaluators.post_evaluation.save_database") as mock_save:
            ev.run()
            mock_save.assert_not_called()

    @patch("src.evaluators.post_evaluation.load_data")
    def test_run_calls_save_and_discord_when_data_available(self, mock_load):
        mock_load.side_effect = [_make_full_boxscore(), _make_full_predictions()]
        ev = _make_evaluator()
        with patch("src.evaluators.post_evaluation.save_database") as mock_save, \
             patch("src.evaluators.post_evaluation.delete_rows_by_evaluation_date"), \
             patch.object(ev, "_send_discord_alert") as mock_discord:
            ev.run()
            self.assertEqual(mock_save.call_count, 2)  # once per table
            mock_discord.assert_called_once()

    @patch("src.evaluators.post_evaluation.load_data")
    def test_run_save_receives_two_dataframes(self, mock_load):
        mock_load.side_effect = [_make_full_boxscore(), _make_full_predictions()]
        ev = _make_evaluator()
        with patch("src.evaluators.post_evaluation.save_database") as mock_save, \
             patch("src.evaluators.post_evaluation.delete_rows_by_evaluation_date"), \
             patch.object(ev, "_send_discord_alert"):
            ev.run()
            aggregated_df = mock_save.call_args_list[0].kwargs["df"]
            detail_df = mock_save.call_args_list[1].kwargs["df"]
            self.assertIn("tier", aggregated_df.columns)
            self.assertIn("mae", aggregated_df.columns)
            self.assertIn("person_id", detail_df.columns)
            self.assertIn("abs_error", detail_df.columns)

    @patch("src.evaluators.post_evaluation.load_data")
    def test_run_propagates_exceptions(self, mock_load):
        mock_load.side_effect = RuntimeError("BQ connection failed")
        ev = _make_evaluator()
        with self.assertRaises(RuntimeError):
            ev.run()


if __name__ == "__main__":
    unittest.main()
