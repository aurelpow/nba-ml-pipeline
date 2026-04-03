"""
Availability Table Builder
==========================
Combines the raw injury report with the NBA players roster to produce the
clean, downstream-ready **player availability table** consumed by the win-
probability, player-props, and team-strength models.

Output schema (one row per player per game date):
    game_date        : date
    matchup          : str   (e.g. "MIL@BOS")
    team             : str   (team abbreviation from injury report)
    team_id          : int   (NBA team ID, joined from players table)
    person_id        : int   (NBA player ID, joined from players table)
    player_slug      : str
    player_name_raw  : str   (Lastname,Firstname as in the PDF)
    raw_status       : str   (original PDF string)
    status           : str   (canonical: Out|Doubtful|Questionable|Probable|Available)
    reason           : str   (injury description)
    play_probability : float (prior probability the player will play)
    is_available     : bool  (True when play_probability >= threshold)

Players NOT listed in the injury report are assumed fully Available (prob=0.97).

Public API
----------
    AvailabilityTableBuilder(save_mode, report_date, availability_threshold)
    .run() -> pd.DataFrame
"""

import re
import logging
import datetime
import pandas as pd

from common.singleton_meta import SingletonMeta
from common.io_utils import (
    InjuryReportFileName,
    AvailabilityFileName,
    PlayersFileName,
    load_data,
    save_database,
)
from common.constants import (
    AVAILABILITY_PLAY_PROBABILITY,
    AVAILABILITY_DEFAULT_THRESHOLD,
)
from src.availability.injury_normalizer import normalize_report

logger = logging.getLogger(__name__)


