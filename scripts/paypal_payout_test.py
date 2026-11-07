"""Day 1 check: can our PayPal sandbox app send a payout to a supplier?

Run:  python paypal_payout_test.py
Needs PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET and TEST_SUPPLIER_EMAIL in .env
"""
import os
import sys
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"
CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
SUPPLIER = os.getenv("TEST_SUPPLIER_EMAIL")

if not (CLIENT_ID and SECRET and SUPPLIER):
    sys.exit("Fill PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET and TEST_SUPPLIER_EMAIL in .env first.")


def get_token(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/v1/oauth2/token",
        auth=(CLIENT_ID, SECRET),
        data={"grant_type": "client_credentials"},
    )
    r.raise_for_status()
    print("1. OAuth token: OK")
    return r.json()["access_token"]


def send_payout(client: httpx.Client, token: str) -> str:
    batch_id = f"spendguard-test-{uuid.uuid4().hex[:10]}"  # also our idempotency key
    body = {
        "sender_batch_header": {
            "sender_batch_id": batch_id,
            "email_subject": "SpendGuard test payment",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": SUPPLIER,
                "amount": {"value": "5.00", "currency": "USD"},
                "note": "Test order: 20 HSS tool bits",
                "sender_item_id": "order-test-1",
            }
        ],
    }
    r = client.post(
        f"{BASE}/v1/payments/payouts",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    if r.status_code >= 400:
        print("2. Payout FAILED:", r.status_code, r.text)
        sys.exit("   -> Payouts may not be enabled for this app. See the notes in chat.")
    payout_batch_id = r.json()["batch_header"]["payout_batch_id"]
    print(f"2. Payout created: batch {payout_batch_id}")
    return payout_batch_id


def wait_for_status(client: httpx.Client, token: str, payout_batch_id: str) -> None:
    for attempt in range(10):
        r = client.get(
            f"{BASE}/v1/payments/payouts/{payout_batch_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        data = r.json()
        batch_status = data["batch_header"]["batch_status"]
        item_status = data["items"][0]["transaction_status"] if data.get("items") else "?"
        print(f"3. Check {attempt + 1}: batch={batch_status}, item={item_status}")
        if batch_status in ("SUCCESS", "DENIED", "CANCELED") or item_status in ("SUCCESS", "FAILED", "UNCLAIMED"):
            break
        time.sleep(3)
    print("\nDone. Log in to the supplier's sandbox account at https://www.sandbox.paypal.com to see the $5.")


with httpx.Client(timeout=30) as client:
    token = get_token(client)
    batch = send_payout(client, token)
    wait_for_status(client, token, batch)
