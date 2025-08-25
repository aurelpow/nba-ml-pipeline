""
"This module contains common utility functions and constants for NBA data processing."

# Nba api timeout
nba_api_timeout: int = 20 
# Number of retries for nba api requests
max_retries: int = 3
# Delay between retries in seconds
retry_delay: int = 5
nba_api_header_user_agent: dict = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}