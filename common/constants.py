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
    'avg_points_opp_position_last_10': 'engineering stats',
    'avg_points_opp_position_last_20': 'engineering stats',
    'avg_points_opp_position_all': 'engineering stats',
}

# Categorical features for points ML models
categorical_cols_points: list[str] = [
    'is_home', 
    'season'
]

# target variable for points ML models
target_variable_points: str = 'points'

# key statistics for fantasy ML models
key_stats_fantasy: dict[str, str] = {
    'points': 'raw stats',
    'fieldGoalsMade': 'raw stats',
    'fieldGoalsAttempted': 'raw stats',
    'possessions': 'raw stats',
    'reboundsTotal': 'raw stats',
    'assists': 'raw stats',
    'threePointersMade': 'raw stats',
    'threePointersAttempted': 'raw stats',
    'usagePercentage': 'raw stats',
    'freeThrowsMade': 'raw stats',
    'freeThrowsAttempted': 'raw stats',
    'trueShootingPercentage': 'raw stats',
    'offensiveRating': 'raw stats',
    'effectiveFieldGoalPercentage': 'raw stats',
    'turnovers': 'raw stats',
    'assistToTurnover': 'raw stats',
    'steals': 'raw stats',
    'blocks': 'raw stats',
    'avg_fantasy_points_opp_position_last_10': 'engineering stats',
    'avg_fantasy_points_opp_position_last_20': 'engineering stats',
    'avg_fantasy_points_opp_position_all': 'engineering stats',
}


# Categorical features for fantasy ML models
categorical_cols_fantasy: list[str] = [
    'is_home', 
    'season',
    'position_group'
]

# target variable for fantasy ML models
target_variable_fantasy: str = 'fantasy_points'
# Rolling windows for fantasy ML models
rolling_windows_fantasy: list[int] = [3, 7, 15, 30]