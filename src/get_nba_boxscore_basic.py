import time
import random
import pandas as pd
import requests

from nba_api.stats.endpoints import boxscoretraditionalv3
from nba_api.stats.library.parameters import LeagueID

from common.io_utils import save_database, load_data, BoxscoreFileName
from common.utils import  nba_api_timeout
from common.singleton_meta import SingletonMeta

class BoxscoreGames(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA boxscore data for ended games.
    """
    def __init__(self, current_season: str, save_mode: str,
                 proxy_user: str = None, proxy_pass: str = None) -> None:
        """
        Args:
            current_season (str): format "YYYY-YY"
            save_mode (str): 'local' or 'bq'
            proxy_user (str, optional): Proxy username if needed. Defaults to None.
            proxy_user (str, optional): Proxy password if needed. Defaults to None.
        """

        print(f"Initializing BoxscoreGames with season: {current_season}")
        self.current_season: str = current_season
        self.current_season_year: int = int(current_season.split("-")[0])
        self.SAVE_MODE: str = save_mode
        # Build proxy string only if not running locally
        if self.SAVE_MODE != "local" and proxy_user and proxy_pass:
            self.proxy: str = f"http://{proxy_user}:{proxy_pass}@gate.decodo.com:10001"
        else:
            self.proxy: str = None

    def get_schedule(self) -> pd.DataFrame:
        """
        Fetch and process NBA schedule for self.current_season_year.
        Only regular season & playoffs are returned.
        Args:
            None
        Returns:
            pd.DataFrame: Processed schedule data
        """
        # Define the URL for the NBA schedule data
        url = (
            f"https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/"
            f"{self.current_season_year}/league/{LeagueID.default}_full_schedule.json"
        )
        
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
    def fetch_boxscore(game_id: str, proxy_arg) -> pd.DataFrame:
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
                proxy=proxy_arg,
                timeout=nba_api_timeout
            ).get_data_frames()[0]
            print(f"Fetched boxscore for game ID {game_id}")

            return boxscore
        
        except Exception as e:
            print(f"Error fetching boxscore for game ID {game_id}: {e}")
            return pd.DataFrame() 

    def get_boxscore_data(self, schedule_df: pd.DataFrame) -> pd.DataFrame:
        """
        Retrieve boxscores for finals that are not yet saved.
        Args:
            schedule_df (pd.DataFrame): The schedule DataFrame with game IDs.
        Returns:
            pd.DataFrame: The combined boxscore DataFrame including new and existing data.
        """
        # Fetch already processed game IDs (avoid re-processing)
        existing_df: pd.DataFrame = load_data(BoxscoreFileName, mode=self.SAVE_MODE)

        if not existing_df.empty and "gameId" in existing_df.columns: # only if existing data has gameId col
            if self.SAVE_MODE == "bq": # In BQ gameID is stored as string (so we already have 00 prefix)
                processed_game_ids: set = set(existing_df["gameId"].astype(str).unique())
            else: # In local CSV gameID is stored as int (no leading zeros)
                processed_game_ids: set = {f"00{gid}" for gid in existing_df["gameId"].astype(int).unique()}
        else: # Empty existing data 
            processed_game_ids: set = set()

        # Filter schedule to only ended games (status "3"
        schedule_df = schedule_df[schedule_df["game_status"] == "3"]
        
        # Create List of Ended game IDs 
        game_id_list = schedule_df["game_id"].astype(str).tolist()

        # Identify new game IDs to process 
        new_game_ids = [gid for gid in game_id_list if gid not in processed_game_ids]
        # Print total of games and new to process
        print(f"Total finals: {len(game_id_list)}; New to process: {len(new_game_ids)}")

        # With a loop over new game IDs, fetch boxscores using function above
        new_results = []
        for i, game_id in enumerate(new_game_ids, 1):
            print(f"[{i}/{len(new_game_ids)}] Fetching {game_id}...")
            result_df = self.fetch_boxscore(game_id, self.proxy)
            if not result_df.empty:
                new_results.append(result_df)
            else:
                print(f"Failed to fetch boxscore for game ID {game_id}")
            # polite pacing between calls (randomized)
            time.sleep(random.uniform(0.6, 1.2))

        # Check if we have new games fetched
        if not new_results:
            print("No new boxscore data to fetch.")
            return existing_df

        # Concatenate all new results into a Pandas DataFrame
        new_boxscores_df: pd.DataFrame = pd.concat(new_results, ignore_index=True)

        # Merge with schedule to get more metadata
        new_boxscores_df: pd.DataFrame = new_boxscores_df.merge(
            schedule_df,
            left_on="gameId",
            right_on="game_id",
            how="left",
        )
        
        # Combine with existing data if any
        final_df: pd.DataFrame = (
            pd.concat([existing_df, new_boxscores_df], ignore_index=True)
            if not existing_df.empty
            else new_boxscores_df
        )

        return final_df
    
    def run(self):
        """
        Run the BoxscoreGames process.
        """
        # Get the schedule data
        schedule_df_current_season: pd.DataFrame = self.get_schedule()
        
        # Get the boxscore data (new + existing)
        boxscore_df = self.get_boxscore_data(schedule_df_current_season)
        
        # Save the combined boxscore data
        save_database(boxscore_df, BoxscoreFileName, mode=self.SAVE_MODE)