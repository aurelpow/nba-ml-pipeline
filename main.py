from datetime import datetime
import argparse
import os
import logging
import sys

from src.get_nba_boxscore_basic import BoxscoreGames
from src.get_nba_players import NbaPlayersData
from src.get_nba_teams import NbaTeamsData
from src.get_future_games import NbaGamesLog
from src.get_nba_advanced_boxscore import AdvancedBoxscoreGames
from src.get_predictions_stats_points import PredictionsStatsPoints 
from common.parser import build_parser


def main():
    time_start = datetime.today()

    parser:argparse.ArgumentParser = argparse.ArgumentParser(description="NBA Stats Data Pipeline")

    process_name, current_season,save_mode,season_type, date, days_number, model_path = build_parser(parser)

    valid_processes: list[str] = ["get_nba_players",
                                  "get_nba_teams", 
                                  "get_nba_boxscore_basic", 
                                  "get_future_games", 
                                  "get_nba_advanced_boxscore",
                                  "get_predictions_stats_points"]
    
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
    elif process_name == "get_nba_players":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaPlayersData(current_season=current_season, save_mode=save_mode ).run()

    elif process_name == "get_nba_teams":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaTeamsData(save_mode=save_mode).run()
    
    elif process_name == "get_nba_boxscore_basic":
        print(f"Running process: {process_name} with season: {current_season}")
        BoxscoreGames(current_season).run()

    elif process_name == "get_future_games":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaGamesLog(save_mode=save_mode,date=date,days_number=days_number).run()
    
    elif process_name == "get_nba_advanced_boxscore":
        print(f"Running process: {process_name} with season: {current_season}")
        AdvancedBoxscoreGames(current_season).run()

    elif process_name == "get_predictions_stats_points":
        print(f"Running process: {process_name} with date: {date} and model path:{model_path}")
        PredictionsStatsPoints(date,model_path).run()
        
    # print the time taken to run the process    
    print(f"Process {process_name} completed in {datetime.today() - time_start}.")
    

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