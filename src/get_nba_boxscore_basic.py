import sys
import os
# Add the project root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.utils import boxscore_sheet_name, CREDENTIALS_FILE
from common.google_sheets_utils import connect_to_sheet
from common.confidentials import sheet_url
import requests
import json

class BoxscoreGames(object):

    def __init__(self, current_season: str, season_type: str):
        """
        Initialize the BoxscoreGames class with the current season and season type.
            Args:
                current_season (str): The current season in the format "YYYY-YY".
                season_type (str): The type of season, e.g., "Regular Season", "Playoffs".
        """
        self.current_season: str = current_season
        self.season_type: str = season_type
        self.worksheet: str = boxscore_sheet_name
        self.sheet_url:str = sheet_url

    def get_nba_boxscores(self)-> tuple:
        """
        Fetch the NBA boxscores for the current season and season type.
        Returns:
            list: The list of boxscore rows.
            list: The list of boxscore headers.
        """

        url = f"https://stats.nba.com/stats/leaguegamelog?Counter=1000&DateFrom=&DateTo=&Direction=DESC&LeagueID=00&PlayerOrTeam=P&Season={self.current_season}&SeasonType={self.season_type}&Sorter=DATE"

        headers = {
            "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, identity",
            "x-nba-stats-origin": "stats",
            "x-nba-stats-token": "true",
            "Connection": "keep-alive",
            "Referer": "https://stats.nba.com/",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            data: json = response.json()
            return data["resultSets"][0]["rowSet"], data["resultSets"][0]["headers"]  # Return rows and headers
        except requests.exceptions.RequestException as e:
            print("Error fetching NBA players:", e)
            return None, None


    def update_sheet(self, boxscore_rows, boxscore_headers)->None:
        """
        Update the Google Sheet with the NBA boxscore data.
            Args:
                boxscore_rows (list): The list of boxscore rows to update.
                boxscore_headers (list): The list of boxscore headers.
        """

        # Fetch existing data from the sheet
        worksheet = connect_to_sheet(self.sheet_url, self.worksheet, credentials_file=CREDENTIALS_FILE)
        existing_rows = worksheet.get_all_values()
        # Check if the sheet is empty and add headers
        if boxscore_rows is None or boxscore_headers is None:
            print("No new data to update.")
            return
        
        if not existing_rows:
            # Add headers to the empty sheet
            worksheet.append_row(boxscore_headers)
            print("Headers added to the empty sheet.")

        # Skip the header row and normalize the keys
        existing_keys = set()
        if len(existing_rows) > 1:  # Skip headers if already present
            for row in existing_rows[1:]:
                key = (
                    row[0].strip(),  # SEASON_ID
                    row[1].strip(),  # PLAYER_ID
                    row[3].strip(),  # TEAM_ID
                    row[6].strip()   # GAME_ID
                )
                existing_keys.add(key)

        # Normalize keys for new rows
        new_rows = []
        for row in boxscore_rows:
            key = (
                str(row[0]).strip(),  # SEASON_ID
                str(row[1]).strip(),  # PLAYER_ID
                str(row[3]).strip(),  # TEAM_ID
                str(row[6]).strip()   # GAME_ID
            )
            if key not in existing_keys:
                new_rows.append(row)
                existing_keys.add(key)  # Add key to avoid future duplicates

        # Debugging: Log keys and rows
        print(f"Existing Keys Count: {len(existing_keys)}")
        print(f"New Rows Prepared: {len(new_rows)}")

        # Append only unique rows
        if new_rows:
            worksheet.append_rows(new_rows, value_input_option="RAW")
            print(f"Added {len(new_rows)} new rows to the sheet.")
        else:
            print("No new unique rows to add.")

    def run(self):
        """
        Run the BoxscoreGames process.
        """
        boxscore_rows,boxscore_headers = self.get_nba_boxscores()
        self.update_sheet( boxscore_rows, boxscore_headers)