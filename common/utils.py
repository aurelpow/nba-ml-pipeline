"""
This module contains common utility functions for NBA data processing.
"""
import time
import logging
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import quote

logger = logging.getLogger(__name__)

PROXY_HOST = "gate.decodo.com:10001"

# Transient HTTP status codes that warrant a retry
_RETRY_STATUS = frozenset([500, 502, 503, 504, 522, 524])


def build_proxy_url(proxy_user: str, proxy_pass: str) -> str | None:
    """
    Build a URL-encoded proxy string from credentials.
    Returns None when either credential is missing.
    """
    if not proxy_user or not proxy_pass:
        return None
    return f"http://{quote(proxy_user, safe='')}:{quote(proxy_pass, safe='')}@{PROXY_HOST}"


def get_retry_session(proxy_url: str | None = None) -> requests.Session:
    """
    Return a requests.Session pre-configured with:
    - exponential backoff retry (3 attempts, 2-4-8 s)
    - retries on 5xx / 522 / 524 status codes
    - optional proxy routing
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,           # waits 2 s, 4 s, 8 s between retries
        status_forcelist=list(_RETRY_STATUS),
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}
    return session


def call_nba_api_with_retry(fn, *args, max_retries: int = 3, backoff: float = 2.0, **kwargs):
    """
    Call any zero-argument callable (or callable fn(*args, **kwargs)) that
    wraps an nba_api endpoint, retrying on transient ProxyError / timeout.

    Usage:
        df = call_nba_api_with_retry(
                lambda: SomeEndpoint(param=value, proxy=proxy_url, timeout=60)
                        .get_data_frames()[0]
             )
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            # Only retry on transient network / proxy errors
            transient = any(kw in err_str for kw in (
                "522", "524", "ProxyError", "ReadTimeoutError",
                "ConnectionError", "RemoteDisconnected", "Read timed out",
            ))
            if not transient or attempt == max_retries:
                logger.error("[retry] Non-retryable or max retries reached: %s", exc)
                raise
            wait = backoff ** attempt
            logger.warning("[retry] Attempt %d/%d failed (%s). Retrying in %.0fs...",
                           attempt, max_retries, exc.__class__.__name__, wait)
            time.sleep(wait)
    raise last_exc  # unreachable, satisfies type checkers

# Function to extract season from game_id
def extract_season(game_id):
    """
    Extract the season year from a given game_id.
    Args:
        game_id (str or int): The game ID from which to extract the season.
        Returns:
        int: The extracted season year (e.g., 2023 for the 2023-24 season).
    """
    try:
        if pd.isnull(game_id):
            return np.nan
        if len(str(game_id)) == 8:
            gid = str(game_id)[1:3]
            return int(gid) + 2000
        
        if game_id.startswith('00'):
            gid = game_id[3:5]
            return int(gid) + 2000
    except Exception:
        return np.nan

# Function to transform minutes from string to float
def parse_minutes(val):
    """
    Convert 'MM:SS' or 'H:MM:SS' to minutes (float).
    Args:
        val (str or float): The minutes string or numeric value.    
        Returns:
            float: The total minutes as a float.
    """
    if pd.isna(val) or val == '':
        return 0.0
    try:
        parts = str(val).split(':')
        if len(parts) == 2:  # MM:SS
            m, s = map(int, parts)
            return m + s / 60
        elif len(parts) == 3:  # H:MM:SS
            h, m, s = map(int, parts)
            return h * 60 + m + s / 60
        else:
            return float(val)  # already numeric
    except Exception:
        return 0.0  # fallback if unexpected format