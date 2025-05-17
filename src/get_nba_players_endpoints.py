import logging
import time
import pandas as pd
from nba_api.stats.endpoints import commonallplayers, commonplayerinfo

from common.singleton_meta import SingletonMeta
from common.utils import nba_players_sheet_name, CREDENTIALS_FILE
from common.google_sheets_utils import connect_to_sheet
from common.confidentials import sheet_url

class NbaPlayersData(metaclass=SingletonMeta):
    """
    A class to fetch and update NBA players data.
    """
    
    def get_nba_players_common(self) -> list:
        """
        Retrieve a list of active NBA players' IDs using the nba_api endpoint.
        
        Returns:
            list: A list of active NBA players' PERSON_IDs.
        """
        retries = 3
        for attempt in range(retries):
            try:
                print("Fetching active NBA players from nba_api...")
                # Increase timeout in case the remote call takes longer
                df = commonallplayers.CommonAllPlayers(is_only_current_season=1, timeout=60).get_data_frames()[0]
                if df.empty:
                    raise ValueError("Received an empty dataframe for active players.")
                print(f"Retrieved {len(df)} active players.")
                return list(df["PERSON_ID"])
            except Exception as e:
                print(f"Error fetching active NBA players on attempt {attempt+1}: {e}")
                if attempt < retries - 1:
                    print("Retrying after 10 seconds...")
                    time.sleep(10)
                else:
                    print("All attempts failed. Returning empty player list.")
                    return []

    def get_nba_players_info(self, players_id_list: list) -> pd.DataFrame:
        """
        Retrieve the information of NBA players given a list of player IDs.
        
        Args:
            players_id_list (list): A list of NBA player IDs.
        
        Returns:
            pd.DataFrame: A DataFrame containing the information of NBA players.
        """
        players_info = []
        # Ensure we have IDs to iterate over
        if not players_id_list:
            print("No player IDs found; skipping player info retrieval.")
            return pd.DataFrame()
        
        for p_id in players_id_list:
            try:
                print(f"Fetching player info for ID: {p_id}...")
                player_info = commonplayerinfo.CommonPlayerInfo(player_id=p_id, timeout=60).get_data_frames()[0]
                players_info.append(player_info)
                time.sleep(.600)  # Sleep for 600ms to avoid rate limiting
            except Exception as e:
                print(f"Error fetching player info for ID: {p_id}", exc_info=True)
        
        # Only concatenate if we have at least one dataframe
        if players_info:
            return pd.concat(players_info)
        else:
            print("No player info dataframes to concatenate.")
            return pd.DataFrame()

    def update_sheet(self, players_df: pd.DataFrame) -> None:
        """
        Update the Google Sheet with the NBA players data.
        
        Args:
            players_df (pd.DataFrame): The DataFrame of players data to update.
        """
        wk_players = connect_to_sheet(sheet_url, nba_players_sheet_name, credentials_file=CREDENTIALS_FILE)  # type: ignore
        
        print("Clearing existing data in the sheet...")
        wk_players.clear()
        print("Existing data cleared successfully.")
        
        if players_df.empty:
            logging.info("No new data to update.")
            return
        
        # Convert DataFrame to 2D list (header + data)
        data = [players_df.columns.tolist()] + players_df.values.tolist()
        
        print("Writing data to the sheet...")
        wk_players.update("A1", data)
        print("Data updated successfully.")

    def run(self) -> None:
        """
        Run the process to fetch and update NBA players data.
        """
        # Fetch active player IDs
        players_id_list = self.get_nba_players_common()
        if not players_id_list:
            print("Failed to retrieve any active player IDs. Exiting process.")
            return
        
        # Fetch detailed player info
        final_df = self.get_nba_players_info(players_id_list)
        if final_df.empty:
            print("No player info retrieved. Exiting process.")
            return
        
        # Update the Google Sheet with the data
        self.update_sheet(final_df)