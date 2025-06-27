import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
client = gspread.authorize(CREDS)

try:
    # Force a call to Drive API to trigger quota setup
    spreadsheet = client.open("Dummy")  # Will fail if no sheet named "Dummy"
except Exception as e:
    print("Drive API triggered (intentionally failed):", e)

try:
    sheets = client.openall()
    print("✅ Sheets your bot can access:")
    for sheet in sheets:
        print("-", sheet.title)
except Exception as e:
    print("❌ Failed to access any sheets:")
    print(e)
