import time
import random
import pandas as pd
import requests

from nba_api.stats.endpoints import boxscoretraditionalv3
from nba_api.stats.library.parameters import LeagueID

from common.io_utils import save_database, load_data, BoxscoreFileName, ScheduleFileName
from common.constants import nba_api_timeout
from common.singleton_meta import SingletonMeta
from common.utils import build_proxy_url, call_nba_api_with_retry

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
        self.proxy: str | None = build_proxy_url(proxy_user, proxy_pass)
        print(f"[PROXY] boxscore_basic → {'enabled' if self.proxy else 'disabled (no creds)'}")

    def get_schedule(self) -> pd.DataFrame:
        """
        Fetch and process NBA schedule for self.current_season_year.
        Only regular season & playoffs are returned.
        Args:
            None
        Returns:
            pd.DataFrame: Processed schedule data
        """
        # Load the full schedule from our schedule dataframe
        schedule_df: pd.DataFrame = load_data(ScheduleFileName, mode=self.SAVE_MODE)
        
        # Ensure gameId is string with leading zeros
        schedule_df['gameId'] = schedule_df['gameId'].astype(str).str.zfill(10)
        
        # Flag if games are in the playoffs
        schedule_df['is_playoffs'] = schedule_df['gameId'].str.startswith('004')

        # Flag if games are in the Regular Season
        schedule_df['is_regular_season'] = schedule_df['gameId'].str.startswith('002')

        # Remove games not in regular season or playoffs
        games_df = schedule_df[schedule_df['is_playoffs'] | schedule_df['is_regular_season']]

        # Rename columns for clarity
        games_df = games_df.rename(columns={
            "gameId": "game_id",
            "homeTeam_teamId": "home_team_id",
            "homeTeam_teamTricode": "home_team_tricode",
            "awayTeam_teamId": "visitor_team_id",
            "awayTeam_teamTricode": "visitor_team_tricode",
            "gameDate": "game_date",
            "gameStatus": "game_status",
            "gameStatusText": "game_status_text"
        })

        # Select and order columns
        games_df = games_df[[
            "game_id",
            "is_regular_season",
            "is_playoffs",
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
            boxscore: pd.DataFrame = call_nba_api_with_retry(
                lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(
                    game_id=game_id,
                    proxy=proxy_arg,
                    timeout=nba_api_timeout,
                ).get_data_frames()[0]
            )
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

        # Determine already processed game IDs
        if existing_df is None: # Case when there is no file yet (first run)
            processed_game_ids: set = set()
        elif not existing_df.empty and "gameId" in existing_df.columns: # only if existing data has gameId col
            if self.SAVE_MODE == "bq": # In BQ gameID is stored as string (so we already have 00 prefix)
                processed_game_ids: set = set(existing_df["gameId"].astype(str).unique())
            else: # In local CSV gameID is stored as int (no leading zeros)
                processed_game_ids: set = {f"00{gid}" for gid in existing_df["gameId"].astype(int).unique()}
        elif existing_df.empty:  # Case when there is no existing data 
            processed_game_ids: set = set()
        else: # Case when existing data has no gameId col (should not happen)
            processed_game_ids: set = set()

        # Filter schedule to only ended games (status "3")
        schedule_df = schedule_df[schedule_df["game_status"].astype(str) == "3"]

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
        
        # Only select relevant columns 
        final_columns: list = [
            "gameId",
            "teamId",
            "teamTricode",
            "personId",
            "playerSlug",
            "position",
            "minutes",
            "fieldGoalsMade",
            "fieldGoalsAttempted",
            "fieldGoalsPercentage",
            "threePointersMade",
            "threePointersAttempted",
            "threePointersPercentage",
            "freeThrowsMade",
            "freeThrowsAttempted",
            "freeThrowsPercentage",
            "reboundsOffensive",
            "reboundsDefensive",
            "reboundsTotal",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "foulsPersonal",
            "points",
            "is_regular_season",
            "is_playoffs",
            "game_date",
            "home_team_id",
            "visitor_team_id",
            "game_status_text"
        ]

        # Convert date to date without timezone info
        new_boxscores_df['game_date'] = pd.to_datetime(new_boxscores_df['game_date']).dt.strftime('%Y-%m-%d')

        # Combine with existing data if not none or empty 
        if existing_df is None:
            final_df: pd.DataFrame = new_boxscores_df
        elif existing_df.empty:
            final_df: pd.DataFrame = new_boxscores_df
        else: # existing data is not empty
            final_df: pd.DataFrame = (
                pd.concat([existing_df, new_boxscores_df], ignore_index=True)
                )
        
        # return final dataframe or new datafdrame 
        if self.SAVE_MODE == 'local':
            return final_df[final_columns]
        else:
            return new_boxscores_df[final_columns]
    
    def run(self):
        """
        Run the BoxscoreGames process.
        """
        # Get the schedule data
        schedule_df_current_season: pd.DataFrame = self.get_schedule()
        
        # Get the boxscore data (new + existing)
        boxscore_df = self.get_boxscore_data(schedule_df_current_season)

        # Save the combined boxscore data
        save_database(df=boxscore_df,
                      table_name=BoxscoreFileName, 
                      mode=self.SAVE_MODE, 
                      write_disposition="WRITE_APPEND",
                      autodetect_schema=True
                      )