
import pandas as pd
import nba_api.stats.library.http as http_lib
import requests 

from nba_api.stats.endpoints import boxscoretraditionalv3
from nba_api.stats.library.parameters import LeagueID
from common.utils import  (save_database, load_data,
                            BoxscoreFileName) 
from common.singleton_meta import SingletonMeta
 


# Override default headers with a custom User-Agent.
http_lib.STATS_HEADERS['User-Agent'] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/95.0.4638.54 Safari/537.36"
)

class BoxscoreGames(metaclass=SingletonMeta):

    def __init__(self, current_season: str, save_mode: str) -> None:
        """
        Initialize the BoxscoreGames class with the current season and season type.
            Args:
                current_season (str): The current season in the format "YYYY-YY".
                season_type (str): The type of season, e.g., "Regular Season", "Playoffs".
                save_mode (str): The mode to save data, either 'local' or 'bq' (google bigquery). 
        """
        print(f"Initializing BoxscoreGames with season: {current_season}")
        self.current_season: str = current_season
        self.current_season_year: int = int(current_season.split("-")[0])
        self.SAVE_MODE: str = save_mode

    
    def get_schedule(self):
        """
        Fetches and processes NBA schedule data for a given season year.
        
        Args:
            current_season_year (int): The year of the season (default: 2024)
            
        Returns:
            pandas.DataFrame: Processed schedule data
        """
        # Define the URL for the NBA schedule data
        url = f"http://data.nba.com/data/10s/v2015/json/mobile_teams/nba/{self.current_season_year}/league/{LeagueID.default}_full_schedule.json"
        
        # Get the data
        r = requests.get(url)
        data = r.json()

        # Initialize an empty list to store all games
        all_games_list = []
        
        # Iterate through the league schedule data
        for month in data['lscd']:
            # Extract games from each month
            if 'mscd' in month and 'g' in month['mscd']:
                games = month['mscd']['g']
                all_games_list.extend(games)

        # Convert the list of games to a DataFrame
        games_df = pd.json_normalize(all_games_list)

        # Rename the columns to be more readable
        games_df = games_df.rename(columns={
            'gid': 'game_id',
            'seri': 'playoffs_desc',
            'st': 'game_status',
            'stt': 'game_status_text',
            'gdte': 'game_date',
            'h.tid': 'home_team_id',
            'h.ta': 'home_team_tricode',
            'v.tid': 'visitor_team_id',
            'v.ta': 'visitor_team_tricode',
        })

        # Flag if games are in the playoffs
        games_df['is_playoffs'] = games_df['game_id'].str.startswith('004')
        # Flag if games are in the Regular Season 
        games_df['is_regular_season'] = games_df['game_id'].str.startswith('002')
        # Remove games not in regular season or playoffs
        games_df = games_df[games_df['is_playoffs'] | games_df['is_regular_season']]

        # Select and order columns
        games_df = games_df[[
            "game_id",
            "is_regular_season",
            "is_playoffs",
            "playoffs_desc",
            "game_date",
            "home_team_id",
            "home_team_tricode",
            "visitor_team_id",
            "visitor_team_tricode",
            "game_status",
            "game_status_text"
        ]]

        return games_df

    @staticmethod
    def fetch_boxscore(game_id: str) -> pd.DataFrame:
        """
        Helper function to fetch a single game's boxscore.
        
        Args:
            game_id (str): The game ID.
            
        Returns:
            pd.DataFrame: The boxscore DataFrame for the game or an empty DataFrame on error.
        """
        try:
            # Increase timeout if needed (here, timeout=1 second)
            boxscore: pd.DataFrame = boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=game_id, 
                timeout=0.600
            ).get_data_frames()[0]
            print(f"Fetched boxscore for game ID {game_id}")
            return boxscore
        
        except Exception as e:
            print(f"Error fetching boxscore for game ID {game_id}: {e}")
            return pd.DataFrame()   
        

    def get_boxscore_data(self, schedule_df: pd.DataFrame) -> pd.DataFrame:
        """
        Retrieves boxscore data for new game IDs.
        
        Compares against a local CSV to avoid re-fetching.
        
        Args:
            game_id_list (list): A list of game IDs from the API.
        
        Returns:
            pd.DataFrame: A DataFrame with the updated boxscore data.
        """
        # Load existing data if available
        existing_df: pd.DataFrame = load_data(BoxscoreFileName, mode= self.SAVE_MODE)
        if not existing_df.empty and "gameId" in existing_df.columns:
            # Get unique game IDs from the existing DataFrame
            processed_game_ids: set = set(existing_df["gameId"].unique())
            # Convert game IDs to string format with leading zeros
            processed_game_ids = {f"00{gid}" for gid in processed_game_ids}
        else:
            processed_game_ids: set = set()
        
        # Filter the schedule DataFrame to only include games that are completed
        schedule_df: pd.DataFrame = schedule_df[schedule_df["game_status"] == "3"]
        # Get the list of game IDs from the API DataFrame
        game_id_list: list = schedule_df["game_id"].tolist()

        # Filter game IDs to only new ones
        new_game_ids: list = [gid for gid in game_id_list if gid not in processed_game_ids]
        print(f"Total game IDs: {len(game_id_list)}; New game IDs to process: {len(new_game_ids)}")

        # Create an empty list to store new results
        new_results = []
        # Use a loop over new game IDs to fetch boxscores
        for game_id in new_game_ids:
            result_df = self.fetch_boxscore(game_id)
            if not result_df.empty:
                new_results.append(result_df)
            else:
                print(f"Failed to fetch boxscore for game ID {game_id}")

        # Combine new results with existing data if any new data was fetched
        if new_results:
            # Filter out any DataFrame that is empty or all NA before concatenation.
            new_results = [df for df in new_results if not df.empty and not df.isna().all().all()]
            if new_results:
                new_boxscores_df: pd.DataFrame = pd.concat(new_results, ignore_index=True)
                # Merge with scheduke DataFrame to add game details
                new_boxscores_df: pd.DataFrame = new_boxscores_df.merge(
                schedule_df, 
                left_on="gameId",
                right_on="game_id",
                how="left"
            )
                
            else : new_boxscores_df: pd.DataFrame = pd.DataFrame()
            
            if not existing_df.empty:
                final_df:pd.DataFrame = pd.concat([existing_df, new_boxscores_df], ignore_index=True)
            else:
                final_df: pd.DataFrame = new_boxscores_df
            

            return final_df
        else:
            print("No new boxscore data to fetch.")
            return existing_df


    def run(self):
        """
        Run the BoxscoreGames process.
        """
        # Gest the schedule data
        schedule_df_current_season = self.get_schedule()
        
        # Get the boxscore data for new game IDs only
        boxscore_df = self.get_boxscore_data(schedule_df_current_season)        

        # Save the combined DataFrame locally
        save_database(boxscore_df, BoxscoreFileName, mode= self.SAVE_MODE)