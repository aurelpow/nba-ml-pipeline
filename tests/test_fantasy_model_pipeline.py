import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import os
import tempfile
from src.training.train import UnifiedModelTrainer as ModelTrainer
from common.io_utils import BoxscoreFileName, AdvancedBoxscoreFileName, PlayersFileName


class TestFantasyModelPipeline(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.model_path = os.path.join(self.temp_dir.name, "model.pkl")
        # persist_model writes metrics CSV to databases/ — create it inside temp dir
        self.databases_dir = os.path.join(self.temp_dir.name, "databases")
        os.makedirs(self.databases_dir, exist_ok=True)
        self._orig_dir = os.getcwd()
        os.chdir(self.temp_dir.name)
        self.trainer = ModelTrainer(
            target="fantasy_points", model_path=self.model_path, save_mode="local"
        )

        # Mock data
        self.box = pd.DataFrame(
            {
                "gameId": [f"002230000{i}" for i in range(1, 21)],
                "personId": ["p1"] * 10 + ["p2"] * 10,
                "teamId": ["t1"] * 20,
                "points": np.random.randint(10, 30, 20),
                "reboundsTotal": np.random.randint(2, 10, 20),
                "rebounds": np.random.randint(2, 10, 20),
                "assists": np.random.randint(2, 10, 20),
                "steals": np.random.randint(0, 3, 20),
                "blocks": np.random.randint(0, 3, 20),
                "turnovers": np.random.randint(0, 5, 20),
                "threePointersMade": np.random.randint(0, 5, 20),
                "fieldGoalsMade": np.random.randint(5, 15, 20),
                "fieldGoalsAttempted": np.random.randint(10, 20, 20),
                "threePointersAttempted": np.random.randint(2, 10, 20),
                "freeThrowsMade": np.random.randint(0, 5, 20),
                "freeThrowsAttempted": np.random.randint(0, 5, 20),
                "minutes": ["30:00"] * 20,
                "position": ["G"] * 20,
                "game_date": pd.date_range(start="2023-01-01", periods=20).astype(str),
                "home_team_id": ["t1"] * 20,
                "visitor_team_id": ["t2"] * 20,
                "possessions": [100] * 20,
            }
        )

        self.adv = pd.DataFrame(
            {
                "gameId": [f"002230000{i}" for i in range(1, 21)],
                "personId": ["p1"] * 10 + ["p2"] * 10,
                "teamId": ["t1"] * 20,
                "offensiveRating": [100] * 20,
                "usagePercentage": [0.25] * 20,
                "trueShootingPercentage": [0.55] * 20,
                "effectiveFieldGoalPercentage": [0.50] * 20,
                "assistToTurnover": [2.0] * 20,
            }
        )

        self.players = pd.DataFrame({"person_id": ["p1", "p2"], "position": ["G", "F"]})

    def tearDown(self):
        os.chdir(self._orig_dir)
        self.temp_dir.cleanup()

    @patch("common.training_helpers.load_data")
    def test_run_pipeline(self, mock_load_data):
        # Setup mock return values
        def side_effect(filename, mode):
            if filename == BoxscoreFileName:
                return self.box
            elif filename == AdvancedBoxscoreFileName:
                return self.adv
            elif filename == PlayersFileName:
                return self.players
            return pd.DataFrame()

        mock_load_data.side_effect = side_effect

        # Run pipeline with minimal iterations for speed
        self.trainer.run(tune_params=False, n_iter=1)

        # Check if model file was created
        self.assertTrue(os.path.exists(self.model_path))

        # Check if feature columns were populated
        self.assertTrue(len(self.trainer.feature_cols) > 0)


if __name__ == "__main__":
    unittest.main()
