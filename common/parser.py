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
    parser.add_argument("-p", "--process", type=str, required=True, help="Name of the process to run")
    parser.add_argument("-s", "--season", type=str, required=True, help="Current season to run the process for")
    parser.add_argument("-sm", "--save_mode", type=str, default="bq", choices=["bq", "local"], help="Where to save the output ('bq' or 'local')")
    parser.add_argument("-st","--season_type", type=str, default=None, help="Type of season to run the process for")
    parser.add_argument("-d","--date", type=str, default=None, help="Date to run the process for (optional)")
    parser.add_argument("-dn","--days_number", type=int, default=None, help="Number of days to run the process for (optional)")
    parser.add_argument("-m","--model_path", type=str, default=None, help="Path to the model for predictions (optional)")


    
    # Get the arguments from the parser
    args = parser.parse_args()

    process_name = args.process
    current_season = args.season
    save_mode = args.save_mode
    season_type = args.season_type
    date = args.date
    days_number = args.days_number
    model_path = args.model_path 
    
    return process_name, current_season, save_mode, season_type, date, days_number, model_path