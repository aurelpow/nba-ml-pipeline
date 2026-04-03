"""Test unified training module with both targets."""

import unittest
import os
import tempfile
import pandas as pd
import numpy as np
from unittest.mock import patch
from src.training.train import UnifiedModelTrainer
from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName


def _make_mock_data():
    """Return (box, adv, players) DataFrames sufficient for the full training pipeline."""
    n = 40  # enough rows for a meaningful train/test split
    box = pd.DataFrame(
        {
            "gameId": [f"00223000{i:02d}" for i in range(n)],
            "personId": [f"p{i % 4 + 1}" for i in range(n)],
            "teamId": ["t1"] * (n // 2) + ["t2"] * (n // 2),
            "points": np.random.randint(5, 35, n),
            "reboundsTotal": np.random.randint(1, 12, n),
            "rebounds": np.random.randint(1, 12, n),
            "assists": np.random.randint(0, 10, n),
            "steals": np.random.randint(0, 4, n),
            "blocks": np.random.randint(0, 4, n),
            "turnovers": np.random.randint(0, 6, n),
            "threePointersMade": np.random.randint(0, 6, n),
            "fieldGoalsMade": np.random.randint(3, 15, n),
            "fieldGoalsAttempted": np.random.randint(8, 22, n),
            "threePointersAttempted": np.random.randint(1, 10, n),
            "freeThrowsMade": np.random.randint(0, 6, n),
            "freeThrowsAttempted": np.random.randint(0, 8, n),
            "minutes": ["28:00"] * n,
            "position": ["G"] * n,
            "game_date": pd.date_range(start="2023-01-01", periods=n).astype(str),
            "home_team_id": ["t1"] * n,
            "visitor_team_id": ["t2"] * n,
            "possessions": [100] * n,
        }
    )
    adv = pd.DataFrame(
        {
            "gameId": [f"00223000{i:02d}" for i in range(n)],
            "personId": [f"p{i % 4 + 1}" for i in range(n)],
            "teamId": ["t1"] * (n // 2) + ["t2"] * (n // 2),
            "offensiveRating": [105.0] * n,
            "usagePercentage": [0.25] * n,
            "trueShootingPercentage": [0.55] * n,
            "effectiveFieldGoalPercentage": [0.50] * n,
            "assistToTurnover": [2.0] * n,
        }
    )
    players = pd.DataFrame(
        {
            "person_id": ["p1", "p2", "p3", "p4"],
            "position": ["G", "G", "F", "C"],
        }
    )
    return box, adv, players


class TestUnifiedTraining(unittest.TestCase):
    """Test unified training for both points and fantasy_points targets."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        # persist_model writes metrics CSV to databases/ — redirect cwd to temp dir
        self.databases_dir = os.path.join(self.temp_dir.name, "databases")
        os.makedirs(self.databases_dir, exist_ok=True)
        self._orig_dir = os.getcwd()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self._orig_dir)
        self.temp_dir.cleanup()

    def _run_trainer(self, target: str):
        box, adv, players = _make_mock_data()
        model_path = os.path.join(self.temp_dir.name, f"{target}_model.pkl")
        trainer = UnifiedModelTrainer(
            target=target, model_path=model_path, save_mode="local"
        )

        def side_effect(filename, mode):
            if filename == BoxscoreFileName:
                return box
            elif filename == AdvancedBoxscoreFileName:
                return adv
            elif filename == PlayersFileName:
                return players
            return pd.DataFrame()

        with patch("common.training_helpers.load_data", side_effect=side_effect):
            trainer.run(tune_params=False)

        return trainer, model_path

    def test_points_target_training(self):
        """Test training with points target."""
        trainer, model_path = self._run_trainer("points")
        self.assertTrue(os.path.exists(model_path))
        self.assertTrue(len(trainer.feature_cols) > 0)

    def test_fantasy_target_training(self):
        """Test training with fantasy_points target."""
        trainer, model_path = self._run_trainer("fantasy_points")
        self.assertTrue(os.path.exists(model_path))
        self.assertTrue(len(trainer.feature_cols) > 0)

    def test_invalid_target_raises_error(self):
        """Test that invalid target raises ValueError."""
        with self.assertRaises(ValueError):
            UnifiedModelTrainer(
                target="invalid_target",
                model_path="dummy.pkl",
                save_mode="local",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
