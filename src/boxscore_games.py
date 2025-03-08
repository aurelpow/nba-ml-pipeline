import requests
from common.google_sheets_utils import connect_to_sheet
from common.utils import boxscore_sheet_name
from common.confidentials import sheet_url

class BoxscoreGames(object):

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


    def update_sheet(self):
        # Fetch existing data from the sheet
        worksheet = connect_to_sheet(self.sheet_url, self.worksheet)
        existing_rows = worksheet.get_all_values()
        # Check if the sheet is empty and add headers
        rows, headers = BoxscoreGames.get_nba_boxscores()
        if rows is None or headers is None:
            print("No new data to update.")
            return
        
        if not existing_rows:
            # Add headers to the empty sheet
            worksheet.append_row(headers)
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
        for row in rows:
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
        self.update_sheet()
