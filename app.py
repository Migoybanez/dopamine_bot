from flask import Flask, redirect, request
import base64
import json
import requests
import time
from datetime import datetime

# ✅ Google Sheets Setup
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
CREDS = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
client = gspread.authorize(CREDS)
SHEET_ID = "16jltODL87JrKjoXMbAbYTwhENDyz6Kj-SqSICItZgyc"
worksheet = client.open_by_key(SHEET_ID).sheet1

# ✅ Flask app
app = Flask(__name__)

@app.route('/create-payment')
def create_payment():
    merchant_id = "MYDIGITAL"
    password = "1a0b9ebe8be7d24fa57cae4bb4a9234c8aef50e9"
    transaction_id = f"{merchant_id}-{int(time.time() * 1000)}"

    endpoint = f"https://test.dragonpay.ph/api/collect/v1/{transaction_id}/post"

    payload = {
        "TransactionId": transaction_id,
        "Amount": "100.00",
        "Currency": "PHP",
        "Description": "Test GCash Payment",
        "Email": "migo.ybanez@gmail.com"
    }

    auth_string = f"{merchant_id}:{password}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_auth}"
    }

    print("[DEBUG] Generated Transaction ID:", transaction_id)

    response = requests.post(endpoint, headers=headers, data=json.dumps(payload))

    try:
        result = response.json()
    except ValueError:
        print("[ERROR] Response was not JSON:", response.text)
        return "Failed to parse Dragonpay response."

    print("[DEBUG] API Response:", result)

    worksheet.append_row([
        transaction_id,
        "Pending",
        str(datetime.now()),
        "payment initiated"
    ])
    print(f"✅ Transaction {transaction_id} logged as Pending.")

    if result.get("Status") == "S":
        return redirect(result.get("Url"))
    else:
        return f"❌ Error: {result.get('Message', 'Unknown error')}"

@app.route('/thank-you')
def thank_you():
    return "✅ Payment complete. This is the Return URL page."

@app.route('/postback', methods=['POST'])
def handle_postback():
    data = request.form.to_dict()
    print("📦 Received Dragonpay POSTBACK:", data)

    txnid = data.get("txnid")
    status = data.get("status")
    
    # Map Dragonpay status codes to readable names
    status_mapping = {
        'P': 'Pending',
        'V': 'Validate', 
        'S': 'Successful',
        'F': 'Failed',
        'U': 'Unknown'
    }
    readable_status = status_mapping.get(status, status)

    if not txnid:
        return "Missing txnid", 400

    try:
        cell = worksheet.find(txnid)
        row = cell.row
        
        # Update multiple cells at once using batch_update
        updates = [
            {'range': f'B{row}', 'values': [[readable_status]]},
            {'range': f'C{row}', 'values': [[str(datetime.now())]]},
            {'range': f'D{row}', 'values': [['postback']]}
        ]
        
        worksheet.batch_update(updates)
        print(f"✅ Updated TXN {txnid} to {readable_status}")
        return "OK", 200
    except Exception as e:
        print(f"❌ Failed to update sheet: {e}")
        return "Update failed", 500

# ✅ Run the app
if __name__ == '__main__':
    app.run(port=3000, debug=True)
