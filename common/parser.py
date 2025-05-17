import argparse

def build_parser(parser:argparse.ArgumentParser):
    """
    Build the parser for the command line arguments
        Args:
            parser (argparse.ArgumentParser): The parser object to build
        Returns:
            str: The name of the process to run
            str: The current season to run the process for
            str: The season type to run the process for
    """
    # Add arguments to the parser
    parser.add_argument("process_name", type=str, help="Name of the process to run")
    parser.add_argument("current_season", type=str, help="Current season to run the process for")
    parser.add_argument("season_type", type=str, help="Type of season to run the process for")
    
    # Get the arguments from the parser
    args = parser.parse_args()

    process_name = args.process_name
    current_season = args.current_season
    season_type = args.season_type
    
    return process_name, current_season, season_type