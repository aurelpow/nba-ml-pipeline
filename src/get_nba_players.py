import pandas as pd 
import time 

from nba_api.stats.endpoints import playerindex
from nba_api.stats.endpoints import commonplayerinfo
from common.singleton_meta import SingletonMeta
from common.utils import  save_database_local
import nba_api.stats.library.http as http_lib
import nba_api.stats.library.http as http
http_lib._NBAStatsHTTP__timeout = 60
# Make the NBA-API pretend to be a browser
http.NBAStatsHTTP.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
})

class NbaPlayersData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA players data.
    """

    def __init__(self, current_season: str) -> None:
        """
        Initialize the NBA players data object.
            Args:
                current_season (str): The current season in the format "YYYY-YY".
        """
        self.current_season: str = current_season
        self.file_name: str = f"nba_players_df_{current_season}"

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
        players_df: pd.DataFrame = self.get_nba_players_index()
        
        # Save the df as .csv file in the databases folder
        save_database_local(players_df, self.file_name)