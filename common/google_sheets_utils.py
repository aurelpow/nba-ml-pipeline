import gspread
from google.oauth2.service_account import Credentials


def connect_to_sheet(sheet_url, worksheet_title):
    """Connect to a specific worksheet in the Google Sheet."""
    SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(sheet_url)
    return spreadsheet.worksheet(worksheet_title)


def update_sheet(worksheet, data):
    """
    Update the worksheet with new data.
    Clears existing data and writes headers + rows.
    """
    worksheet.clear()  # Clear existing content

    # Write new data
    if len(data) > 0:
        worksheet.append_rows(data, value_input_option="RAW")  # Insert rows
    print(f"Updated {worksheet.title} successfully!")