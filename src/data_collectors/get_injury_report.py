"""
Injury Report Collector

Fetches the latest NBA official injury/availability PDF report,
parses it into a structured DataFrame, and persists it to storage.

Output schema:
    report_date   : str  (MM/DD/YYYY)
    matchup       : str  (e.g. "MIL@BOS")
    team          : str  (full CamelCase team name, e.g. "MilwaukeeBucks")
    player_name   : str  (Lastname,Firstname)
    status        : str  (Out | Doubtful | Questionable | Probable | Available)
    reason        : str  (free-text injury description)
"""

import re
import datetime
import logging
import requests
import pdfplumber
import pandas as pd
from io import BytesIO

from common.singleton_meta import SingletonMeta
from common.io_utils import InjuryReportFileName, save_database

logger = logging.getLogger(__name__)

# Hours tried in order from earliest to latest.  The loop stops as soon as a
# URL stops returning HTTP 200, so we always pick the freshest published file.
_HOURS_TO_TRY = [
    "02_00AM",
    "04_00AM",
    "06_00AM",
    "08_00AM",
    "10_00AM",
    "11_00AM",
    "12_00PM",
    "01_00PM",
    "02_00PM",
    "03_00PM",
    "04_00PM",
    "05_00PM",
    "06_00PM",
    "08_00PM",
]

_PDF_BASE_URL = (
    "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date}_{hour}.pdf"
)


