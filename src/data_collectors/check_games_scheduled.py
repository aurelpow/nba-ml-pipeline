import logging
import pandas as pd

from common.io_utils import ScheduleFileName, load_data
from common.raw_columns import game_date_col_alt

logger = logging.getLogger(__name__)


class GamesScheduleChecker:
    """Check whether any games are scheduled for a given date."""

    def __init__(self, date: str, save_mode: str = "bq") -> None:
        """
        Args:
            date: Target date in YYYY-MM-DD format.
            save_mode: 'local' or 'bq'.
        """
        self.date = date
        self.save_mode = save_mode

    def run(self) -> int:
        """
        Load the schedule and count games for self.date.

        Returns:
            Number of games scheduled for self.date (0 = no games).

        Raises:
            ValueError: If the schedule table is empty or missing.
        """
        schedule: pd.DataFrame = load_data(
            FileName=ScheduleFileName,
              mode=self.save_mode)

        if schedule.empty:
            raise ValueError(
                f"Schedule table is empty — cannot determine games for {self.date}."
            )

        games_today: pd.DataFrame = schedule[
            pd.to_datetime(schedule[game_date_col_alt]).dt.strftime("%Y-%m-%d")
            == self.date
        ]

        n = len(games_today)

        if n == 0:
            logger.info(f"No games scheduled for {self.date}.")
        else:
            logger.info(f"{n} game(s) scheduled for {self.date}.")

        return n
