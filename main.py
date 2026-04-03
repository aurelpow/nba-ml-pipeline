from datetime import datetime
import argparse
import os
import sys
import logging
from io import TextIOWrapper

# Force UTF-8 stdout/stderr on Windows so emoji in print() don't crash.
def _force_utf8_stream(stream: object) -> None:
    if not isinstance(stream, TextIOWrapper):
        return

    encoding = stream.encoding or ""
    if encoding.lower() not in ("utf-8", "utf8"):
        stream.reconfigure(encoding="utf-8", errors="replace")


_force_utf8_stream(sys.stdout)
_force_utf8_stream(sys.stderr)

from src.data_collectors.get_nba_boxscore_basic import BoxscoreGames
from src.data_collectors.get_nba_players import NbaPlayersData
from src.data_collectors.get_nba_teams import NbaTeamsData
from src.data_collectors.get_nba_schedule import ScheduleData
from src.data_collectors.get_nba_advanced_boxscore import AdvancedBoxscoreGames
from src.data_collectors.get_injury_report import InjuryReportCollector
from src.availability.availability_table import AvailabilityTableBuilder
from src.predictors.unified_predictor import UnifiedPredictor
from src.training.train import UnifiedModelTrainer
from common.parser import build_parser


def main():
    time_start = datetime.today()

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="NBA Stats Data Pipeline"
    )

    (
        process_name,
        current_season,
        save_mode,
        season_type,
        date,
        model_path,
        target,
        tune_params,
    ) = build_parser(parser)

    valid_processes: list[str] = [
        "get_nba_players",
        "get_nba_teams",
        "get_nba_schedule",
        "get_nba_boxscore_basic",
        "get_nba_advanced_boxscore",
        "get_injury_report",
        "compute_availability",
        "train",
        "get_predictions_stats_points",
        "get_predictions_fantasy_points",
    ]

    # Strip whitespace and check for validity
    process_name = process_name.strip()

    # Check if the process name is valid
    if process_name not in valid_processes:
        logging.error(
            f"Invalid process name: {process_name}. Valid processes are: {valid_processes}"
        )
        raise Exception(
            f"Invalid process name: {process_name}. Valid processes are: {valid_processes}"
        )

    # Execute the process
    elif process_name == "get_nba_players":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaPlayersData(
            current_season=current_season,
            save_mode=save_mode,
            proxy_user=os.getenv("NBA_PROXY_USER"),
            proxy_pass=os.getenv("NBA_PROXY_PASS"),
        ).run()

    elif process_name == "get_nba_teams":
        print(f"Running process: {process_name} with season: {current_season}")
        NbaTeamsData(save_mode=save_mode).run()

    elif process_name == "get_nba_boxscore_basic":
        print(f"Running process: {process_name} with season: {current_season}")
        BoxscoreGames(
            current_season,
            save_mode=save_mode,
            proxy_user=os.getenv("NBA_PROXY_USER"),
            proxy_pass=os.getenv("NBA_PROXY_PASS"),
        ).run()
    elif process_name == "get_nba_schedule":
        print(f"Running process: {process_name} with season: {current_season}")
        ScheduleData(
            current_season=current_season,
            save_mode=save_mode,
            proxy_user=os.getenv("NBA_PROXY_USER"),
            proxy_pass=os.getenv("NBA_PROXY_PASS"),
        ).run()

    elif process_name == "get_nba_advanced_boxscore":
        print(f"Running process: {process_name} with season: {current_season}")
        AdvancedBoxscoreGames(
            current_season,
            save_mode=save_mode,
            proxy_user=os.getenv("NBA_PROXY_USER"),
            proxy_pass=os.getenv("NBA_PROXY_PASS"),
        ).run()

    elif process_name == "get_injury_report":
        print(f"Running process: {process_name} with date: {date}")
        InjuryReportCollector(
            save_mode=save_mode,
            report_date=date,
        ).run()

    elif process_name == "compute_availability":
        print(f"Running process: {process_name} with date: {date}")
        AvailabilityTableBuilder(
            save_mode=save_mode,
            report_date=date,
        ).run()

    elif process_name == "train":
        for tgt in target:
            print(
                f"Running process: {process_name} for target: {tgt} (tune_params={tune_params})"
            )
            UnifiedModelTrainer(
                target=tgt, model_path=model_path, save_mode=save_mode
            ).run(tune_params=tune_params)

    elif process_name == "get_predictions_stats_points":
        print(
            f"Running process: {process_name} with date: {date} and model path:{model_path}"
        )
        UnifiedPredictor(
            target="points", save_mode=save_mode, date=date, model_path=model_path
        ).run()

    elif process_name == "get_predictions_fantasy_points":
        print(
            f"Running process: {process_name} with date: {date} and model path:{model_path}"
        )
        UnifiedPredictor(
            target="fantasy_points",
            save_mode=save_mode,
            date=date,
            model_path=model_path,
        ).run()

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
        logging.error(e, exc_info=True)
        sys.exit(1)
