"""
Injury Status Normalizer
========================
Converts the raw status strings found in the official NBA injury report PDF into
a canonical five-level scale and assigns each player a *play probability* for
their next scheduled game.

Canonical statuses (from most to least certain to sit out):
    Out          → 0.02   (near-certain DNP)
    Doubtful     → 0.15   (very unlikely to play)
    Questionable → 0.50   (coin-flip)
    Probable     → 0.85   (very likely to play)
    Available    → 0.97   (essentially certain to play)

Any raw string that cannot be mapped defaults to "Questionable" / 0.50.

Public API
----------
    normalize_status(raw_status: str) -> str
    play_probability(canonical_status: str) -> float
    normalize_report(df: pd.DataFrame) -> pd.DataFrame
"""

import re
import pandas as pd
from common.constants import (
    AVAILABILITY_STATUS_MAP,
    AVAILABILITY_PLAY_PROBABILITY,
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def normalize_status(raw_status: str) -> str:
    """
    Map a raw PDF status string to one of the five canonical statuses.

    The mapping is fuzzy: it first tries an exact lookup (case-insensitive),
    then falls back to substring / regex matching defined in
    ``AVAILABILITY_STATUS_MAP``.

    Args:
        raw_status: Raw string as parsed from the PDF (e.g. "OUT", "GTD",
                    "QUESTIONABLE", "DNP – rest", …).

    Returns:
        One of: "Out", "Doubtful", "Questionable", "Probable", "Available".
    """
    if not isinstance(raw_status, str) or not raw_status.strip():
        return "Questionable"

    cleaned = raw_status.strip().upper()

    # Direct key lookup first (fastest path)
    if cleaned in AVAILABILITY_STATUS_MAP:
        return AVAILABILITY_STATUS_MAP[cleaned]

    # Substring / pattern matching
    for pattern, canonical in AVAILABILITY_STATUS_MAP.items():
        if re.search(pattern, cleaned):
            return canonical

    return "Questionable"


def play_probability(canonical_status: str) -> float:
    """
    Return the prior probability that a player with *canonical_status* will
    play in their next game.

    Args:
        canonical_status: One of the five canonical status strings.

    Returns:
        Float in [0, 1].
    """
    return AVAILABILITY_PLAY_PROBABILITY.get(canonical_status, 0.50)


# ---------------------------------------------------------------------------
# DataFrame-level transform
# ---------------------------------------------------------------------------


def normalize_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply status normalization and play-probability assignment to a raw
    injury report DataFrame produced by ``InjuryReportCollector``.

    Input columns expected:
        report_date, matchup, team, player_name, status, reason

    Added / modified columns:
        status          → overwritten with canonical value
        raw_status      → original value preserved here
        play_probability → float [0,1]

    Args:
        df: Raw injury report DataFrame.

    Returns:
        Enriched DataFrame with canonical status + play probability columns.
    """
    if df.empty:
        return df.copy()

    out = df.copy()

    # Preserve original string
    out["raw_status"] = out["status"].astype(str)

    # Canonical status
    out["status"] = out["raw_status"].apply(normalize_status)

    # Play probability
    out["play_probability"] = out["status"].apply(play_probability)

    return out
