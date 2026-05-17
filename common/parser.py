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
    parser.add_argument("-s", "--season", type=str, default=None, help="Current season to run the process for")
    parser.add_argument("-sm", "--save_mode", type=str, default="bq", choices=["bq", "local"], help="Where to save the output ('bq' or 'local')")
    parser.add_argument("-st","--season_type", type=str, default=None, help="Type of season to run the process for")
    parser.add_argument("-d","--date", type=str, default=None, help="Date to run the process for (optional)")
    parser.add_argument("-m","--model_path", type=str, default=None, help="Path to the model for predictions (optional)")
    parser.add_argument(
        "-dw",
        "--discord_webhook_url",
        type=str,
        default=None,
        help="Discord webhook URL for post_evaluation alerts (optional; falls back to DISCORD_WEBHOOK_URL)",
    )
    parser.add_argument(
        "-t", "--target",
        nargs="+",
        type=lambda s: "fantasy_points" if s in ("fantasy", "fantasy_points") else s,
        default=["points"],
        choices=["points", "fantasy_points"],
        help="Target variable(s) for training (one or more of: 'points', 'fantasy'/'fantasy_points')"
    )
    parser.add_argument("--tune_params", type=str, default="false", choices=["true", "false"], help="Enable hyperparameter tuning during training (true/false)")
    
    # Get the arguments from the parser
    args = parser.parse_args()

    process_name = args.process
    current_season = args.season
    save_mode = args.save_mode
    season_type = args.season_type
    date = args.date
    model_path = args.model_path
    discord_webhook_url = args.discord_webhook_url
    target = args.target
    tune_params = args.tune_params.lower() == "true"
    
    return process_name, current_season, save_mode, season_type, date, model_path, discord_webhook_url, target, tune_params