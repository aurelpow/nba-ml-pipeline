import time
import pandas as pd

from nba_api.stats.endpoints import leaguegamelog

from common.singleton_meta import SingletonMeta
from common.io_utils import HistoricTtflMaxFileName, PlayersFileName, load_data, save_database
from common.constants import HISTORIC_TTFL_SEASON_TYPES, nba_api_timeout
from common.raw_columns import (
    assists_col,
    blocks_col,
    fantasy_points_col,
    field_goals_attempted_col,
    field_goals_made_col,
    free_throws_attempted_col,
    free_throws_made_col,
    person_id_col,
    person_id_col_alt,
    player_name_col,
    points_col,
    rebounds_total_col,
    steals_col,
    three_pointers_attempted_col,
    three_pointers_made_col,
    turnovers_col,
)
from common.utils import build_proxy_url, call_nba_api_with_retry
from src.targets.fantasy_points import compute_fantasy_points

# Output columns
season_type_col: str = "season_type"
max_ttfl_col: str = "max_ttfl"
max_ttfl_game_id_col: str = "max_ttfl_game_id"
max_ttfl_game_date_col: str = "max_ttfl_game_date"
max_ttfl_season_col: str = "max_ttfl_season"

# LeagueGameLog (player mode) column -> pipeline column used by compute_fantasy_points
_LOG_TO_BOXSCORE_COLS: dict[str, str] = {
    "PTS": points_col,
    "REB": rebounds_total_col,
    "AST": assists_col,
    "STL": steals_col,
    "BLK": blocks_col,
    "TOV": turnovers_col,
    "FGM": field_goals_made_col,
    "FGA": field_goals_attempted_col,
    "FG3M": three_pointers_made_col,
    "FG3A": three_pointers_attempted_col,
    "FTM": free_throws_made_col,
    "FTA": free_throws_attempted_col,
}