class InjuryReportCollector(metaclass=SingletonMeta):
    """
    Fetches and parses the official NBA injury report PDF for a given date,
    then persists the raw structured records to storage.

    Args:
        report_date (str | None): ISO date string "YYYY-MM-DD".
            Defaults to today (UTC).
        save_mode (str): "local" or "bq".
    """

    def __init__(
        self,
        save_mode: str = "local",
        report_date: str | None = None,
    ) -> None:
        self.save_mode = save_mode
        if report_date:
            self.report_date = datetime.datetime.strptime(
                report_date, "%Y-%m-%d"
            ).date()
        else:
            self.report_date = datetime.datetime.utcnow().date()

    # ------------------------------------------------------------------
    # PDF resolution
    # ------------------------------------------------------------------

    def _resolve_pdf_url(self) -> str:
        """
        Try each candidate hour and return the last URL that returned HTTP 200.
        The NBA typically publishes one report per day but updates it during the day.
        """
        date_str = self.report_date.strftime("%Y-%m-%d")
        last_valid: str | None = None

        for hour in _HOURS_TO_TRY:
            url = _PDF_BASE_URL.format(date=date_str, hour=hour)
            try:
                resp = requests.head(url, timeout=10)
                if resp.status_code == 200:
                    last_valid = url
                else:
                    break  # stop at the first hour that has no file yet
            except requests.RequestException as exc:
                logger.debug(f"HEAD request failed for {url}: {exc}")
                break

        if last_valid is None:
            raise FileNotFoundError(
                f"No injury report PDF found for {date_str}. "
                "The report may not yet have been published."
            )
        return last_valid

    # ------------------------------------------------------------------
    # PDF parsing
    # ------------------------------------------------------------------

    def _parse_pdf(self, pdf_url: str) -> pd.DataFrame:
        """Download and parse the PDF into a list of injury records.

        Real NBA injury-report PDFs have an unusual flat-text structure:
        - Date, time, matchup, team name, player name, status, and reason can
          all appear on a single line.
        - Team names are CamelCase with no spaces (e.g. "MilwaukeeBucks").
        - Multi-line injury reasons are very common.
        - Page headers ("Injury Report: …") and footers ("Page1of11") must be
          stripped before any other processing.
        - Teams that haven't filed appear as "TeamName NOTYETSUBMITTED".
        """
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
        pdf_content = BytesIO(response.content)

        today_str = self.report_date.strftime("%m/%d/%Y")

        # ------------------------------------------------------------------
        # Compiled patterns
        # ------------------------------------------------------------------

        # Full date+time+matchup line, e.g.:
        #   "03/30/2025 03:30(ET) LAC@CLE LAClippers BaldwinJr.,Patrick Out ..."
        date_matchup_pat = re.compile(
            r"^(\d{2}/\d{2}/\d{4})\s+\d{1,2}:\d{2}\(ET\)\s+([A-Z]{2,4}@[A-Z]{2,4})"
        )

        # Time-only+matchup line (same day, new game), e.g.:
        #   "06:00(ET) POR@NYK PortlandTrailBlazers Ayton,Deandre Out ..."
        time_matchup_pat = re.compile(r"^\d{1,2}:\d{2}\(ET\)\s+([A-Z]{2,4}@[A-Z]{2,4})")

        # Bare matchup line — no date or time prefix, appears after page breaks
        # when pdfplumber merges the time token into the previous page's last line.
        # e.g. "PHX@CHA PhoenixSuns Coffey,Amir Out ..."
        #      "MIN@PHI MinnesotaTimberwolves NOTYETSUBMITTED"
        bare_matchup_pat = re.compile(r"^([A-Z]{2,4}@[A-Z]{2,4})(?:\s|$)")

        # CamelCase team name token: alphabetic, length > 5, mixed case.
        # Examples: "LAClippers", "ClevelandCavaliers", "PortlandTrailBlazers",
        #           "OKCThunder", "MilwaukeeBucks"
        # NOTE: we also require the NEXT token to be a player or NOTYETSUBMITTED
        # so that single-word reason continuations ("Management", "Tendinopathy")
        # are not misidentified as team names.

        # Player token: "Lastname,Firstname" or "LastnameJr.,Firstname" etc.
        player_pat = re.compile(r"^[^,\s]+,[^\s]+$")

        # Lines to strip entirely
        skip_pat = re.compile(r"^(Injury Report:|GameDate\s+GameTime|Page\d+of\d+$)")

        # ------------------------------------------------------------------
        # Helpers
        # ------------------------------------------------------------------

        def _is_player(token: str) -> bool:
            return bool(player_pat.match(token))

        def _looks_like_team_token(token: str) -> bool:
            """True for mixed-case team name tokens (alphanumeric, length > 5, mixed case).
            Handles teams with digits in the name e.g. 'Philadelphia76ers'.
            """
            return (
                bool(re.match(r"^[A-Za-z0-9]+$", token))
                and len(token) > 5
                and any(c.isupper() for c in token)
                and any(c.islower() for c in token)
            )

        def _is_team_line_start(parts: list[str]) -> bool:
            """
            A line starts with a team token if:
              - parts[0] looks like a team token, AND
              - parts[1] is a player token OR 'NOTYETSUBMITTED'
            This lookahead prevents single-word reasons ('Management') from
            being mistaken for team names.
            """
            if len(parts) < 2:
                return False
            if not _looks_like_team_token(parts[0]):
                return False
            return _is_player(parts[1]) or parts[1] == "NOTYETSUBMITTED"

        def _consume_matchup_line(parts: list[str], matchup: str) -> None:
            """
            After extracting the matchup token from *parts*, pull out the
            optional CamelCase team and optional player+status+reason that
            may follow on the same line.
            """
            nonlocal current_matchup, current_team, current_record
            current_matchup = matchup

            # Find position of the matchup token and advance past it
            # (parts may still contain the time/date tokens at index 0,1 …)
            for i, p in enumerate(parts):
                if p == matchup:
                    remaining = parts[i + 1 :]
                    break
            else:
                remaining = []

            # Optional team name immediately after matchup token
            if remaining and _looks_like_team_token(remaining[0]):
                current_team = remaining[0]
                remaining = remaining[1:]

            # Optional "NOTYETSUBMITTED" — no player data
            if remaining and remaining[0] == "NOTYETSUBMITTED":
                return

            # Optional player record on the same line
            if remaining and _is_player(remaining[0]):
                current_record = _make_record(remaining)
                if current_record:
                    records.append(current_record)

        def _make_record(parts: list[str]) -> dict | None:
            if len(parts) < 2:
                return None
            return {
                "report_date": date_part,
                "matchup": current_matchup or "",
                "team": current_team or "",
                "player_name": parts[0],
                "status": parts[1],
                "reason": " ".join(parts[2:]) if len(parts) > 2 else "",
            }

        # ------------------------------------------------------------------
        # Main parse loop
        # ------------------------------------------------------------------

        records: list[dict] = []
        current_matchup: str | None = None
        current_team: str | None = None
        current_record: dict | None = None
        date_part: str = today_str

        with pdfplumber.open(pdf_content) as pdf:
            for page in pdf.pages:
                raw_text = page.extract_text()
                if not raw_text:
                    continue

                for line in raw_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue

                    # 1. Strip header / footer lines unconditionally
                    if skip_pat.match(line):
                        continue

                    parts = line.split()

                    # 2. Date + matchup line
                    #    "MM/DD/YYYY HH:MM(ET) LAC@CLE ..."
                    m = date_matchup_pat.match(line)
                    if m:
                        date_part = m.group(1)
                        matchup_token = m.group(2)
                        # Skip records for dates other than today
                        if date_part != today_str:
                            # Still parse — multi-day reports include next-day
                            # games; we keep them but tag with their own date.
                            pass
                        _consume_matchup_line(parts, matchup_token)
                        continue

                    # 3. Time-only + matchup line (same date, new game)
                    #    "06:00(ET) POR@NYK PortlandTrailBlazers ..."
                    m = time_matchup_pat.match(line)
                    if m:
                        matchup_token = m.group(1)
                        _consume_matchup_line(parts, matchup_token)
                        continue

                    # 3b. Bare matchup line — no date/time prefix (page-break artifact)
                    #     "PHX@CHA PhoenixSuns Coffey,Amir Out ..."
                    #     "MIN@PHI MinnesotaTimberwolves NOTYETSUBMITTED"
                    m = bare_matchup_pat.match(line)
                    if m:
                        matchup_token = m.group(1)
                        _consume_matchup_line(parts, matchup_token)
                        continue

                    # We need an active matchup context from here on
                    if current_matchup is None:
                        continue

                    # 4. Team name line (possibly followed by player or NOTYETSUBMITTED)
                    #    "ClevelandCavaliers Bates,Emoni Out GLeague-Two-Way"
                    #    "CharlotteHornets NOTYETSUBMITTED"
                    if _is_team_line_start(parts):
                        current_team = parts[0]
                        remaining = parts[1:]

                        if not remaining or remaining[0] == "NOTYETSUBMITTED":
                            current_record = None
                            continue

                        if _is_player(remaining[0]):
                            current_record = _make_record(remaining)
                            if current_record:
                                records.append(current_record)
                        # else: unexpected token after team name — treat as
                        # continuation of previous reason (should not happen)
                        continue

                    # 5. Player line: "Lastname,Firstname Status [Reason...]"
                    if _is_player(parts[0]):
                        current_record = _make_record(parts)
                        if current_record:
                            records.append(current_record)
                        continue

                    # 6. Continuation: append to most-recent player's reason
                    if records:
                        records[-1]["reason"] = (
                            records[-1]["reason"] + " " + line
                        ).strip()
                        # Keep current_record in sync
                        if current_record is not None:
                            current_record["reason"] = records[-1]["reason"]

        return (
            pd.DataFrame(records)
            if records
            else pd.DataFrame(
                columns=[
                    "report_date",
                    "matchup",
                    "team",
                    "player_name",
                    "status",
                    "reason",
                ]
            )
        )

    def run(self) -> pd.DataFrame:
        """Fetch → parse → persist. Returns the raw injury report DataFrame."""
        logger.info(f"Fetching injury report for {self.report_date} …")
        pdf_url = self._resolve_pdf_url()
        logger.info(f"Latest PDF URL: {pdf_url}")

        df = self._parse_pdf(pdf_url)
        if df.empty:
            logger.warning("No injury records parsed — nothing to save.")
            return df

        save_database(
            df,
            InjuryReportFileName,
            mode=self.save_mode,
            write_disposition="WRITE_TRUNCATE",
        )
        logger.info(f"Injury report saved ({len(df)} rows) via mode={self.save_mode}")
        return df
