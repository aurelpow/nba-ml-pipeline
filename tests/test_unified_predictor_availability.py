"""
Unit tests for the availability filtering logic in UnifiedPredictor.get_future_games_players()
and the confidence score computation in UnifiedPredictor.persist().

Key behaviour under test (availability filter):
  - Only players with play_probability < PREDICTION_EXCLUDE_THRESHOLD are excluded.
    By default that means only 'Out' players (play_probability=0.02).
  - 'Doubtful' players (play_probability=0.15) are now included and receive a prediction.
  - 'Questionable' players (play_probability=0.50) are included.
  - Players not present in the availability table default to play_probability=0.97 (Available)
    and are always included.
  - When the availability DataFrame is empty, all roster players are included.

Key behaviour under test (confidence score):
  confidence = play_probability × stability × sample_conf
  stability   = 1 - min(volatility / CONFIDENCE_MAX_VOLATILITY, 1.0)
  sample_conf = min(games_played / CONFIDENCE_SAMPLE_SIZE_CAP, 1.0)
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

from common.singleton_meta import SingletonMeta
from common.constants import (
    PREDICTION_EXCLUDE_THRESHOLD,
    CONFIDENCE_MAX_VOLATILITY,
    CONFIDENCE_SAMPLE_SIZE_CAP,
)


def _reset_singleton(cls):
    if cls in SingletonMeta._instances:
        del SingletonMeta._instances[cls]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

GAME_DATE = "2026-04-02"


def _make_schedule_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "gameId": ["0022600001"],
            "gameDate": [GAME_DATE],
            "homeTeam_teamId": [1610612747],  # LAL
            "awayTeam_teamId": [1610612744],  # GSW
        }
    )


def _make_players_df() -> pd.DataFrame:
    """4 players: 2 LAL, 2 GSW."""
    return pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "player_slug": [
                "lebron-james",
                "anthony-davis",
                "stephen-curry",
                "klay-thompson",
            ],
            "team_id": [1610612747, 1610612747, 1610612744, 1610612744],
            "position": ["F", "C", "G", "G"],
        }
    )


def _make_availability_df(rows: list[dict]) -> pd.DataFrame:
    """
    Each row dict should have: person_id, play_probability, status (optional).
    Missing keys are filled with defaults.
    """
    defaults = {"game_date": GAME_DATE, "is_available": True, "status": "Available"}
    filled = [{**defaults, **r} for r in rows]
    return pd.DataFrame(filled)


# ---------------------------------------------------------------------------
# Helper to call get_future_games_players() in isolation
# ---------------------------------------------------------------------------


def _call_get_future_games_players(availability_df: pd.DataFrame) -> pd.DataFrame:
    """
    Instantiate a fresh UnifiedPredictor (singleton reset each call) and invoke
    get_future_games_players with fully mocked I/O.
    """
    from src.predictors.unified_predictor import UnifiedPredictor
    from common.io_utils import (
        ScheduleFileName,
        PlayersFileName,
        AvailabilityFileName,
        BoxscoreFileName,
        AdvancedBoxscoreFileName,
    )

    _reset_singleton(UnifiedPredictor)

    with patch("src.predictors.unified_predictor.load_model_artifact"):
        predictor = UnifiedPredictor(
            target="fantasy_points",
            save_mode="local",
            date=GAME_DATE,
            model_path="/fake/path",
        )

    data_map = {
        ScheduleFileName: _make_schedule_df(),
        PlayersFileName: _make_players_df(),
        AvailabilityFileName: availability_df,
        BoxscoreFileName: pd.DataFrame(),
        AdvancedBoxscoreFileName: pd.DataFrame(),
    }

    return predictor.get_future_games_players(data_map)


# ---------------------------------------------------------------------------
# Helper to call persist() in isolation
# ---------------------------------------------------------------------------


def _make_predictor():
    from src.predictors.unified_predictor import UnifiedPredictor

    _reset_singleton(UnifiedPredictor)
    with patch("src.predictors.unified_predictor.load_model_artifact"):
        return UnifiedPredictor(
            target="fantasy_points",
            save_mode="local",
            date=GAME_DATE,
            model_path="/fake/path",
        )


def _make_pred_rows(person_ids, predictions, measure=2):
    """Minimal prediction rows DataFrame."""
    return pd.DataFrame(
        {
            "gameId": ["G1"] * len(person_ids),
            "gameDate": [GAME_DATE] * len(person_ids),
            "teamId": [1] * len(person_ids),
            "opponentId": [2] * len(person_ids),
            "personId": person_ids,
            "player_slug": [f"player-{i}" for i in person_ids],
            "Measure": [measure] * len(person_ids),
            "Predictions": predictions,
        }
    )


def _call_persist(predictor, pred_rows, vol_rows, availability_df, games_played_df):
    """Call persist() with save_predictions mocked out; return the saved DataFrame."""
    import common.constants as c
    from src.predictors.unified_predictor import UnifiedPredictor

    saved = {}

    def capture(df, table_name, mode):
        saved["df"] = df.copy()

    combined = pd.concat([pred_rows, vol_rows], ignore_index=True)

    with patch(
        "src.predictors.unified_predictor.save_predictions", side_effect=capture
    ):
        predictor.persist(
            predictions_df=combined,
            availability_df=availability_df,
            games_played_df=games_played_df,
        )
    return saved["df"]


# ---------------------------------------------------------------------------
# Tests — availability filter
# ---------------------------------------------------------------------------


class TestPredictorAvailabilityFilter(unittest.TestCase):
    def tearDown(self):
        from src.predictors.unified_predictor import UnifiedPredictor

        _reset_singleton(UnifiedPredictor)

    # ------------------------------------------------------------------
    # PREDICTION_EXCLUDE_THRESHOLD sanity
    # ------------------------------------------------------------------

    def test_exclude_threshold_above_out(self):
        """PREDICTION_EXCLUDE_THRESHOLD must be > Out probability (0.02)."""
        self.assertGreater(PREDICTION_EXCLUDE_THRESHOLD, 0.02)

    def test_exclude_threshold_below_doubtful(self):
        """PREDICTION_EXCLUDE_THRESHOLD must be <= Doubtful probability (0.15)
        so that Doubtful players are NOT excluded."""
        self.assertLessEqual(PREDICTION_EXCLUDE_THRESHOLD, 0.15)

    # ------------------------------------------------------------------
    # Out players excluded
    # ------------------------------------------------------------------

    def test_out_player_excluded(self):
        """A player with play_probability=0.02 (Out) must not appear in output."""
        avail = _make_availability_df(
            [
                {"person_id": 1, "play_probability": 0.02, "status": "Out"},
            ]
        )
        result = _call_get_future_games_players(avail)
        self.assertNotIn(1, result["person_id"].values)

    def test_out_player_excluded_other_players_present(self):
        """Excluding one Out player must not affect the others."""
        avail = _make_availability_df(
            [
                {"person_id": 1, "play_probability": 0.02, "status": "Out"},
            ]
        )
        result = _call_get_future_games_players(avail)
        present = set(result["person_id"].unique())
        self.assertIn(2, present)
        self.assertIn(3, present)
        self.assertIn(4, present)

    def test_multiple_out_players_excluded(self):
        """Multiple Out players on the same team are all excluded."""
        avail = _make_availability_df(
            [
                {"person_id": 1, "play_probability": 0.02, "status": "Out"},
                {"person_id": 2, "play_probability": 0.02, "status": "Out"},
            ]
        )
        result = _call_get_future_games_players(avail)
        present = set(result["person_id"].unique())
        self.assertNotIn(1, present)
        self.assertNotIn(2, present)
        self.assertIn(3, present)
        self.assertIn(4, present)

    # ------------------------------------------------------------------
    # Doubtful / Questionable players included
    # ------------------------------------------------------------------

    def test_doubtful_player_included(self):
        """A player with play_probability=0.15 (Doubtful) must appear in output."""
        avail = _make_availability_df(
            [
                {"person_id": 1, "play_probability": 0.15, "status": "Doubtful"},
            ]
        )
        result = _call_get_future_games_players(avail)
        self.assertIn(1, result["person_id"].values)

    def test_questionable_player_included(self):
        """A player with play_probability=0.50 (Questionable) must appear in output."""
        avail = _make_availability_df(
            [
                {"person_id": 3, "play_probability": 0.50, "status": "Questionable"},
            ]
        )
        result = _call_get_future_games_players(avail)
        self.assertIn(3, result["person_id"].values)

    # ------------------------------------------------------------------
    # Players not in / empty availability table
    # ------------------------------------------------------------------

    def test_player_not_in_availability_included(self):
        """Players absent from the availability table are included (healthy by default)."""
        avail = _make_availability_df([])
        result = _call_get_future_games_players(avail)
        self.assertEqual(set(result["person_id"].unique()), {1, 2, 3, 4})

    def test_empty_availability_includes_all(self):
        """When availability_df is completely empty, all roster players are included."""
        result = _call_get_future_games_players(pd.DataFrame())
        self.assertEqual(set(result["person_id"].unique()), {1, 2, 3, 4})

    # ------------------------------------------------------------------
    # Row count sanity
    # ------------------------------------------------------------------

    def test_row_count_one_out(self):
        """With 1 Out player, output should have rows for 3 players."""
        avail = _make_availability_df(
            [
                {"person_id": 1, "play_probability": 0.02, "status": "Out"},
            ]
        )
        result = _call_get_future_games_players(avail)
        self.assertEqual(len(result), 3)

    def test_row_count_no_exclusions(self):
        """With no Out players, all 4 players get a row."""
        result = _call_get_future_games_players(pd.DataFrame())
        self.assertEqual(len(result), 4)


# ---------------------------------------------------------------------------
# Tests — confidence score
# ---------------------------------------------------------------------------


class TestPredictorConfidence(unittest.TestCase):
    """
    Tests for persist() confidence computation.
    Formula:
        stability   = 1 - min(volatility / CONFIDENCE_MAX_VOLATILITY, 1.0)
        sample_conf = min(games_played / CONFIDENCE_SAMPLE_SIZE_CAP, 1.0)
        confidence  = play_probability × stability × sample_conf
    """

    def tearDown(self):
        from src.predictors.unified_predictor import UnifiedPredictor

        _reset_singleton(UnifiedPredictor)

    def _run(self, play_prob, volatility, games_played):
        """Run persist() for a single player and return their confidence value."""
        predictor = _make_predictor()

        pred_rows = _make_pred_rows([1], [30.0], measure=predictor.measure_prediction)
        vol_rows = _make_pred_rows(
            [1], [volatility], measure=predictor.measure_volatility
        )
        avail_df = _make_availability_df(
            [{"person_id": 1, "play_probability": play_prob}]
        )
        gp_df = pd.DataFrame({"personId": [1], "games_played": [games_played]})

        result = _call_persist(predictor, pred_rows, vol_rows, avail_df, gp_df)
        pred = result[result["Measure"] == predictor.measure_prediction]
        return float(pred["confidence"].iloc[0])

    # ------------------------------------------------------------------
    # confidence column exists on prediction rows
    # ------------------------------------------------------------------

    def test_confidence_column_present(self):
        """persist() output must have a 'confidence' column."""
        predictor = _make_predictor()
        pred_rows = _make_pred_rows([1], [20.0], measure=predictor.measure_prediction)
        vol_rows = _make_pred_rows([1], [5.0], measure=predictor.measure_volatility)
        avail_df = _make_availability_df([{"person_id": 1, "play_probability": 0.97}])
        gp_df = pd.DataFrame({"personId": [1], "games_played": [30]})

        result = _call_persist(predictor, pred_rows, vol_rows, avail_df, gp_df)
        self.assertIn("confidence", result.columns)

    # ------------------------------------------------------------------
    # Volatility rows carry NaN confidence
    # ------------------------------------------------------------------

    def test_volatility_rows_have_nan_confidence(self):
        """Volatility rows (Measure=4) must not have a confidence score."""
        predictor = _make_predictor()
        pred_rows = _make_pred_rows([1], [20.0], measure=predictor.measure_prediction)
        vol_rows = _make_pred_rows([1], [5.0], measure=predictor.measure_volatility)
        avail_df = _make_availability_df([{"person_id": 1, "play_probability": 0.97}])
        gp_df = pd.DataFrame({"personId": [1], "games_played": [30]})

        result = _call_persist(predictor, pred_rows, vol_rows, avail_df, gp_df)
        vol = result[result["Measure"] == predictor.measure_volatility]
        self.assertTrue(vol["confidence"].isna().all())

    # ------------------------------------------------------------------
    # Healthy, consistent, many games → near-max confidence
    # ------------------------------------------------------------------

    def test_healthy_consistent_veteran(self):
        """play_prob=0.97, low vol=5, 70 games → high confidence."""
        conf = self._run(play_prob=0.97, volatility=5.0, games_played=70)
        stability = 1 - 5.0 / CONFIDENCE_MAX_VOLATILITY
        sample_conf = 1.0
        expected = round(0.97 * stability * sample_conf, 2)
        self.assertAlmostEqual(conf, expected, places=2)
        self.assertGreater(conf, 0.60)

    # ------------------------------------------------------------------
    # Questionable player → reduced by play_probability
    # ------------------------------------------------------------------

    def test_questionable_reduces_confidence(self):
        """play_prob=0.50 halves confidence vs a healthy equivalent."""
        conf_healthy = self._run(play_prob=0.97, volatility=5.0, games_played=70)
        conf_questionable = self._run(play_prob=0.50, volatility=5.0, games_played=70)
        self.assertLess(conf_questionable, conf_healthy)

    # ------------------------------------------------------------------
    # High volatility → reduced by stability factor
    # ------------------------------------------------------------------

    def test_high_volatility_reduces_confidence(self):
        """High volatility (22) gives lower confidence than low volatility (5)."""
        conf_low_vol = self._run(play_prob=0.97, volatility=5.0, games_played=70)
        conf_high_vol = self._run(play_prob=0.97, volatility=22.0, games_played=70)
        self.assertLess(conf_high_vol, conf_low_vol)

    def test_volatility_at_cap_gives_zero_stability(self):
        """Volatility at or above CONFIDENCE_MAX_VOLATILITY → stability=0 → confidence=0."""
        conf = self._run(
            play_prob=0.97, volatility=CONFIDENCE_MAX_VOLATILITY, games_played=70
        )
        self.assertEqual(conf, 0.0)

    def test_volatility_above_cap_clamped(self):
        """Volatility above cap should still give confidence=0, not negative."""
        conf = self._run(
            play_prob=0.97, volatility=CONFIDENCE_MAX_VOLATILITY + 10, games_played=70
        )
        self.assertEqual(conf, 0.0)

    # ------------------------------------------------------------------
    # Few games → reduced by sample_conf factor
    # ------------------------------------------------------------------

    def test_few_games_reduces_confidence(self):
        """A player with 5 games has lower confidence than one with 50."""
        conf_few = self._run(play_prob=0.97, volatility=5.0, games_played=5)
        conf_many = self._run(play_prob=0.97, volatility=5.0, games_played=50)
        self.assertLess(conf_few, conf_many)

    def test_zero_games_gives_zero_confidence(self):
        """0 games played → sample_conf=0 → confidence=0."""
        conf = self._run(play_prob=0.97, volatility=5.0, games_played=0)
        self.assertEqual(conf, 0.0)

    def test_games_at_cap_saturates(self):
        """games_played at CONFIDENCE_SAMPLE_SIZE_CAP and above give the same sample_conf=1."""
        conf_at_cap = self._run(
            play_prob=0.97, volatility=5.0, games_played=CONFIDENCE_SAMPLE_SIZE_CAP
        )
        conf_above_cap = self._run(
            play_prob=0.97, volatility=5.0, games_played=CONFIDENCE_SAMPLE_SIZE_CAP + 30
        )
        self.assertAlmostEqual(conf_at_cap, conf_above_cap, places=2)

    # ------------------------------------------------------------------
    # Missing availability → defaults to 0.97
    # ------------------------------------------------------------------

    def test_missing_availability_defaults_to_healthy(self):
        """Player absent from availability table gets play_probability=0.97."""
        predictor = _make_predictor()
        pred_rows = _make_pred_rows([1], [20.0], measure=predictor.measure_prediction)
        vol_rows = _make_pred_rows([1], [5.0], measure=predictor.measure_volatility)
        gp_df = pd.DataFrame({"personId": [1], "games_played": [30]})

        # Pass empty availability
        result_empty_avail = _call_persist(
            predictor, pred_rows, vol_rows, pd.DataFrame(), gp_df
        )

        _reset_singleton(type(predictor))
        predictor2 = _make_predictor()
        avail_df = _make_availability_df([{"person_id": 1, "play_probability": 0.97}])
        result_explicit_healthy = _call_persist(
            predictor2, pred_rows, vol_rows, avail_df, gp_df
        )

        conf_empty = float(
            result_empty_avail[
                result_empty_avail["Measure"] == predictor.measure_prediction
            ]["confidence"].iloc[0]
        )
        conf_healthy = float(
            result_explicit_healthy[
                result_explicit_healthy["Measure"] == predictor.measure_prediction
            ]["confidence"].iloc[0]
        )
        self.assertAlmostEqual(conf_empty, conf_healthy, places=2)

    # ------------------------------------------------------------------
    # Missing volatility → worst-case stability (0)
    # ------------------------------------------------------------------

    def test_missing_volatility_gives_zero_confidence(self):
        """NaN volatility (new player, < 5 games) → stability=0 → confidence=0."""
        predictor = _make_predictor()
        pred_rows = _make_pred_rows([1], [10.0], measure=predictor.measure_prediction)
        vol_rows = _make_pred_rows([1], [np.nan], measure=predictor.measure_volatility)
        avail_df = _make_availability_df([{"person_id": 1, "play_probability": 0.97}])
        gp_df = pd.DataFrame({"personId": [1], "games_played": [10]})

        result = _call_persist(predictor, pred_rows, vol_rows, avail_df, gp_df)
        pred = result[result["Measure"] == predictor.measure_prediction]
        self.assertEqual(float(pred["confidence"].iloc[0]), 0.0)

    # ------------------------------------------------------------------
    # Confidence is bounded [0, 1]
    # ------------------------------------------------------------------

    def test_confidence_bounded_between_0_and_1(self):
        """Confidence must always be in [0.0, 1.0]."""
        for play_prob, vol, games in [
            (0.97, 0.0, 70),  # best case
            (0.50, 12.0, 10),  # mid case
            (0.15, 24.0, 3),  # near-worst case
            (0.97, 30.0, 100),  # volatility above cap
        ]:
            conf = self._run(play_prob, vol, games)
            self.assertGreaterEqual(conf, 0.0, f"conf<0 for {play_prob},{vol},{games}")
            self.assertLessEqual(conf, 1.0, f"conf>1 for {play_prob},{vol},{games}")

    # ------------------------------------------------------------------
    # Negative predictions are clipped to 0
    # ------------------------------------------------------------------

    def test_negative_predictions_clipped(self):
        """persist() must clip negative prediction values to 0."""
        predictor = _make_predictor()
        pred_rows = _make_pred_rows([1], [-3.5], measure=predictor.measure_prediction)
        vol_rows = _make_pred_rows([1], [5.0], measure=predictor.measure_volatility)
        avail_df = _make_availability_df([{"person_id": 1, "play_probability": 0.97}])
        gp_df = pd.DataFrame({"personId": [1], "games_played": [30]})

        result = _call_persist(predictor, pred_rows, vol_rows, avail_df, gp_df)
        pred = result[result["Measure"] == predictor.measure_prediction]
        self.assertEqual(float(pred["Predictions"].iloc[0]), 0.0)


if __name__ == "__main__":
    unittest.main()
