import unittest
import pandas as pd
import numpy as np
from common.feature_engineering import (
    merge_data,
    preprocess_data,
    create_historical_features,
    normalize_features,
    compute_rolling_stats,
    encode_categorical_features,
    get_feature_cols,
)


class TestFeatureEngineering(unittest.TestCase):
    def setUp(self):
        # Create sample dataframes
        self.box = pd.DataFrame(
            {
                "gameId": ["0022300001", "0022300002", "0022300003"],
                "personId": ["p1", "p1", "p2"],
                "teamId": ["t1", "t1", "t2"],
                "points": [10, 20, 15],
                "minutes": ["20:00", "30:00", "25:00"],
                "game_date": ["2023-01-01", "2023-01-02", "2023-01-01"],
                "home_team_id": ["t1", "t2", "t2"],
                "visitor_team_id": ["t2", "t1", "t1"],
                "possessions": [100, 100, 100],
                "position": ["G", "G", "F"],
            }
        )

        self.adv = pd.DataFrame(
            {
                "gameId": ["0022300001", "0022300002", "0022300003"],
                "personId": ["p1", "p1", "p2"],
                "teamId": ["t1", "t1", "t2"],
                "offensive_rating": [100, 110, 105],
            }
        )

        self.players = pd.DataFrame({"person_id": ["p1", "p2"], "position": ["G", "F"]})

        self.key_stats = {"points": "Points (raw)", "assists": "Assists (engineering)"}

    def test_merge_data(self):
        df = merge_data(self.box, self.adv, self.players)
        self.assertIn("offensive_rating", df.columns)
        self.assertIn("position_player", df.columns)
        self.assertEqual(len(df), 3)

    def test_preprocess_data(self):
        df = merge_data(self.box, self.adv, self.players)
        df = preprocess_data(df)

        self.assertTrue(pd.api.types.is_float_dtype(df["minutes"]))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["game_date"]))
        self.assertIn("position_group", df.columns)
        self.assertIn("season", df.columns)
        self.assertIn("is_home", df.columns)
        self.assertIn("opponent", df.columns)

    def test_create_historical_features(self):
        df = merge_data(self.box, self.adv, self.players)
        df = preprocess_data(df)
        # Ensure we have enough data for historical features or handle NaNs
        df = create_historical_features(df)

        self.assertIn("avg_points_opp_position_last_10", df.columns)
        self.assertIn("avg_points_opp_position_last_20", df.columns)
        self.assertIn("avg_points_opp_position_all", df.columns)

    def test_normalize_features(self):
        df = merge_data(self.box, self.adv, self.players)
        df = preprocess_data(df)
        df = normalize_features(df, self.key_stats)

        self.assertIn("points_per36", df.columns)
        self.assertIn("points_per_poss", df.columns)

        # Check calculation: 10 points in 20 mins -> 18 per 36
        row1 = df.iloc[0]
        self.assertAlmostEqual(row1["points_per36"], 10 / 20 * 36)

    def test_compute_rolling_stats(self):
        df = merge_data(self.box, self.adv, self.players)
        df = preprocess_data(df)
        df = normalize_features(df, self.key_stats)
        df = compute_rolling_stats(df, self.key_stats, windows=[2])

        self.assertIn("points_per36_rolling_2", df.columns)
        self.assertIn("points_per_poss_rolling_2", df.columns)

    def test_encode_categorical_features(self):
        df = pd.DataFrame({"pos": ["A", "B", "A"]})
        # encode_categorical_features now returns (df, feature_names, encoder)
        df, encoded_cols, encoder = encode_categorical_features(df, ["pos"])

        self.assertIn("pos_A", df.columns)
        self.assertIn("pos_B", df.columns)
        self.assertIn("pos_A", encoded_cols)
        # encoder should be reusable at inference time
        self.assertIsNotNone(encoder)

    def test_get_feature_cols(self):
        cols = get_feature_cols(self.key_stats, rolling_periods=[5])
        self.assertIn("points_per36_rolling_5", cols)
        self.assertIn("points_per_poss_rolling_5", cols)
        self.assertIn("assists_per36", cols)
        self.assertIn("assists_per_poss", cols)


if __name__ == "__main__":
    unittest.main()
