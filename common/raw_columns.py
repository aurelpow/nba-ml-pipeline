"""
 Centralized column-name constants used across raw NBA API tables and pipeline outputs.
 These constants help avoid hardcoding column strings (e.g., camelCase vs snake_case) throughout the codebase.
 """

# ID columns
game_id_col: str = "gameId"
game_id_col_alt: str = "game_id"
id_col: str = "id"
team_id_col: str = "team_id"
team_id_col_alt: str = "teamId"
person_id_col: str = "person_id"
person_id_col_alt: str = "personId"
home_team_id_col: str = "home_team_id"
visitor_team_id_col: str = "visitor_team_id"
opponent_id_col_alt: str = "opponentId"

# Date and time columns
game_date_col: str = "game_date"          # snake_case — boxscore tables
game_date_col_alt: str = "gameDate"       # camelCase  — schedule + predictions
report_date_col: str = "report_date"

# Names and identifiers
player_name_col: str = "player_name"
player_last_name_col: str = "player_last_name"
player_first_name_col: str = "player_first_name"
player_slug_col: str = "player_slug"
full_name_col: str = "full_name"
team_col: str = "team"
team_abbreviation_col: str = "team_abbreviation"
abbreviation_col: str = "abbreviation"
nickname_col: str = "nickname"
matchup_col: str = "matchup"

# Boxscore statistics columns
minutes_col: str = "minutes"
field_goals_made_col: str = "fieldGoalsMade"
field_goals_attempted_col: str = "fieldGoalsAttempted"
three_pointers_made_col: str = "threePointersMade"
three_pointers_attempted_col: str = "threePointersAttempted"
free_throws_made_col: str = "freeThrowsMade"
free_throws_attempted_col: str = "freeThrowsAttempted"
rebounds_total_col: str = "reboundsTotal"
assists_col: str = "assists"
steals_col: str = "steals"
turnovers_col: str = "turnovers"
blocks_col: str = "blocks"
points_col: str = "points"
is_regular_season_col: str = "is_regular_season"
is_playoffs_col: str = "is_playoffs"

# Other Metadata columns
city_col: str = "city"
state_col: str = "state"
year_founded_col: str = "year_founded"
jersey_number_col: str = "jersey_number"
position_col: str = "position"
height_col: str = "height"
weight_col: str = "weight"
season_col: str = "season"
college_col : str = "college"
country_col: str = "country"
draft_year_col: str = "draft_year"
draft_round_col: str = "draft_round"
draft_number_col: str = "draft_number"
roster_status_col: str = "roster_status"
from_year_col: str = "from_year"
to_year_col: str = "to_year"

# Injury and Availability columns
raw_status_col: str = "raw_status" # availability status in raw data (e.g. "Active", "Inactive", "Retired", "Undisclosed")
status_col: str = "status" # availability status after mapping to "available", "unavailable", "unknown"
reason_col: str = "reason" # reason for unavailability, if known (e.g. "Injury", "Rest", "Personal", "Other")
play_probability_col: str = "play_probability" # probability of playing, derived from availability status and other factors
is_available_col: str = "is_available" # binary indicator of availability, derived from play_probability_col

# Engineering columns
aud_modification_date_col: str = "aud_modification_date"

# Predictions columns
predictions_col: str = "Predictions"
measure_col: str = "Measure"
confidence_col: str = "confidence"

# Computed target columns
fantasy_points_col: str = "fantasy_points"
