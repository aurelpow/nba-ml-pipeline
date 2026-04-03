"""
This module contains common utility constants for NBA data processing.
"""

# Nba api timeout
nba_api_timeout: int = 60  # increased from 20 – proxy adds latency
# Number of retries for nba api requests
max_retries: int = 3
# Delay between retries in seconds
retry_delay: int = 10

# key statistics for points ML models
key_stats_points: dict[str, str] = {
    "usagePercentage": "raw stats",
    "trueShootingPercentage": "raw stats",
    "effectiveFieldGoalPercentage": "raw stats",
    "offensiveRating": "raw stats",
    "freeThrowsMade": "raw stats",
    "threePointersMade": "raw stats",
    "fieldGoalsMade": "raw stats",
    "avg_points_opp_position_last_10": "engineering stats",
    "avg_points_opp_position_last_20": "engineering stats",
    "avg_points_opp_position_all": "engineering stats",
}

# Categorical features for points ML models
categorical_cols_points: list[str] = ["is_home", "season"]

# target variable for points ML models
target_variable_points: str = "points"

# key statistics for fantasy ML models
key_stats_fantasy: dict[str, str] = {
    "points": "raw stats",
    "fieldGoalsMade": "raw stats",
    "fieldGoalsAttempted": "raw stats",
    "possessions": "raw stats",
    "reboundsTotal": "raw stats",
    "assists": "raw stats",
    "threePointersMade": "raw stats",
    "threePointersAttempted": "raw stats",
    "usagePercentage": "raw stats",
    "freeThrowsMade": "raw stats",
    "freeThrowsAttempted": "raw stats",
    "trueShootingPercentage": "raw stats",
    "offensiveRating": "raw stats",
    "effectiveFieldGoalPercentage": "raw stats",
    "turnovers": "raw stats",
    "assistToTurnover": "raw stats",
    "steals": "raw stats",
    "blocks": "raw stats",
    "avg_fantasy_points_opp_position_last_10": "engineering stats",
    "avg_fantasy_points_opp_position_last_20": "engineering stats",
    "avg_fantasy_points_opp_position_all": "engineering stats",
}


# Categorical features for fantasy ML models
categorical_cols_fantasy: list[str] = ["is_home", "season", "position_group"]

# target variable for fantasy ML models
target_variable_fantasy: str = "fantasy_points"
# Rolling windows for fantasy ML models
rolling_windows_fantasy: list[int] = [3, 7, 15, 30]
rolling_windows_points: list[int] = [5, 10, 20]

# Measure types for predictions output (narrow format)
MEASURE_PREDICTED_POINTS: int = 1
MEASURE_PREDICTED_FANTASY_POINTS: int = 2
MEASURE_POINTS_VOLATILITY: int = 3
MEASURE_FANTASY_VOLATILITY: int = 4

# ---------------------------------------------------------------------------
# Availability subsystem constants
# ---------------------------------------------------------------------------

# Maps raw PDF status strings (upper-cased) to one of the five canonical levels.
# Keys are matched first by exact equality, then as regex sub-patterns, in the
# order defined here.  The first match wins.
AVAILABILITY_STATUS_MAP: dict[str, str] = {
    # --- Out variants ---
    "OUT": "Out",
    "DNP": "Out",
    "DND": "Out",
    "NWT": "Out",  # Not With Team
    "INACTIVE": "Out",
    "SUSPENDED": "Out",
    r"OUT\b": "Out",  # fallback regex
    r"DO NOT PLAY": "Out",
    # --- Doubtful variants ---
    "DOUBTFUL": "Doubtful",
    r"DOUBTFUL\b": "Doubtful",
    # --- Questionable / Game-Time Decision variants ---
    "QUESTIONABLE": "Questionable",
    "GTD": "Questionable",  # Game-Time Decision
    "GAME TIME DECISION": "Questionable",
    r"QUESTIONABLE\b": "Questionable",
    # --- Probable variants ---
    "PROBABLE": "Probable",
    r"PROBABLE\b": "Probable",
    # --- Available / no restriction ---
    "AVAILABLE": "Available",
    "ACTIVE": "Available",
    r"AVAILABLE\b": "Available",
}

# Prior play-probability assigned to each canonical status.
# These are empirical calibrations; adjust as you collect outcome data.
AVAILABILITY_PLAY_PROBABILITY: dict[str, float] = {
    "Out": 0.02,
    "Doubtful": 0.15,
    "Questionable": 0.50,
    "Probable": 0.85,
    "Available": 0.97,
}

# Minimum play_probability for is_available=True in the downstream table.
AVAILABILITY_DEFAULT_THRESHOLD: float = 0.50

# Players with play_probability strictly below this threshold are excluded from
# predictions entirely. Set to just above "Out" (0.02) so that only Out players
# are excluded; Doubtful (0.15) and above receive a prediction row.
PREDICTION_EXCLUDE_THRESHOLD: float = 0.10

# Confidence score parameters.
# stability   = 1 - min(volatility / CONFIDENCE_MAX_VOLATILITY, 1.0)
# sample_conf = min(games_played / CONFIDENCE_SAMPLE_SIZE_CAP, 1.0)
# confidence  = play_probability * stability * sample_conf
CONFIDENCE_MAX_VOLATILITY: float = 25.0  # std dev cap; beyond this → stability = 0
CONFIDENCE_SAMPLE_SIZE_CAP: int = 20  # games to reach full sample confidence

# Target configuration - centralized settings for each target variable
# To add a new target, simply add a new entry to this dictionary
TARGET_CONFIGS: dict[str, dict] = {
    "points": {
        "key_stats": key_stats_points,
        "categorical_cols": categorical_cols_points,
        "target_variable": target_variable_points,
        "rolling_windows": rolling_windows_points,
        "measure_prediction": MEASURE_PREDICTED_POINTS,
        "measure_volatility": MEASURE_POINTS_VOLATILITY,
        "target_computer_fn": None,  # No computation needed, already in data
    },
    "fantasy_points": {
        "key_stats": key_stats_fantasy,
        "categorical_cols": categorical_cols_fantasy,
        "target_variable": target_variable_fantasy,
        "rolling_windows": rolling_windows_fantasy,
        "measure_prediction": MEASURE_PREDICTED_FANTASY_POINTS,
        "measure_volatility": MEASURE_FANTASY_VOLATILITY,
        "target_computer_fn": "compute_fantasy_points",  # String reference to avoid circular import
    },
}
