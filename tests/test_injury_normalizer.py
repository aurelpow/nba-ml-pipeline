"""
Unit tests for src/availability/injury_normalizer.py

Tests cover:
  - normalize_status: exact matches, alias matches (GTD, DND, NWT, DNP),
    case-insensitivity, unknown values, empty/None input
  - play_probability: all canonical levels, unknown input
  - normalize_report: column additions, value preservation, empty DataFrame guard
"""

import unittest
import pandas as pd

from src.availability.injury_normalizer import (
    normalize_status,
    play_probability,
    normalize_report,
)
from common.constants import AVAILABILITY_PLAY_PROBABILITY


class TestNormalizeStatus(unittest.TestCase):
    """normalize_status maps raw strings to canonical levels."""

    # ------------------------------------------------------------------ exact
    def test_out_exact(self):
        self.assertEqual(normalize_status("Out"), "Out")

    def test_out_uppercase(self):
        self.assertEqual(normalize_status("OUT"), "Out")

    def test_doubtful_exact(self):
        self.assertEqual(normalize_status("Doubtful"), "Doubtful")

    def test_questionable_exact(self):
        self.assertEqual(normalize_status("Questionable"), "Questionable")

    def test_probable_exact(self):
        self.assertEqual(normalize_status("Probable"), "Probable")

    def test_available_exact(self):
        self.assertEqual(normalize_status("Available"), "Available")

    # ------------------------------------------------------------------ aliases
    def test_dnp_maps_to_out(self):
        self.assertEqual(normalize_status("DNP"), "Out")

    def test_dnd_maps_to_out(self):
        self.assertEqual(normalize_status("DND"), "Out")

    def test_nwt_maps_to_out(self):
        self.assertEqual(normalize_status("NWT"), "Out")

    def test_gtd_maps_to_questionable(self):
        self.assertEqual(normalize_status("GTD"), "Questionable")

    def test_game_time_decision_maps_to_questionable(self):
        self.assertEqual(normalize_status("GAME TIME DECISION"), "Questionable")

    def test_active_maps_to_available(self):
        self.assertEqual(normalize_status("ACTIVE"), "Available")

    def test_inactive_maps_to_out(self):
        self.assertEqual(normalize_status("INACTIVE"), "Out")

    def test_suspended_maps_to_out(self):
        self.assertEqual(normalize_status("SUSPENDED"), "Out")

    # ------------------------------------------------------------------ case
    def test_mixed_case_out(self):
        self.assertEqual(normalize_status("out"), "Out")

    def test_mixed_case_probable(self):
        self.assertEqual(normalize_status("probable"), "Probable")

    # ------------------------------------------------------------------ edge
    def test_unknown_returns_questionable(self):
        self.assertEqual(normalize_status("MYSTERY_STATUS"), "Questionable")

    def test_empty_string_returns_questionable(self):
        self.assertEqual(normalize_status(""), "Questionable")

    def test_none_returns_questionable(self):
        self.assertEqual(normalize_status(None), "Questionable")

    def test_whitespace_only_returns_questionable(self):
        self.assertEqual(normalize_status("   "), "Questionable")


class TestPlayProbability(unittest.TestCase):
    """play_probability returns calibrated floats for canonical statuses."""

    def test_out_probability(self):
        self.assertEqual(play_probability("Out"), AVAILABILITY_PLAY_PROBABILITY["Out"])

    def test_doubtful_probability(self):
        self.assertEqual(
            play_probability("Doubtful"), AVAILABILITY_PLAY_PROBABILITY["Doubtful"]
        )

    def test_questionable_probability(self):
        self.assertEqual(
            play_probability("Questionable"),
            AVAILABILITY_PLAY_PROBABILITY["Questionable"],
        )

    def test_probable_probability(self):
        self.assertEqual(
            play_probability("Probable"), AVAILABILITY_PLAY_PROBABILITY["Probable"]
        )

    def test_available_probability(self):
        self.assertEqual(
            play_probability("Available"), AVAILABILITY_PLAY_PROBABILITY["Available"]
        )

    def test_probabilities_are_ordered(self):
        """Out < Doubtful < Questionable < Probable < Available."""
        probs = [
            play_probability("Out"),
            play_probability("Doubtful"),
            play_probability("Questionable"),
            play_probability("Probable"),
            play_probability("Available"),
        ]
        self.assertEqual(probs, sorted(probs))

    def test_all_probabilities_in_unit_interval(self):
        for status in ("Out", "Doubtful", "Questionable", "Probable", "Available"):
            p = play_probability(status)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_unknown_status_returns_half(self):
        self.assertEqual(play_probability("UNKNOWN"), 0.50)


class TestNormalizeReport(unittest.TestCase):
    """normalize_report enriches a raw injury DataFrame."""

    def _make_raw_df(self):
        return pd.DataFrame(
            {
                "report_date": ["03/31/2026", "03/31/2026", "03/31/2026"],
                "matchup": ["MIL@BOS", "MIL@BOS", "LAL@GSW"],
                "team": ["MIL", "BOS", "LAL"],
                "player_name": [
                    "Antetokounmpo,Giannis",
                    "Brown,Jaylen",
                    "James,LeBron",
                ],
                "status": ["OUT", "GTD", "PROBABLE"],
                "reason": ["Knee", "Hamstring", ""],
            }
        )

    # ------------------------------------------------------------------ columns
    def test_raw_status_column_preserved(self):
        df = normalize_report(self._make_raw_df())
        self.assertIn("raw_status", df.columns)

    def test_status_column_canonical(self):
        df = normalize_report(self._make_raw_df())
        self.assertIn("status", df.columns)
        valid = {"Out", "Doubtful", "Questionable", "Probable", "Available"}
        for val in df["status"]:
            self.assertIn(val, valid, f"Unexpected canonical status: {val!r}")

    def test_play_probability_column_added(self):
        df = normalize_report(self._make_raw_df())
        self.assertIn("play_probability", df.columns)

    # ------------------------------------------------------------------ values
    def test_out_row_has_low_probability(self):
        df = normalize_report(self._make_raw_df())
        out_rows = df[df["status"] == "Out"]
        self.assertFalse(out_rows.empty)
        self.assertTrue((out_rows["play_probability"] < 0.20).all())

    def test_gtd_maps_to_questionable_in_dataframe(self):
        df = normalize_report(self._make_raw_df())
        # Second row was "GTD"
        self.assertEqual(df.loc[1, "status"], "Questionable")
        self.assertEqual(df.loc[1, "raw_status"], "GTD")

    def test_probable_row_has_high_probability(self):
        df = normalize_report(self._make_raw_df())
        prob_rows = df[df["status"] == "Probable"]
        self.assertFalse(prob_rows.empty)
        self.assertTrue((prob_rows["play_probability"] >= 0.80).all())

    def test_row_count_unchanged(self):
        raw = self._make_raw_df()
        df = normalize_report(raw)
        self.assertEqual(len(df), len(raw))

    # ------------------------------------------------------------------ edge
    def test_empty_dataframe_returns_empty(self):
        empty = pd.DataFrame(
            columns=[
                "report_date",
                "matchup",
                "team",
                "player_name",
                "status",
                "reason",
            ]
        )
        result = normalize_report(empty)
        self.assertTrue(result.empty)

    def test_original_dataframe_not_mutated(self):
        raw = self._make_raw_df()
        original_statuses = raw["status"].tolist()
        normalize_report(raw)
        self.assertEqual(raw["status"].tolist(), original_statuses)


if __name__ == "__main__":
    unittest.main(verbosity=2)
