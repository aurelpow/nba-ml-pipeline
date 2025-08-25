import pandas as pd

from nba_api.stats.endpoints import playerindex

from common.singleton_meta import SingletonMeta
from common.io_utils import PlayersFileName, save_database
from common.utils import  nba_api_timeout



class NbaPlayersData(metaclass=SingletonMeta):
    """
    Simple process:
    - Loop CommonTeamRoster(season, team_id) for all 30 teams
    - Keep core columns (PLAYER_ID, TEAM_ID, POSITION, HEIGHT, WEIGHT, NUM)
    - (Optional) Use CommonPlayerInfo per player if you ever want extra fields
    - Save with save_database like your other processes
    """

    def __init__(self, current_season: str, save_mode: str,
                    proxy_user: str = None, proxy_pass: str = None) -> None:
        self.current_season: str = current_season  # e.g., "2024-25"
        self.file_name: str = f"{PlayersFileName}_{current_season}"
        self.SAVE_MODE: str = save_mode
        # Build proxy string only if not running locally
        if self.SAVE_MODE != "local" and proxy_user and proxy_pass:
            self.proxy: str = f"http://{proxy_user}:{proxy_pass}@gate.decodo.com:10001"
        else:
            self.proxy: str = None
  
    def get_nba_players_index(self) -> pd.DataFrame:
        """
        Fetch NBA players data from the NBA stats API and clean it.
        """
        # Get a list of all NBA teams (each team is represented as a dictionary)
        print("Fetching Active NBA players data from API...")
        playerindex_df: pd.DataFrame =  playerindex.PlayerIndex(season=self.current_season,
                                                                proxy= self.proxy,
                                                                timeout= nba_api_timeout
                                                                ).get_data_frames()[0]

        return playerindex_df

    def run(self) -> None:
        print(f"Fetching NBA players for season {self.current_season} ...")
        try:
            df = self.get_nba_players_index()
            if df is not None and not df.empty:
                save_database(df, self.file_name, mode=self.SAVE_MODE)
                print(f"✅ Players data saved with mode: {self.SAVE_MODE} (rows={len(df)})")
            else:
                print("⚠️ No players data fetched. Process skipped.")
        except Exception as e:
            print(f"❌ Failed to fetch players: {e}")