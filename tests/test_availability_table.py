"""
Unit tests for src/availability/availability_table.py

Tests cover:
  - _build: schema, available/unavailable row counts, threshold behaviour
  - _build: full roster appears in output even when not in injury report
  - _build: injured players override the Available baseline
  - _build: empty injury report → all players Available
  - _build: empty players DataFrame → returns empty
  - run: calls save_database and returns DataFrame (mocked I/O)
"""

import datetime
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd

from common.singleton_meta import SingletonMeta
from common.constants import (
    AVAILABILITY_DEFAULT_THRESHOLD,
    AVAILABILITY_PLAY_PROBABILITY,
)


def _reset_singleton(cls):
    if cls in SingletonMeta._instances:
        del SingletonMeta._instances[cls]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_players_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "person_id": [1, 2, 3, 4],
            "player_slug": [
                "giannis-antetokounmpo",
                "jaylen-brown",
                "lebron-james",
                "stephen-curry",
            ],
            "team_id": [1610612749, 1610612738, 1610612747, 1610612744],
            "team_abbreviation": ["MIL", "BOS", "LAL", "GSW"],
            "player_last_name": ["Antetokounmpo", "Brown", "James", "Curry"],
            "player_first_name": ["Giannis", "Jaylen", "LeBron", "Stephen"],
        }
    )


def _make_injury_df(statuses: dict | None = None) -> pd.DataFrame:
    """
    Build a raw injury report with a subset of players.
    statuses: {player_name_pdf: status_string}
    Default: Giannis=Out, Jaylen=GTD
    """
    if statuses is None:
        statuses = {
            "Antetokounmpo,Giannis": "Out",
            "Brown,Jaylen": "GTD",
        }
    n = len(statuses)
    teams_pool = ["MIL", "BOS", "LAL", "GSW", "PHX", "MIA"]
    return pd.DataFrame(
        {
            "report_date": ["03/31/2026"] * n,
            "matchup": ["MIL@BOS"] * n,
            "team": [teams_pool[i % len(teams_pool)] for i in range(n)],
            "player_name": list(statuses.keys()),
            "status": list(statuses.values()),
            "reason": ["Injury"] * n,
        }
    )


# ---------------------------------------------------------------------------
# Tests for _build (pure logic, no I/O)
# ---------------------------------------------------------------------------


class TestBuildSchema(unittest.TestCase):
    """Output schema is always correct."""

    def setUp(self):
        from src.availability.availability_table import AvailabilityTableBuilder

        _reset_singleton(AvailabilityTableBuilder)
        self.AvailabilityTableBuilder = AvailabilityTableBuilder

    def tearDown(self):
        _reset_singleton(self.AvailabilityTableBuilder)

    def _builder(self):
        return self.AvailabilityTableBuilder(
            save_mode="local", report_date="2026-03-31"
        )

    def test_required_columns_present(self):
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        for col in (
            "game_date",
            "team",
            "team_id",
            "person_id",
            "player_slug",
            "status",
            "play_probability",
            "is_available",
        ):
            self.assertIn(col, df.columns, f"Missing column: {col}")

    def test_is_available_is_boolean(self):
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        self.assertTrue(
            df["is_available"].dtype == bool or df["is_available"].dtype == object,
            "is_available should be bool-like",
        )

    def test_play_probability_in_unit_interval(self):
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        self.assertTrue((df["play_probability"] >= 0).all())
        self.assertTrue((df["play_probability"] <= 1).all())

    def test_game_date_is_correct(self):
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        expected_date = pd.Timestamp("2026-03-31")
        self.assertTrue((df["game_date"] == expected_date).all())


