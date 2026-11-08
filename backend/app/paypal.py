"""PayPal sandbox client: OAuth token, Payouts, payout status."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

BASES = {"sandbox": "https://api-m.sandbox.paypal.com", "live": "https://api-m.paypal.com"}


class PayPalError(RuntimeError):
    pass


class Payer(Protocol):
    def create_payout(self, sender_batch_id: str, receiver_email: str, amount_usd: float, note: str) -> dict: ...
    def get_payout(self, payout_batch_id: str) -> dict: ...
    def list_transactions(self, days: int = 31) -> dict: ...


class PayPalClient:
    def __init__(self, timeout: float = 30.0):
        env = os.getenv("PAYPAL_ENV", "sandbox")
        if env != "sandbox":
            raise PayPalError("SpendGuard only runs against the PayPal sandbox (PAYPAL_ENV=sandbox).")
        self.base = BASES[env]
        self.client_id = os.getenv("PAYPAL_CLIENT_ID", "")
        self.secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
        if not (self.client_id and self.secret):
            raise PayPalError("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set in .env")
        self.timeout = timeout
        self._token = ""
        self._token_expiry = 0.0

    def _auth_header(self) -> dict:
        if not self._token or time.time() > self._token_expiry - 60:
            r = httpx.post(f"{self.base}/v1/oauth2/token", auth=(self.client_id, self.secret),
                           data={"grant_type": "client_credentials"}, timeout=self.timeout)
            if r.status_code >= 400:
                raise PayPalError(f"OAuth failed {r.status_code}: {r.text[:300]}")
            data = r.json()
            self._token = data["access_token"]
            self._token_expiry = time.time() + int(data.get("expires_in", 3000))
        return {"Authorization": f"Bearer {self._token}"}

    def create_payout(self, sender_batch_id: str, receiver_email: str, amount_usd: float, note: str) -> dict:
        body = {
            "sender_batch_header": {"sender_batch_id": sender_batch_id, "email_subject": "Payment from SpendGuard"},
            "items": [{
                "recipient_type": "EMAIL",
                "receiver": receiver_email,
                "amount": {"value": f"{amount_usd:.2f}", "currency": "USD"},
                "note": note[:4000],
                "sender_item_id": sender_batch_id,
            }],
        }
        r = httpx.post(f"{self.base}/v1/payments/payouts", headers=self._auth_header(), json=body, timeout=self.timeout)
        if r.status_code >= 400:
            raise PayPalError(f"Payout failed {r.status_code}: {r.text[:500]}")
        return r.json()

    def get_payout(self, payout_batch_id: str) -> dict:
        r = httpx.get(f"{self.base}/v1/payments/payouts/{payout_batch_id}", headers=self._auth_header(), timeout=self.timeout)
        if r.status_code >= 400:
            raise PayPalError(f"Payout status failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def list_transactions(self, days: int = 31) -> dict:
        """PayPal Transaction Search (GET /v1/reporting/transactions): this account's
        successful transactions in the last `days` days (PayPal allows at most 31).
        Needs "Transaction search" ticked in the app's features; sandbox data can lag up to ~3 hours."""
        days = max(1, min(int(days), 31))
        end = datetime.now(timezone.utc).replace(microsecond=0)
        start = end - timedelta(days=days)
        params = {
            "start_date": start.isoformat().replace("+00:00", "Z"),
            "end_date": end.isoformat().replace("+00:00", "Z"),
            "transaction_status": "S",
            "fields": "transaction_info",
            "page_size": 100,
            "page": 1,
        }
        r = httpx.get(f"{self.base}/v1/reporting/transactions", headers=self._auth_header(),
                      params=params, timeout=self.timeout)
        if r.status_code >= 400:
            raise PayPalError(f"Transaction search failed {r.status_code}: {r.text[:300]}")
        return r.json()
