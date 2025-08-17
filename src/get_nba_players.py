import pandas as pd 

from common.singleton_meta import SingletonMeta
from common.utils import  PlayersFileName, save_database


from nba_api.stats.endpoints import playerindex
import nba_api.stats.library.http as http_lib
import nba_api.stats.library.http as http
import time 
import random
import requests
from requests.exceptions import ReadTimeout, Timeout, ConnectionError as ReqConnectionError
http_lib._NBAStatsHTTP__timeout = 60
# Make the NBA-API pretend to be a browser
http.NBAStatsHTTP.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.nba.com/",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
})

class NbaPlayersData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA players data.
    """

    def __init__(self, current_season: str, save_mode: str) -> None:
        """
        Initialize the NBA players data object.
            Args:
                current_season (str): The current season in the format "YYYY-YY".
                save_mode (str): The mode to save the data, either "bq" for BigQuery or "local" for local storage.
        """
        self.current_season: str = current_season
        self.file_name: str = f"{PlayersFileName}_{current_season}"
        self.SAVE_MODE: str = save_mode
        self.MAX_TRIES: int = 5 
        self.DEFAULT_TIMEOUT: int = 90
        self.BASE_BACKOFF: int = 1.5


    def _with_retry_fetch_players(self) -> pd.DataFrame:
        """
        Call NBA PlayerIndex with retries, exponential backoff, and jitter.
        """
        last_err = None
        for attempt in range(1, self.MAX_TRIES + 1):
            try:
                # Pass timeout directly to the endpoint (this actually works; the class var often doesn't)
                df = playerindex.PlayerIndex(season=self.current_season, timeout=self.DEFAULT_TIMEOUT).get_data_frames()[0]
                return df

            except (ReadTimeout, Timeout, ReqConnectionError, requests.HTTPError) as e:
                last_err = e
                # Backoff with jitter to play nice with CDN/rate-limits
                sleep_s = self.BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, 0.75)
                # Optional: cap the backoff if you prefer
                sleep_s = min(sleep_s, 20)
                print(f"[retry {attempt}/self.{self.MAX_TRIES}] NBA API error: {repr(e)}; sleeping {sleep_s:.1f}s...")
                time.sleep(sleep_s)

        # If we got here, all retries failed
        raise RuntimeError(f"Failed to fetch PlayerIndex for season {self.current_season} after {self.MAX_TRIES} attempts") from last_err

    def get_nba_players_index(self) -> pd.DataFrame:
        """
        Fetch NBA players data from the NBA stats API and clean it.
        """
        # Get a list of all NBA teams (each team is represented as a dictionary)
        print("Fetching Active NBA players data from API...")
        playerindex_df: pd.DataFrame =  playerindex.PlayerIndex(season=self.current_season).get_data_frames()[0]

        return playerindex_df


    def run(self) -> None:
        """
        Run the process to fetch and update NBA players data.
        """

        # Get detailed player information for the active players
        players_df: pd.DataFrame = self._with_retry_fetch_players()
        
        # Save the df as .csv file in the databases folder
        save_database(players_df, self.file_name, mode = self.SAVE_MODE)
        print(f"✅ Players data saved with mode: {self.SAVE_MODE}")