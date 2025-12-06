import unittest
import pandas as pd
import numpy as np
from src.targets.fantasy_points import compute_fantasy_points

class TestFantasyPoints(unittest.TestCase):
    
    def test_compute_fantasy_points_ttfl(self):
        # Example Player Stats
        # PTS: 20
        # REB: 5
        # AST: 5
        # STL: 1
        # BLK: 1
        # TOV: 2
        # FGM: 8, FGA: 15 (Missed: 7)
        # 3PM: 2, 3PA: 5 (Missed: 3)
        # FTM: 2, FTA: 3 (Missed: 1)
        
        data = {
            'points': [20],
            'reboundsTotal': [5],
            'assists': [5],
            'steals': [1],
            'blocks': [1],
            'turnovers': [2],
            'fieldGoalsMade': [8],
            'fieldGoalsAttempted': [15],
            'threePointersMade': [2],
            'threePointersAttempted': [5],
            'freeThrowsMade': [2],
            'freeThrowsAttempted': [3]
        }
        df = pd.DataFrame(data)
        df = compute_fantasy_points(df)
        
        # Calculation:
        # Positive: 20 + 5 + 5 + 1 + 1 + 8 + 2 + 2 = 44
        # Negative: 2 (TOV) + 7 (FG Miss) + 3 (3P Miss) + 1 (FT Miss) = 13
        # Total: 44 - 13 = 31
        
        self.assertEqual(df['fantasy_points'].iloc[0], 31)

    def test_missing_columns(self):
        data = {'points': [10]}
        df = pd.DataFrame(data)
        with self.assertRaises(ValueError):
            compute_fantasy_points(df)

if __name__ == '__main__':
    unittest.main()
