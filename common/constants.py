"""
This module contains common utility constants for NBA data processing.
"""

# Nba api timeout
nba_api_timeout: int = 20 
# Number of retries for nba api requests
max_retries: int = 3
# Delay between retries in seconds
retry_delay: int = 5