class AvailabilityTableBuilder(metaclass=SingletonMeta):
    """
    Reads the stored injury report + the players roster, enriches with
    play-probability scores, and saves the final availability table.

    Args:
        save_mode  (str):   "local" or "bq".
        report_date (str):  ISO date "YYYY-MM-DD" (defaults to today UTC).
        availability_threshold (float): Minimum play_probability to mark a
            player as is_available=True (default from constants).
    """

    def __init__(
        self,
        save_mode: str = "local",
        report_date: str | None = None,
        availability_threshold: float | None = None,
    ) -> None:
        self.save_mode = save_mode
        if report_date:
            self.report_date = datetime.datetime.strptime(
                report_date, "%Y-%m-%d"
            ).date()
        else:
            self.report_date = datetime.datetime.utcnow().date()

        self.threshold = (
            availability_threshold
            if availability_threshold is not None
            else AVAILABILITY_DEFAULT_THRESHOLD
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """
        Full pipeline: load → enrich → save.

        Returns:
            Availability DataFrame ready for downstream consumption.
        """
        logger.info(f"Building availability table for {self.report_date} …")

        injury_df = load_data(InjuryReportFileName, mode=self.save_mode)
        players_df = load_data(PlayersFileName, mode=self.save_mode)

        availability_df = self._build(injury_df, players_df)

        if availability_df.empty:
            logger.warning("Availability table is empty — nothing to save.")
            return availability_df

        save_database(
            availability_df,
            AvailabilityFileName,
            mode=self.save_mode,
            write_disposition="WRITE_TRUNCATE",
        )
        logger.info(
            f"Availability table saved ({len(availability_df)} rows) "
            f"via mode={self.save_mode}"
        )
        return availability_df

    # ------------------------------------------------------------------
    # Core build logic
    # ------------------------------------------------------------------

    def _build(
        self,
        injury_df: pd.DataFrame,
        players_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Join injury report with players roster, fill missing players as
        Available, and produce the final table.
        """
        if players_df.empty:
            logger.error(
                "Players DataFrame is empty — cannot build availability table."
            )
            return pd.DataFrame()

        # ---- 1. Normalise the raw injury report ----
        if injury_df.empty:
            logger.warning(
                "Injury report is empty — treating all players as Available."
            )
            normalized_injury = pd.DataFrame()
        else:
            normalized_injury = normalize_report(injury_df)

        # ---- 2. Prepare players lookup ----
        # Standardise column names from nba_players_df (lowercase from get_nba_players)
        players_lookup = (
            players_df[
                [
                    "person_id",
                    "player_slug",
                    "team_id",
                    "team_abbreviation",
                    "player_last_name",
                    "player_first_name",
                ]
            ]
            .drop_duplicates(subset=["person_id"])
            .copy()
        )

        # Build "Lastname,Firstname" key to match the PDF format
        players_lookup["player_name_key"] = (
            players_lookup["player_last_name"].str.strip().str.upper()
            + ","
            + players_lookup["player_first_name"].str.strip().str.upper()
        )

        # ---- 3. Merge injury records onto players ----
        if not normalized_injury.empty:
            # Upper-case the name key in injury data for joining.
            # The NBA PDF compresses suffixes: "PorterJr." instead of "Porter Jr.",
            # "WilliamsIII" instead of "Williams III", etc.  Insert the missing
            # space so the key matches the players table's "PORTER JR.,KEVIN" form.
            _suffix_pat = re.compile(r"([A-Za-z])(Jr\.|Sr\.|II|III|IV)(?=,)")
            normalized_injury["player_name_key"] = (
                normalized_injury["player_name"]
                .str.strip()
                .apply(lambda n: _suffix_pat.sub(r"\1 \2", n))
                .str.upper()
            )

            injured_merged = players_lookup.merge(
                normalized_injury[
                    [
                        "report_date",
                        "matchup",
                        "team",
                        "player_name_key",
                        "player_name",
                        "raw_status",
                        "status",
                        "reason",
                        "play_probability",
                    ]
                ],
                on="player_name_key",
                how="inner",
            )

            # Warn about injury-report players that have no roster entry
            matched_keys = set(injured_merged["player_name_key"])
            unmatched = normalized_injury[
                ~normalized_injury["player_name_key"].isin(matched_keys)
            ]
            if not unmatched.empty:
                names = unmatched["player_name"].tolist()
                logger.warning(
                    "%d player(s) in the injury report have no roster entry "
                    "(G-League / two-way / not yet rostered) — skipped: %s",
                    len(names),
                    ", ".join(names),
                )
        else:
            injured_merged = pd.DataFrame()

        # ---- 4. Build the "all players" baseline — every player is Available ----
        default_prob = AVAILABILITY_PLAY_PROBABILITY["Available"]
        all_players_base = players_lookup.copy()
        all_players_base["report_date"] = self.report_date.strftime("%m/%d/%Y")
        all_players_base["matchup"] = ""
        all_players_base["team"] = all_players_base["team_abbreviation"]
        all_players_base["player_name"] = all_players_base["player_name_key"]
        all_players_base["raw_status"] = "Available"
        all_players_base["status"] = "Available"
        all_players_base["reason"] = ""
        all_players_base["play_probability"] = default_prob

        # ---- 5. Override baseline with injury records ----
        if not injured_merged.empty:
            # Players that appear in the injury report
            injured_person_ids = set(injured_merged["person_id"].unique())

            # Keep baseline only for players NOT in the injury report
            clean_players = all_players_base[
                ~all_players_base["person_id"].isin(injured_person_ids)
            ]

            combined = pd.concat(
                [injured_merged, clean_players],
                ignore_index=True,
            )
        else:
            combined = all_players_base

        # ---- 6. Final column selection + is_available flag ----
        combined["game_date"] = pd.to_datetime(self.report_date)
        combined["is_available"] = combined["play_probability"] >= self.threshold

        output_cols = [
            "game_date",
            "matchup",
            "team",
            "team_id",
            "person_id",
            "player_slug",
            "player_name",
            "raw_status",
            "status",
            "reason",
            "play_probability",
            "is_available",
        ]

        # Keep only columns that exist
        output_cols = [c for c in output_cols if c in combined.columns]
        result = combined[output_cols].reset_index(drop=True)

        logger.info(
            f"Availability summary — "
            f"Available: {result['is_available'].sum()} | "
            f"Unavailable: {(~result['is_available']).sum()} | "
            f"Total: {len(result)}"
        )
        return result