class HistoricTtflMaxCollector(metaclass=SingletonMeta):
    """
    One-shot job: career-high TTFL score per player, split by regular season / playoffs,
    over all seasons *before* the current one (the current season is already in the
    boxscore table). Replaces the Power BI / Power Query loop over stats.nba.com.

    Uses LeagueGameLog (one call returns every player's games for a season), so the cost is
    2 API calls per season. Only players present in the players table are kept.
    Not part of scripts/run_all.sh — run it manually once.
    """

    def __init__(
        self,
        current_season: str,
        save_mode: str,
        proxy_user: str | None = None,
        proxy_pass: str | None = None,
    ) -> None:
        """
        Args:
            current_season (str): format "YYYY-YY"; seasons strictly before it are processed
            save_mode (str): 'local' or 'bq'
            proxy_user (str, optional): Proxy username if needed. Defaults to None.
            proxy_pass (str, optional): Proxy password if needed. Defaults to None.
        """
        self.current_season: str = current_season
        self.current_season_year: int = int(current_season.split("-")[0])
        self.SAVE_MODE: str = save_mode
        self.proxy: str | None = (
            build_proxy_url(proxy_user, proxy_pass)
            if proxy_user and proxy_pass
            else None
        )
        print(f"[PROXY] historic_ttfl_max → {'enabled' if self.proxy else 'disabled (no creds)'}")

    @staticmethod
    def format_season(start_year: int) -> str:
        """2024 -> '2024-25'."""
        return f"{start_year}-{str(start_year + 1)[-2:]}"

    def get_players(self) -> pd.DataFrame:
        """
        Load the players table and keep the columns needed to bound the season range.
        Returns:
            pd.DataFrame: person_id and from_year, one row per player
        """
        players_df: pd.DataFrame = load_data(PlayersFileName, mode=self.SAVE_MODE)
        if players_df is None or players_df.empty:
            raise ValueError(
                "Players table is empty — run get_nba_players before get_historic_ttfl_max."
            )
        return players_df[[person_id_col, "from_year"]].dropna()

    def fetch_season_log(self, season: str, season_type: str) -> pd.DataFrame:
        """
        Fetch every player game log of one season and season type.
        Args:
            season (str): format "YYYY-YY"
            season_type (str): 'Regular Season' or 'Playoffs'
        Returns:
            pd.DataFrame: raw LeagueGameLog rows (empty when the season type did not exist)
        """
        return call_nba_api_with_retry(
            lambda: leaguegamelog.LeagueGameLog(
                season=season,
                season_type_all_star=season_type,
                player_or_team_abbreviation="P",
                counter=0,
                direction="DESC",
                sorter="DATE",
                proxy=self.proxy,
                timeout=nba_api_timeout,
            ).get_data_frames()[0]
        )

    def best_games(
        self, log_df: pd.DataFrame, player_ids: set[int], season: str, season_type: str
    ) -> pd.DataFrame:
        """
        Reduce a season log to each player's best TTFL game.
        Args:
            log_df (pd.DataFrame): raw LeagueGameLog rows
            player_ids (set[int]): players to keep
            season (str): format "YYYY-YY", stored on the result
            season_type (str): stored on the result
        Returns:
            pd.DataFrame: one row per player
        """
        log_df = log_df[log_df["PLAYER_ID"].isin(player_ids)].rename(
            columns=_LOG_TO_BOXSCORE_COLS
        )
        if log_df.empty:
            return pd.DataFrame()

        # Same as the Power Query: stats the NBA did not track (e.g. TOV before 1973) count as 0
        stat_cols: list[str] = list(_LOG_TO_BOXSCORE_COLS.values())
        log_df[stat_cols] = log_df[stat_cols].fillna(0)
        log_df = compute_fantasy_points(log_df)

        best_df: pd.DataFrame = (
            log_df.sort_values([fantasy_points_col, "GAME_DATE"], ascending=[False, True])
            .drop_duplicates("PLAYER_ID")
            .rename(
                columns={
                    "PLAYER_ID": person_id_col_alt,
                    "PLAYER_NAME": player_name_col,
                    "GAME_ID": max_ttfl_game_id_col,
                    "GAME_DATE": max_ttfl_game_date_col,
                    fantasy_points_col: max_ttfl_col,
                }
            )
        )
        best_df[season_type_col] = season_type
        best_df[max_ttfl_season_col] = season
        return best_df[
            [
                person_id_col_alt,
                player_name_col,
                season_type_col,
                max_ttfl_col,
                max_ttfl_game_id_col,
                max_ttfl_game_date_col,
                max_ttfl_season_col,
            ]
        ]

    def compute(self) -> pd.DataFrame:
        """
        Loop over all past seasons and keep the career-high per player and season type.
        Returns:
            pd.DataFrame: one row per (personId, season_type)
        Raises:
            RuntimeError: if any season failed — nothing should be persisted from a partial run
        """
        players_df: pd.DataFrame = self.get_players()
        player_ids: set[int] = set(players_df[person_id_col].astype(int))
        first_year: int = int(players_df["from_year"].astype(int).min())
        last_year: int = self.current_season_year - 1

        print(
            f"Computing max TTFL for {len(player_ids)} players, "
            f"seasons {self.format_season(first_year)} → {self.format_season(last_year)}"
        )

        per_season: list[pd.DataFrame] = []
        failures: list[str] = []
        for year in range(first_year, last_year + 1):
            season: str = self.format_season(year)
            for season_type in HISTORIC_TTFL_SEASON_TYPES:
                try:
                    log_df: pd.DataFrame = self.fetch_season_log(season, season_type)
                except Exception as e:
                    print(f"❌ {season} {season_type}: {e}")
                    failures.append(f"{season} {season_type}")
                    continue
                best_df: pd.DataFrame = self.best_games(
                    log_df, player_ids, season, season_type
                )
                print(f"{season} {season_type}: {len(log_df)} game logs, {len(best_df)} players kept")
                if not best_df.empty:
                    per_season.append(best_df)
                time.sleep(1)  # be gentle with stats.nba.com

        if failures:
            raise RuntimeError(
                f"{len(failures)} season fetch(es) failed, nothing saved: {failures}"
            )
        if not per_season:
            return pd.DataFrame()

        return (
            pd.concat(per_season, ignore_index=True)
            .sort_values(
                [max_ttfl_col, max_ttfl_game_date_col], ascending=[False, True]
            )
            .drop_duplicates([person_id_col_alt, season_type_col])
            .sort_values([person_id_col_alt, season_type_col])
            .reset_index(drop=True)
        )

    def run(self) -> None:
        df: pd.DataFrame = self.compute()
        if df.empty:
            print("⚠️ No historic TTFL data computed. Nothing saved.")
            return
        # Convert to a real date so BigQuery autodetects DATE (the log gives ISO strings)
        df[max_ttfl_game_date_col] = pd.to_datetime(df[max_ttfl_game_date_col]).dt.date
        # WRITE_TRUNCATE (default): re-running simply rebuilds the table
        save_database(df, HistoricTtflMaxFileName, mode=self.SAVE_MODE)
        print(f"✅ Historic TTFL max saved with mode: {self.SAVE_MODE} (rows={len(df)})")