class TestBuildCounts(unittest.TestCase):
    """Row counts and available/unavailable splits."""

    def setUp(self):
        from src.availability.availability_table import AvailabilityTableBuilder

        _reset_singleton(AvailabilityTableBuilder)
        self.AvailabilityTableBuilder = AvailabilityTableBuilder

    def tearDown(self):
        _reset_singleton(self.AvailabilityTableBuilder)

    def _builder(self, threshold=None):
        kwargs = {"save_mode": "local", "report_date": "2026-03-31"}
        if threshold is not None:
            kwargs["availability_threshold"] = threshold
        return self.AvailabilityTableBuilder(**kwargs)

    def test_all_players_appear_in_output(self):
        """Every player in the roster should have a row in the output."""
        players = _make_players_df()
        b = self._builder()
        df = b._build(_make_injury_df(), players)
        self.assertEqual(len(df), len(players))

    def test_injured_players_override_baseline(self):
        """Players in the injury report get their injury status, not 'Available'."""
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        giannis = df[df["person_id"] == 1]
        self.assertFalse(giannis.empty)
        self.assertEqual(giannis.iloc[0]["status"], "Out")

    def test_unlisted_players_are_available(self):
        """Players absent from the injury report default to Available."""
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        # LeBron (id=3) and Curry (id=4) are not in the injury report
        for pid in (3, 4):
            row = df[df["person_id"] == pid]
            self.assertFalse(row.empty)
            self.assertEqual(row.iloc[0]["status"], "Available")

    def test_out_player_is_unavailable(self):
        """A player with status Out should have is_available=False."""
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        giannis = df[df["person_id"] == 1]
        self.assertFalse(bool(giannis.iloc[0]["is_available"]))

    def test_available_player_is_available(self):
        """A player not on the report should have is_available=True."""
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        lebron = df[df["person_id"] == 3]
        self.assertTrue(bool(lebron.iloc[0]["is_available"]))

    def test_threshold_changes_questionable_classification(self):
        """With threshold=0.60, a Questionable player (p=0.50) is unavailable."""
        injury = _make_injury_df({"Antetokounmpo,Giannis": "Questionable"})
        # Threshold below Questionable probability → available
        b_low = self._builder(threshold=0.40)
        df_low = b_low._build(injury, _make_players_df())
        giannis_low = df_low[df_low["person_id"] == 1]
        self.assertTrue(bool(giannis_low.iloc[0]["is_available"]))

        _reset_singleton(self.AvailabilityTableBuilder)
        # Threshold above Questionable probability → unavailable
        b_high = self._builder(threshold=0.60)
        df_high = b_high._build(injury, _make_players_df())
        giannis_high = df_high[df_high["person_id"] == 1]
        self.assertFalse(bool(giannis_high.iloc[0]["is_available"]))


class TestBuildEdgeCases(unittest.TestCase):
    """Edge cases: empty inputs, all injured, single player."""

    def setUp(self):
        from src.availability.availability_table import AvailabilityTableBuilder

        _reset_singleton(AvailabilityTableBuilder)
        self.AvailabilityTableBuilder = AvailabilityTableBuilder

    def tearDown(self):
        _reset_singleton(self.AvailabilityTableBuilder)

    def _builder(self):
        return self.AvailabilityTableBuilder(
            save_mode="local", report_date="2026-03-31"
        )

    def test_empty_injury_report_all_available(self):
        """When the injury report is empty everyone defaults to Available."""
        b = self._builder()
        players = _make_players_df()
        empty_injury = pd.DataFrame(
            columns=[
                "report_date",
                "matchup",
                "team",
                "player_name",
                "status",
                "reason",
            ]
        )
        df = b._build(empty_injury, players)
        self.assertEqual(len(df), len(players))
        self.assertTrue((df["status"] == "Available").all())
        self.assertTrue(df["is_available"].all())

    def test_empty_players_returns_empty(self):
        """An empty players roster returns an empty DataFrame."""
        b = self._builder()
        empty_players = pd.DataFrame(columns=_make_players_df().columns)
        df = b._build(_make_injury_df(), empty_players)
        self.assertTrue(df.empty)

    def test_all_players_injured_out(self):
        """When every player is Out, is_available is False for all."""
        players = _make_players_df()
        statuses = {
            "Antetokounmpo,Giannis": "Out",
            "Brown,Jaylen": "Out",
            "James,LeBron": "Out",
            "Curry,Stephen": "Out",
        }
        injury = _make_injury_df(statuses)
        b = self._builder()
        df = b._build(injury, players)
        self.assertFalse(df["is_available"].any())

    def test_play_probability_for_out_player(self):
        """Out players receive the correct calibrated probability."""
        injury = _make_injury_df({"Antetokounmpo,Giannis": "Out"})
        b = self._builder()
        df = b._build(injury, _make_players_df())
        giannis = df[df["person_id"] == 1]
        self.assertAlmostEqual(
            giannis.iloc[0]["play_probability"],
            AVAILABILITY_PLAY_PROBABILITY["Out"],
        )

    def test_play_probability_for_unlisted_player(self):
        """Unlisted players receive the Available probability."""
        b = self._builder()
        df = b._build(_make_injury_df(), _make_players_df())
        lebron = df[df["person_id"] == 3]
        self.assertAlmostEqual(
            lebron.iloc[0]["play_probability"],
            AVAILABILITY_PLAY_PROBABILITY["Available"],
        )


