import pandas as pd 
from nba_api.stats.static import teams
from common.io_utils import  TeamsFileName, save_database
from common.singleton_meta import SingletonMeta

class NbaTeamsData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA teams data.
    """

    def __init__(self, save_mode: str)->None:
        """
        Initialize the NBA teams data object.
        Args:
            save_mode (str): Where to save the output ('bq' or 'local')
        """
        self.SAVE_MODE: str = save_mode


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
        try:
            nba_teams_df: pd.DataFrame = self.get_nba_teams()
            if nba_teams_df is not None and not nba_teams_df.empty:
                save_database(nba_teams_df, TeamsFileName, mode=self.SAVE_MODE)
                print(f"✅ Teams data saved with mode: {self.SAVE_MODE}")
            else:
                print("⚠️ No teams data fetched. Process skipped.")
        except Exception as e:
            print(f"❌ Failed to fetch players: {e}")