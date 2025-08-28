"""
This module contains common utility functions for NBA data processing.
"""
import pandas as pd 
import numpy as np 

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