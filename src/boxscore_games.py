import requests
from common.google_sheets_utils import connect_to_sheet
from common.utils import boxscore_sheet_name
from common.confidentials import sheet_url

Class BoxscoreGames(object):

    def __init__(self,current_season :str, season_type : str):
        self.current_season = current_season
        self.season_type = season_type
        self.worksheet= boxscore_sheet_name
        self.sheet_url = sheet_url

    def get_nba_boxscores(self):
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
            data = response.json()
            return data["resultSets"][0]["rowSet"], data["resultSets"][0]["headers"]  # Return rows and headers
        except requests.exceptions.RequestException as e:
            print("Error fetching NBA players:", e)
            return None, None

    def update(self, data):
        """
        Update the worksheet with new data.
        Clears existing data and writes headers + rows.
        """
        self.worksheet.clear()  # Clear existing content

        # Write new data
        if len(data) > 0:
            self.worksheet.append_rows(data, value_input_option="RAW")  # Insert rows
        print(f"Updated {self.worksheet.title} successfully!")
```
