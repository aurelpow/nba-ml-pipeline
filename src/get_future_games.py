import datetime
import pandas as pd

from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.library.parameters import SeasonNullable

from nba_api.stats.endpoints import leaguegamefinder
from nba_api.stats.library.parameters import LeagueID
from common.singleton_meta import SingletonMeta
from common.io_utils import FutureGamesFileName, save_database
from common.constants import  nba_api_timeout

class NbaGamesLog(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA future games data.
    """

    def __init__(self, save_mode: int, date: datetime.date,  days_number: int,
                 proxy_user: str = None, proxy_pass: str = None) -> None:
        """
        Initialize the NBA future games data object.
            Args:
                save_mode (str): 'local' or 'bq'
                date (datetime.date): The date to start fetching games from. Format: YYYY-MM-DD.
                days_number (int): The number of days to fetch games for.
                proxy_user (str, optional): Proxy username if needed. Defaults to None.
                proxy_user (str, optional): Proxy password if needed. Defaults to None.
        """
        self.date: datetime.date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        self.days_number: int = days_number
        self.SAVE_MODE: int = save_mode
        # Build proxy string only if not running locally
        if self.SAVE_MODE != "local" and proxy_user and proxy_pass:
            self.proxy: str = f"http://{proxy_user}:{proxy_pass}@gate.decodo.com:10001"
        else:
            self.proxy: str = None

    def get_start_date(self) -> datetime.date:
        # Define the start and end dates for the range 
        # Extract the starting year (as an integer)
        start_year = int(SeasonNullable.current_season.split("-")[0])
        # Define start_date as October 1st of that year
        start_date = datetime.date(start_year, 10, 1)
        return start_date

    def get_ended_games_from_api(self) -> pd.DataFrame:
        """
        Retrieves ended NBA games for the current season and season type.
        Returns:
            pd.DataFrame: A DataFrame with game information including game IDs, dates and Matchups.
        """

        # Get the all games from the API 
        games_df: pd.DataFrame = leaguegamefinder.LeagueGameFinder(
            season_nullable=self.current_season,
            league_id_nullable=LeagueID.nba,
            season_type_nullable=self.season_type,
            proxy=self.proxy,
            timeout=nba_api_timeout
        ).get_data_frames()[0]

        # Get unique game IDs and date from the DataFrame
        games_id_date_df : pd.DataFrame = games_df[["GAME_ID","MATCHUP", "GAME_DATE"]].drop_duplicates()
        
        return games_id_date_df

    def get_games_from_api(self, end_date: datetime.date) -> pd.DataFrame:
        """
        Retrieves scheduled NBA games between start_date and end_date.
        
        Args:
            start_date (datetime.date): The starting date
            end_date (datetime.date): The ending date
            
        Returns:
            pd.DataFrame: A DataFrame with game information for the date range.
        """
        all_games = []
        current_date = self.date
        # Loop through the date range
        while current_date <= end_date:
            try:
                # Format the date as mm/dd/yyyy
                game_date_str = current_date.strftime("%m/%d/%Y")
    
                # Retrieve the scoreboard for the current date
                scoreboard = scoreboardv2.ScoreboardV2(
                    game_date=game_date_str,
                      league_id=LeagueID.nba,
                      proxy=self.proxy,
                      timeout=nba_api_timeout
                      )
                
                # Extract the game header DataFrame
                game_header_df = scoreboard.game_header.get_data_frame()
                game_header_df["GAME_DATE"] = game_date_str  # add date info
                
                all_games.append(game_header_df)
            except Exception as e:
                print(f"Error on {current_date}:", e)
            current_date += datetime.timedelta(days=1)
            
        # Check if any games were found
        if all_games:
            # Concatenate all DataFrames into a single DataFrame
            all_games_df = pd.concat(all_games, ignore_index=True)
            # Filter out games that are not yet played
            all_games_df = all_games_df[all_games_df['GAME_STATUS_ID'] == 1]

            return all_games_df
        # If no games are found, return an empty DataFrame
        else:
            return pd.DataFrame()
        
    
    def get_end_date(self) -> datetime.date:
        """
        Calculate the end date for the games to be fetched.
        
        Args:
            start_date (datetime.date): The starting date
        
        Returns:
            datetime.date: The end date for fetching games.
        """
        # For example, fetch games for 7 days from the start date
        return self.date + datetime.timedelta(days=self.days_number)

    def run(self) -> pd.DataFrame:
        """
        Run the process to fetch and update NBA future games data.
        
        Returns:
            pd.DataFrame: A DataFrame with game information for the date range.
        """
        # Get the end date 
        end_date: datetime = self.get_end_date()
        
        # Fetch the games from the API
        games_df: pd.DataFrame = self.get_games_from_api(end_date)

        # Save the DataFrame locally (optional)
        save_database(games_df, FutureGamesFileName, mode=self.SAVE_MODE)
        print(f"✅ Future Games data saved with mode: {self.SAVE_MODE}")
    