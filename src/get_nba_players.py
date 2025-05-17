import json
import requests
import random
from time import sleep
from typing import Optional, Tuple, List, Dict

from common.singleton_meta import SingletonMeta
from common.google_sheets_utils import connect_to_sheet
from common.utils import nba_players_sheet_name, CREDENTIALS_FILE
from common.confidentials import sheet_url

class NbaPlayersData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA players data.
    """

    def __init__(self, season_year: str):
        """
        Initialize the NBA players data object.
            Args:
                current_season (str): The current season in the format "YYYY-YY".
        """
        self.season_year: str = season_year


    def get_nba_players(self) -> Tuple[List[List], List[str]]:
        """
        Fetch NBA players data from the NBA stats API and clean it.
        Args:
            proxies: Optional proxy configuration to use for the request.
        Returns:
            tuple: A tuple containing cleaned rows and headers if successful.
        Raises:
            requests.exceptions.RequestException: If the request fails after all retries.
        """
        print("Fetching NBA players data from API...")
        url = f"https://stats.nba.com/stats/playerindex?College=&Country=&DraftPick=&DraftRound=&DraftYear=&Height=&Historical=&LeagueID=00&Season={self.season_year}&SeasonType=Regular%20Season&TeamID=0&Weight="
        print("URL:", url)
        
        headers = {
            "user-agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"]),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "x-nba-stats-origin": "stats",
            "x-nba-stats-token": "true",
            "Referer": "https://stats.nba.com/",
        }
        print("Headers:", headers["user-agent"])
        try:
            response = requests.get(url, headers=headers,  timeout=30)
            print(response)
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            data: json = response.json()
            return data["resultSets"][0]["rowSet"], data["resultSets"][0]["headers"]  # Return rows and headers
        except requests.exceptions.RequestException as e:
            print("Error fetching NBA players:", e)
            return None, None

    def update_sheet(self, players_row: List[List], players_header: List[str]) -> None:
        """
        Update the Google Sheet with the NBA teams data.
        Args:
            players_row (list): The list of players rows to update.
            players_header (list): The list of players headers.
        """
        # Fetch existing data from the sheet
        worksheet = connect_to_sheet(sheet_url, nba_players_sheet_name, credentials_file=CREDENTIALS_FILE)

        # Clear the existing data in the sheet
        print("Clearing existing data in the sheet...")
        worksheet.clear()
        print("Existing data cleared successfully.")

        if not players_row or not players_header:
            print("No new data to update.")
            return
        
        # Write headers
        print("Writing headers to the sheet...")
        worksheet.append_row(players_header, value_input_option="RAW")

        # Write rows
        print(f"Writing {len(players_row)} rows to the sheet...")
        worksheet.append_rows(players_row, value_input_option="RAW")
        
        print("Data updated successfully.")

    def run(self) -> None:
        """
        Run the process to fetch and update NBA players data.
        """
        player_rows, player_headers = self.get_nba_players()
            
        # Update the Google Sheet with the data
        self.update_sheet(player_rows, player_headers)