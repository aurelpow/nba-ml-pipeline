import pandas as pd

from nba_api.stats.endpoints import scheduleleaguev2
from nba_api.stats.library.parameters import LeagueID
from common.singleton_meta import SingletonMeta
from common.io_utils import ScheduleFileName, save_database
from common.constants import  nba_api_timeout


class ScheduleData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA schedule data. 
    """

    def __init__(self, current_season: str, save_mode: str,
                proxy_user:str = None, proxy_pass: str = None) -> None: 
        """
        Initialize the NBA schedule data for a given season
            Args:
            current_season (str) : The season to fetch players for, e.g., "2024-25" 
            save_mode (str): Where to save the output ('bq' or 'local')
            proxy_user (str, optional): Proxy username if needed. Defaults to None.
            proxy_user (str, optional): Proxy password if needed. Defaults to None.
        """
        self.current_season: str = current_season
        self.SAVE_MODE: str = save_mode
        # Build proxy string only if not running locally
        if self.SAVE_MODE != "local" and proxy_user and proxy_pass:
            self.proxy: str = f"http://{proxy_user}:{proxy_pass}@gate.decodo.com:10001"
        else:
            self.proxy: str = None

    
    def get_schedule_from_api(self) -> pd.DataFrame:
        """
        Fetch NBA schedule data from the NBA API.
        
        Returns:
            pd.DataFrame: A DataFrame with the NBA shedule for the current season. 
        """
        # Use the ScheduleLeagueV2 endpoint to get the schedule for the current season
        scheduleleaguev2_df: pd.DataFrame = scheduleleaguev2.ScheduleLeagueV2(
            league_id=LeagueID.nba,
            season=self.current_season,
            proxy=self.proxy,
            timeout=nba_api_timeout
        ).get_data_frames()[0]

        return scheduleleaguev2_df
    
    @staticmethod
    def transform_data( df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform data
            Args:
                df (pd.DataFrame): The DataFrame to transform.
            Returns:
                pd.DataFrame: The transformed DataFrame. 
        """
        # First, only keep relevant columns
        relevant_columns = [
            "seasonYear",
            "gameDate",
            "gameId",
            "gameStatus",
            "gameStatusText",
            "gameDateTimeUTC",
            "gameLabel",
            "gameSubLabel",
            "seriesGameNumber",
            "seriesText",
            "postponedStatus",
            "gameSubtype",
            "isNeutral",
            "arenaName",
            "arenaState", 
            "arenaCity",
            "homeTeam_teamId",
            "homeTeam_teamTricode",
            "awayTeam_teamId",
            "awayTeam_teamTricode",
            "nationalBroadcasters_broadcasterDisplay"
        ]

        # Filter the DataFrame with columns defined above 
        df_filtered: pd.DataFrame = df[relevant_columns].copy() 

        # Transform date columns to datetime
        df_filtered["gameDate"] = pd.to_datetime(df_filtered["gameDate"])
        df_filtered["gameDateTimeUTC"] = pd.to_datetime(df_filtered["gameDateTimeUTC"])
        
        return df_filtered

    def run(self):
        """
        Run the Schedule NBA process. 
        """
        # Get the schedule data from the NBA API 
        schedule_df: pd.DataFrame = self.get_schedule_from_api()

        # Transform the data
        schedule_df_filtered: pd.DataFrame = self.transform_data(schedule_df)
        # Save the schedule data 
        save_database(df=schedule_df_filtered,
                    table_name=ScheduleFileName,
                    mode=self.SAVE_MODE,
                    write_disposition="WRITE_TRUNCATE", 
                    autodetect_schema=True 
                    )