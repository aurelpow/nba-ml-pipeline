import unittest
from unittest.mock import patch

import pandas as pd

from common.singleton_meta import SingletonMeta
from src.data_collectors.get_historic_ttfl_max import HistoricTtflMaxCollector

MODULE = "src.data_collectors.get_historic_ttfl_max"


def _log_row(player_id, name, game_id, date, pts, tov=0):
    """A LeagueGameLog row; every other counting stat is 0 so TTFL = pts - tov."""
    row = {
        "PLAYER_ID": player_id,
        "PLAYER_NAME": name,
        "GAME_ID": game_id,
        "GAME_DATE": date,
    }
    row.update({c: 0 for c in ["REB", "AST", "STL", "BLK", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA"]})
    row.update({"PTS": pts, "TOV": tov})
    return row


class TestHistoricTtflMax(unittest.TestCase):
    def setUp(self):
        SingletonMeta._instances.pop(HistoricTtflMaxCollector, None)
        self.collector = HistoricTtflMaxCollector(current_season="2025-26", save_mode="local")

    def test_format_season(self):
        self.assertEqual(HistoricTtflMaxCollector.format_season(1999), "1999-00")
        self.assertEqual(HistoricTtflMaxCollector.format_season(2024), "2024-25")

    def test_best_games_keeps_best_game_of_listed_players_only(self):
        log_df = pd.DataFrame(
            [
                _log_row(1, "A", "0022400001", "2025-01-01", pts=30, tov=5),  # 25
                _log_row(1, "A", "0022400002", "2025-01-02", pts=40, tov=2),  # 38
                _log_row(2, "B", "0022400003", "2025-01-03", pts=99),  # not in players table
            ]
        )
        out = self.collector.best_games(log_df, {1}, "2024-25", "Regular Season")
        self.assertEqual(len(out), 1)
        row = out.iloc[0]
        self.assertEqual(row["personId"], 1)
        self.assertEqual(row["max_ttfl"], 38)
        self.assertEqual(row["max_ttfl_game_id"], "0022400002")
        self.assertEqual(row["season_type"], "Regular Season")
        self.assertEqual(row["max_ttfl_season"], "2024-25")

    def test_best_games_treats_untracked_stats_as_zero(self):
        log_df = pd.DataFrame([_log_row(1, "A", "0021000001", "1975-01-01", pts=10)])
        log_df["TOV"] = None  # not tracked in old seasons
        out = self.collector.best_games(log_df, {1}, "1974-75", "Regular Season")
        self.assertEqual(out.iloc[0]["max_ttfl"], 10)

    def test_best_games_empty_log(self):
        empty = pd.DataFrame(columns=list(_log_row(1, "A", "g", "d", 0).keys()))
        out = self.collector.best_games(empty, {1}, "2000-01", "Playoffs")
        self.assertTrue(out.empty)

    def test_compute_picks_max_across_seasons_per_season_type(self):
        players = pd.DataFrame({"person_id": [1], "from_year": [2023]})
        logs = {
            ("2023-24", "Regular Season"): [_log_row(1, "A", "g1", "2024-01-01", pts=40)],
            ("2023-24", "Playoffs"): [_log_row(1, "A", "g2", "2024-05-01", pts=20)],
            ("2024-25", "Regular Season"): [_log_row(1, "A", "g3", "2025-01-01", pts=35)],
            ("2024-25", "Playoffs"): [_log_row(1, "A", "g4", "2025-05-01", pts=50)],
        }
        with patch.object(self.collector, "get_players", return_value=players), patch.object(
            self.collector,
            "fetch_season_log",
            side_effect=lambda season, st: pd.DataFrame(logs[(season, st)]),
        ), patch(f"{MODULE}.time.sleep"):
            out = self.collector.compute()

        by_type = out.set_index("season_type")
        self.assertEqual(len(out), 2)
        self.assertEqual(by_type.loc["Regular Season", "max_ttfl"], 40)
        self.assertEqual(by_type.loc["Regular Season", "max_ttfl_season"], "2023-24")
        self.assertEqual(by_type.loc["Playoffs", "max_ttfl"], 50)
        self.assertEqual(by_type.loc["Playoffs", "max_ttfl_season"], "2024-25")

    def test_compute_excludes_current_season(self):
        players = pd.DataFrame({"person_id": [1], "from_year": [2024]})
        requested = []

        def fake_fetch(season, st):
            requested.append(season)
            return pd.DataFrame([_log_row(1, "A", "g", "2025-01-01", pts=10)])

        with patch.object(self.collector, "get_players", return_value=players), patch.object(
            self.collector, "fetch_season_log", side_effect=fake_fetch
        ), patch(f"{MODULE}.time.sleep"):
            self.collector.compute()
        self.assertEqual(set(requested), {"2024-25"})

    def test_run_raises_and_saves_nothing_when_a_season_fails(self):
        players = pd.DataFrame({"person_id": [1], "from_year": [2024]})
        with patch.object(self.collector, "get_players", return_value=players), patch.object(
            self.collector, "fetch_season_log", side_effect=Exception("timeout")
        ), patch(f"{MODULE}.time.sleep"), patch(f"{MODULE}.save_database") as mock_save:
            with self.assertRaises(RuntimeError):
                self.collector.run()
        mock_save.assert_not_called()

    def test_run_saves_to_historic_table(self):
        out = pd.DataFrame(
            {
                "personId": [1],
                "player_name": ["A"],
                "season_type": ["Playoffs"],
                "max_ttfl": [50],
                "max_ttfl_game_id": ["g"],
                "max_ttfl_game_date": ["2025-05-01"],
                "max_ttfl_season": ["2024-25"],
            }
        )
        with patch.object(self.collector, "compute", return_value=out), patch(
            f"{MODULE}.save_database"
        ) as mock_save:
            self.collector.run()
        args, kwargs = mock_save.call_args
        self.assertEqual(args[1], "nba_historic_ttfl_max")
        self.assertNotIn("write_disposition", kwargs)  # default WRITE_TRUNCATE -> re-run is idempotent


if __name__ == "__main__":
    unittest.main()
