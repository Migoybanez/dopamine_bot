import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# Setup
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
client = gspread.authorize(CREDS)

SHEET_ID = "16jltODL87JrKjoXMbAbYTwhENDyz6Kj-SqSICItZgyc"
worksheet = client.open_by_key(SHEET_ID).sheet1

# Generate TXN_ID
txnid = f"MYDIGITAL-{int(time.time())}"

# Append row
worksheet.append_row([
    txnid,
    "Pending",
    str(datetime.now()),
    "payment initiated"
])

print(f"✅ Transaction {txnid} logged as Pending.")