# ---------------------------------------------------------------------------
# Tests for run() (mocked I/O)
# ---------------------------------------------------------------------------


class TestAvailabilityTableBuilderRun(unittest.TestCase):
    """run() wires I/O correctly."""

    def setUp(self):
        from src.availability.availability_table import AvailabilityTableBuilder

        _reset_singleton(AvailabilityTableBuilder)
        self.AvailabilityTableBuilder = AvailabilityTableBuilder

    def tearDown(self):
        _reset_singleton(self.AvailabilityTableBuilder)

    def _builder(self):
        return self.AvailabilityTableBuilder(
            save_mode="local", report_date="2026-03-31"
        )

    @patch("src.availability.availability_table.save_database")
    @patch("src.availability.availability_table.load_data")
    def test_run_calls_save_database(self, mock_load, mock_save):
        """run() calls save_database with the built DataFrame."""
        from common.io_utils import InjuryReportFileName, PlayersFileName

        def _side_effect(filename, mode):
            if filename == InjuryReportFileName:
                return _make_injury_df()
            if filename == PlayersFileName:
                return _make_players_df()
            return pd.DataFrame()

        mock_load.side_effect = _side_effect

        b = self._builder()
        result = b.run()

        mock_save.assert_called_once()
        saved_df = mock_save.call_args[0][0]
        self.assertIsInstance(saved_df, pd.DataFrame)
        self.assertFalse(saved_df.empty)

    @patch("src.availability.availability_table.save_database")
    @patch("src.availability.availability_table.load_data")
    def test_run_returns_dataframe(self, mock_load, mock_save):
        """run() returns the availability DataFrame."""
        from common.io_utils import InjuryReportFileName, PlayersFileName

        def _side_effect(filename, mode):
            if filename == InjuryReportFileName:
                return _make_injury_df()
            if filename == PlayersFileName:
                return _make_players_df()
            return pd.DataFrame()

        mock_load.side_effect = _side_effect

        b = self._builder()
        result = b.run()

        self.assertIsInstance(result, pd.DataFrame)
        self.assertFalse(result.empty)

    @patch("src.availability.availability_table.save_database")
    @patch("src.availability.availability_table.load_data")
    def test_run_does_not_save_when_players_empty(self, mock_load, mock_save):
        """run() skips save when the players table is empty."""
        from common.io_utils import InjuryReportFileName, PlayersFileName

        def _side_effect(filename, mode):
            if filename == InjuryReportFileName:
                return _make_injury_df()
            if filename == PlayersFileName:
                return pd.DataFrame()
            return pd.DataFrame()

        mock_load.side_effect = _side_effect

        b = self._builder()
        result = b.run()

        mock_save.assert_not_called()
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main(verbosity=2)
