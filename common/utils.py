"""
This module contains the common variables used in the NBA Stats Data Pipeline.
"""
# Define the sheet names
boxscore_sheet_name = "boxscores" 
nba_teams_sheet_name = "team_data"
nba_players_sheet_name = "player_data"
import os 
import json
# Path to the credentials file
CREDENTIALS_FILE_PATH = "common/credentials.json"

# Ensure the credentials file exists
if not os.path.exists(CREDENTIALS_FILE_PATH):
    raise FileNotFoundError(f"The credentials file was not found at {CREDENTIALS_FILE_PATH}. Please ensure it exists.")

CREDENTIALS_FILE = CREDENTIALS_FILE_PATH