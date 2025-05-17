from datetime import datetime
import argparse
import os
import logging
import sys

from src.get_nba_boxscore_basic import BoxscoreGames
from src.get_nba_players import NbaPlayersData as NbaPlayersData_1
from src.get_nba_players_endpoints import NbaPlayersData
from src.get_nba_teams import NbaTeamsData

from common.confidentials import sheet_url
from common.parser import build_parser


def main():
    time_start = datetime.today()

    parser:argparse.ArgumentParser = argparse.ArgumentParser(description="NBA Stats Data Pipeline")

    process_name, current_season, season_type = build_parser(parser)

    valid_processes: list[str] = ["get_nba_players","get_nba_players_endpoints", "get_nba_teams", "get_nba_boxscore_basic"]
    
    # Debugging: Print received process_name and valid processes
    print(f"Received process_name: {process_name}")
    print(f"Valid processes: {valid_processes}")

    # Strip whitespace and check for validity
    process_name = process_name.strip()
        
    # Check if the process name is valid
    if process_name not in valid_processes:
        logging.error(f"Invalid process name: {process_name}. Valid processes are: {valid_processes}")
        raise Exception(f"Invalid process name: {process_name}. Valid processes are: {valid_processes}")

    # Execute the process
    if process_name == "get_nba_players":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaPlayersData_1(current_season).run()

    # Execute the process
    if process_name == "get_nba_players_endpoints":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaPlayersData().run()

    elif process_name == "get_nba_teams":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaTeamsData(current_season).run()
    
    elif process_name == "get_nba_boxscore_basic":
        print(f"Running process: {process_name} with season: {current_season}")
        BoxscoreGames(current_season, season_type).run()

    logging.info(f"Process {process_name} completed in {datetime.today() - time_start}.")
    

if __name__ == "__main__":
    """
    Run the main function
    """
    try:
        main()
    except Exception as e:
        logging.error("Failed to execute the process")
        logging.error(e,exc_info=True)
        sys.exit(1)