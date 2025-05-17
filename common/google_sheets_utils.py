import gspread
from google.oauth2.service_account import Credentials


def connect_to_sheet(sheet_url, worksheet_title, credentials_file):
    """
    Connect to a specific worksheet in the Google Sheet.

    Args:
        sheet_url (str): The URL of the Google Sheet.
        worksheet_title (str): The title of the worksheet to connect to.

    Returns:
        gspread.models.Worksheet: The worksheet object from the Google Sheet.

    Raises:
        gspread.exceptions.SpreadsheetNotFound: If the spreadsheet is not found.
        gspread.exceptions.WorksheetNotFound: If the worksheet is not found.
        google.auth.exceptions.GoogleAuthError: If there is an issue with Google authentication.
    """
    SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    except FileNotFoundError:
        raise FileNotFoundError("The 'credentials.json' file was not found. Please ensure it exists and is correctly configured.")
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(sheet_url)
    return spreadsheet.worksheet(worksheet_title)