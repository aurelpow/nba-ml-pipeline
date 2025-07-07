import pandas as pd 
from nba_api.stats.static import teams
from common.utils import  save_database_local
from common.singleton_meta import SingletonMeta

class NbaTeamsData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA teams data.
    """

    def __init__(self)->None:
        """
        Initialize the NBA teams data object.
        """

    def get_nba_teams(self)-> tuple:
        """
        Fetch NBA teams data from the NBA stats API and clean it.
        Returns:
            tuple: A tuple containing cleaned rows and headers if successful, or None if an error occurs.
        """  
        print("Fetching NBA teams data from API...")
        all_teams: dict = teams.get_teams()
        
        # Convert the JSON data to a DataFrame 
        teams_df: pd.DataFrame = pd.DataFrame(all_teams)

        return teams_df

    def run(self)->None:
        """
        Run the process to fetch and update NBA teams data.
        """
        nba_teams_df = self.get_nba_teams()

        save_database_local(nba_teams_df, "nba_teams_df")