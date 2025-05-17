import requests 
import pandas as pd 

from common.utils import nba_teams_sheet_name, CREDENTIALS_FILE
from common.google_sheets_utils import connect_to_sheet
from common.confidentials import sheet_url


class NbaTeamsData(object):
    """
    A class to fetch and update NBA teams data.
    """

    def __init__(self, season_year: str):
        """
        Initialize the NBA teams data object.

        Args:
            sheet_url (str): The URL of the Google Sheet.
            worksheet (str): The title of the worksheet to connect to.
        """
        self.season_year:str = season_year
        self.sheet_url:str = sheet_url
        self.worksheet:str = nba_teams_sheet_name

    def get_nba_teams(self)-> tuple:
        """
        Fetch NBA teams data from the NBA stats API and clean it.

        Returns:
            tuple: A tuple containing cleaned rows and headers if successful, or None if an error occurs.
        """
        url:str = "https://stats.nba.com/stats/franchisehistory?LeagueID=00&Season="
        season: str = self.season_year 

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
            data = response.json()

            # Extract rows and headers
            rows = data["resultSets"][0]["rowSet"]
            headers = data["resultSets"][0]["headers"]

            # Add "logo_url" to the headers
            if "logo_url" not in headers:
                headers.append("logo_url")

            # Append logo URL to each row
            for row in rows:
                team_id = row[headers.index("TEAM_ID")]
                logo_url = f"https://cdn.nba.com/logos/nba/{team_id}/primary/L/logo.svg"
                row.append(logo_url)
            # Create a DataFrame for processing
            df = pd.DataFrame(rows, columns=headers)

            # Filter rows with END_YEAR == season_year
            df = df[df["END_YEAR"] == season]
            # Remove duplicates, keeping the row with the lowest START_YEAR for each TEAM_ID
            df = df.loc[df.groupby("TEAM_ID")["START_YEAR"].idxmin()]

            # Keep only the specified columns
            columns_to_keep = ["LEAGUE_ID", "TEAM_ID", "TEAM_CITY", "TEAM_NAME", "START_YEAR", "END_YEAR", "logo_url"]
            df = df[columns_to_keep]

            # Convert the DataFrame back to a list of rows and update headers
            rows_cleaned = df.values.tolist()
            headers_cleaned = df.columns.tolist()

            return rows_cleaned, headers_cleaned

        except requests.exceptions.RequestException as e:
            print("Error fetching NBA teams:", e)
            return None, None
        
    def update_sheet(self, team_rows, team_headers)->None:
        """
        Update the Google Sheet with the NBA teams data.

        Args:
            team_rows (list): The list of team rows to update.
            team_headers (list): The list of team headers.
        """
        # Fetch existing data from the sheet
        worksheet = connect_to_sheet(self.sheet_url, self.worksheet, credentials_file=CREDENTIALS_FILE)
        existing_rows = worksheet.get_all_values()

        # Check if the sheet is empty and add headers
        if team_rows is None or team_headers is None:
            print("No new data to update.")
            return

        if not existing_rows:
            # Add headers to the empty sheet
            worksheet.append_row(team_headers)
            print("Headers added to the empty sheet.")

        # Update the sheet with new data
        for row in team_rows:
            worksheet.append_row(row)

        print("Data updated successfully.")

    def run(self)->None:
        """
        Run the process to fetch and update NBA teams data.
        """
        team_rows, team_headers = self.get_nba_teams()
        self.update_sheet(team_rows, team_headers)