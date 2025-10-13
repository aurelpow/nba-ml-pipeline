"""
This module contains common utility constants for NBA data processing.
"""

# Nba api timeout
nba_api_timeout: int = 20 
# Number of retries for nba api requests
max_retries: int = 3
# Delay between retries in seconds
retry_delay: int = 5

# key statistics for points ML models
key_stats_points: dict[str, str] = {
    'usagePercentage': 'raw stats',
    'trueShootingPercentage': 'raw stats',
    'effectiveFieldGoalPercentage': 'raw stats',
    'offensiveRating': 'raw stats',
    'freeThrowsMade': 'raw stats',
    'threePointersMade': 'raw stats',
    'fieldGoalsMade': 'raw stats',
    'avg_pts_opp_position_last_10': 'engineering stats',
    'avg_pts_opp_position_last_20': 'engineering stats',
    'avg_pts_opp_position_all': 'engineering stats',
}

# Categorical features for points ML models
categorical_cols_points: list[str] = [
    'is_home', 
    'season'
]

# target variable for points ML models
target_variable_points: str = 'points'

