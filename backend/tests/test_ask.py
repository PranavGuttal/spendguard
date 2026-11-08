"""'Ask about spending': read-only answers from orders and PayPal transactions."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.paypal import PayPalClient, PayPalError
from tests.test_flow import NOW, FakeLLM, FakePayPal, make


class AnalystLLM:
    """Calls the given tools in order, then answers using what it saw."""
    def __init__(self, *tool_calls):
        self.calls = list(tool_calls)
        self.seen = []

    def chat(self, messages, tools):
        assert {t["function"]["name"] for t in tools} == {"spend_summary", "list_orders", "paypal_transactions"}
        self.seen = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        if self.calls:
            name, args = self.calls.pop(0)
            return {"tool_calls": [{"id": name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
        return {"content": f"Seen: {json.dumps(self.seen)}"}


class PayPalWithTransactions(FakePayPal):
    def __init__(self, fail_with=None):
        super().__init__()
        self.fail_with = fail_with

    def list_transactions(self, days=31):
        if self.fail_with:
            raise PayPalError(self.fail_with)
        return {"transaction_details": [{"transaction_info": {
            "transaction_id": "9XY", "transaction_initiation_date": "2026-11-08T04:30:00+0000",
            "transaction_amount": {"currency_code": "USD", "value": "-36.36"}, "transaction_event_code": "T0000"}}]}


def seeded(llm, payer):
    """A service with one paid order (₹3,200) and one held order (₹18,000)."""
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), payer)
    svc.submit_request("20 HSS tool bits", now=NOW)
    svc._llm = FakeLLM("carbide insert", "deccan-carbide", [("insert-cnmg", 10)])
    svc.submit_request("10 boxes of inserts", now=NOW)
    svc._llm = llm
    return svc


def test_spend_summary_answers_from_real_orders():
    llm = AnalystLLM(("spend_summary", {}))
    out = seeded(llm, PayPalWithTransactions()).ask("How much did we spend this month?", now=NOW)
    summary = llm.seen[0]
    assert summary["paid_inr"] == 3200 and summary["waiting_for_approval_inr"] == 18000
    assert summary["paid_by_supplier_inr"] == {"Sharma Tools & Hardware": 3200}
    assert summary["paid_by_category_inr"] == {"tooling": 3200}
    assert summary["budget_left_inr"] == 50000 - 3200
    assert out["tools_used"] == ["spend_summary"]


def test_list_orders_filters_by_status():
    llm = AnalystLLM(("list_orders", {"status": "PENDING_APPROVAL"}))
    seeded(llm, PayPalWithTransactions()).ask("What is waiting for me?", now=NOW)
    orders = llm.seen[0]["orders"]
    assert len(orders) == 1 and orders[0]["status"] == "PENDING_APPROVAL" and orders[0]["total_inr"] == 18000


def test_paypal_transactions_are_simplified():
    llm = AnalystLLM(("paypal_transactions", {"days": 7}))
    seeded(llm, PayPalWithTransactions()).ask("What did PayPal record?", now=NOW)
    tx = llm.seen[0]["transactions"][0]
    assert tx == {"id": "9XY", "date": "2026-11-08T04:30:00+0000", "amount": "-36.36", "currency": "USD",
                  "event_code": "T0000", "note": ""}


def test_paypal_permission_error_gives_a_fix():
    llm = AnalystLLM(("paypal_transactions", {}))
    seeded(llm, PayPalWithTransactions(fail_with="Transaction search failed 403: NOT_AUTHORIZED")).ask("PayPal?", now=NOW)
    assert "Transaction search" in llm.seen[0]["error"]


def test_bad_month_is_reported_not_crashed():
    llm = AnalystLLM(("spend_summary", {"month": "November"}))
    seeded(llm, PayPalWithTransactions()).ask("November?", now=NOW)
    assert "2026-11" in llm.seen[0]["error"]


def test_analyst_cannot_buy_or_pay():
    payer = PayPalWithTransactions()
    llm = AnalystLLM(("spend_summary", {}), ("list_orders", {}), ("paypal_transactions", {}))
    svc = seeded(llm, payer)
    before = len(payer.payouts)
    svc.ask("Summarise everything", now=NOW)
    assert len(payer.payouts) == before and len(svc.list_orders()) == 2


def test_list_transactions_request_shape(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("PAYPAL_ENV", "sandbox")
    seen = {}

    class R:
        def __init__(self, code, data): self.status_code, self._d, self.text = code, data, json.dumps(data)
        def json(self): return self._d

    monkeypatch.setattr(httpx, "post", lambda *a, **k: R(200, {"access_token": "t", "expires_in": 3600}))

    def fake_get(url, headers, params, timeout):
        seen.update(url=url, params=params)
        return R(200, {"transaction_details": []})

    monkeypatch.setattr(httpx, "get", fake_get)
    PayPalClient().list_transactions(days=90)
    assert seen["url"].endswith("/v1/reporting/transactions")
    assert seen["params"]["transaction_status"] == "S"
    assert seen["params"]["start_date"].endswith("Z") and seen["params"]["end_date"].endswith("Z")
    from datetime import datetime
    span = datetime.fromisoformat(seen["params"]["end_date"][:-1]) - datetime.fromisoformat(seen["params"]["start_date"][:-1])
    assert span.days == 31  # capped at PayPal's maximum


def test_ask_endpoint(monkeypatch):
    import app.main as main
    svc = seeded(AnalystLLM(("spend_summary", {})), PayPalWithTransactions())
    monkeypatch.setattr(main, "service", svc)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    with TestClient(main.app) as client:
        r = client.post("/api/ask", json={"question": "How much did we spend?"})
        assert r.status_code == 200 and "3200" in r.json()["answer"] and r.json()["tools_used"] == ["spend_summary"]
        assert client.post("/api/ask", json={"question": "x"}).status_code == 422
