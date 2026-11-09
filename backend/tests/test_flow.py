"""End-to-end flow with a scripted fake LLM and a fake PayPal: no network."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.config import load_catalogue, load_policy
from app.paypal import PayPalError
from app.service import InvalidState, SpendGuardService

NOW = datetime(2026, 11, 8, 11, 0)


def call(name, **args):
    return {"tool_calls": [{"id": f"c-{name}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


class FakeLLM:
    """Plays back a script: search first, then propose the given order."""
    def __init__(self, query, supplier, lines, reasoning="Matches the request from an approved supplier."):
        self.script = [call("search_catalogue", query=query),
                       call("propose_order", supplier_id=supplier,
                            lines=[{"item_id": i, "qty": q} for i, q in lines], reasoning=reasoning)]
        self.seen_tool_results = []

    def chat(self, messages, tools):
        self.seen_tool_results += [m for m in messages if m["role"] == "tool"]
        return self.script.pop(0)


class FakePayPal:
    def __init__(self, fail=False):
        self.payouts, self.fail = [], fail

    def create_payout(self, sender_batch_id, receiver_email, amount_usd, note):
        if self.fail:
            raise PayPalError("Payout failed 422: INSUFFICIENT_FUNDS")
        self.payouts.append((sender_batch_id, receiver_email, amount_usd))
        return {"batch_header": {"payout_batch_id": f"PB-{len(self.payouts)}", "batch_status": "PENDING"}}

    def get_payout(self, payout_batch_id):
        return {"batch_header": {"batch_status": "SUCCESS"}, "items": [{"transaction_status": "SUCCESS"}]}


def make(llm, payer):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from app import models  # noqa: F401
    SQLModel.metadata.create_all(eng)
    return SpendGuardService(load_catalogue(), load_policy(), lambda: llm, lambda: payer, eng,
                             poll_attempts=1, poll_delay_s=0)


def test_small_order_is_paid_automatically():
    pp = FakePayPal()
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), pp)
    out = svc.submit_request("20 HSS tool bits for the lathe", now=NOW)["order"]
    assert out["status"] == "PAID"
    assert out["decisions"][0]["outcome"] == "APPROVE"
    assert len(pp.payouts) == 1
    batch_id, email, usd = pp.payouts[0]
    assert batch_id.startswith("spendguard-order-1-")
    assert (email, usd) == ("sb-qsin4753706757@personal.example.com", round(3200 / 88, 2))


def test_payout_ids_differ_after_demo_reset():
    # PayPal refuses a reused sender_batch_id, and order numbers restart after a reset or redeploy
    pp = FakePayPal()
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), pp)
    svc.submit_request("20 HSS tool bits for the lathe", now=NOW)
    svc.reset_demo()
    svc._llm = FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)])
    svc.submit_request("20 HSS tool bits for the lathe", now=NOW + timedelta(minutes=5))
    assert len(pp.payouts) == 2
    assert pp.payouts[0][0] != pp.payouts[1][0]


def test_agent_sees_catalogue_search_results():
    llm = FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)])
    make(llm, FakePayPal()).submit_request("20 HSS tool bits", now=NOW)
    found = json.loads(llm.seen_tool_results[0]["content"])
    assert any(r["item_id"] == "hss-bit-10" for r in found["results"])


def test_big_order_waits_for_owner_then_pays_on_approval():
    pp = FakePayPal()
    svc = make(FakeLLM("carbide insert", "deccan-carbide", [("insert-cnmg", 10)]), pp)
    order = svc.submit_request("10 boxes of carbide inserts", now=NOW)["order"]
    assert order["status"] == "PENDING_APPROVAL" and pp.payouts == []
    paid = svc.approve(order["id"], note="OK for the big job")
    assert paid["status"] == "PAID" and len(pp.payouts) == 1
    assert [d["decided_by"] for d in paid["decisions"]] == ["policy", "owner"]


def test_rejected_order_is_never_paid():
    pp = FakePayPal()
    svc = make(FakeLLM("carbide insert", "deccan-carbide", [("insert-cnmg", 10)]), pp)
    order = svc.submit_request("10 boxes of carbide inserts", now=NOW)["order"]
    assert svc.reject(order["id"])["status"] == "REJECTED"
    with pytest.raises(InvalidState):
        svc.approve(order["id"])
    assert pp.payouts == []


def test_blocked_order_moves_no_money():
    pp = FakePayPal()
    svc = make(FakeLLM("laptop", "quickbuy-online", [("laptop", 1)]), pp)
    order = svc.submit_request("buy a laptop from a new website", now=NOW)["order"]
    assert order["status"] == "BLOCKED" and pp.payouts == []
    with pytest.raises(InvalidState):
        svc.approve(order["id"])


def test_paypal_failure_marks_order_failed():
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), FakePayPal(fail=True))
    out = svc.submit_request("20 HSS tool bits", now=NOW)["order"]
    assert out["status"] == "FAILED" and out["payment"]["status"] == "FAILED"


def test_no_double_payment_for_same_order():
    pp = FakePayPal()
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), pp)
    out = svc.submit_request("20 HSS tool bits", now=NOW)["order"]
    from sqlmodel import Session
    from app.models import Order
    with Session(svc.engine) as s:
        svc._pay(s, s.get(Order, out["id"]))  # a retry must not pay again
    assert len(pp.payouts) == 1


def test_budget_reflects_paid_orders():
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), FakePayPal())
    svc.submit_request("20 HSS tool bits", now=NOW)
    b = svc.budget(now=NOW)
    assert b["spent_inr"] == 3200 and b["remaining_inr"] == 50000 - 3200


def test_api_endpoints(monkeypatch):
    import app.main as main
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), FakePayPal())
    monkeypatch.setattr(main, "service", svc)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    with TestClient(main.app) as client:
        assert client.get("/api/health").json() == {"ok": True}
        r = client.post("/api/requests", json={"text": "20 HSS tool bits"})
        assert r.status_code == 200 and r.json()["order"]["status"] == "PAID"
        assert len(client.get("/api/orders").json()) == 1
        assert client.get("/api/audit").json()[0]["outcome"] == "APPROVE"
        assert client.post("/api/orders/1/approve").status_code == 409
        assert client.post("/api/orders/99/approve").status_code == 404


def test_api_demo_password(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "service", make(FakeLLM("x", "sharma-tools", [("hss-bit-10", 1)]), FakePayPal()))
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setenv("DEMO_PASSWORD", "letmein")
    with TestClient(main.app) as client:
        assert client.post("/api/requests", json={"text": "1 tool bit"}).status_code == 401


def test_demo_reset_clears_orders():
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), FakePayPal())
    svc.submit_request("20 HSS tool bits", now=NOW)
    svc.reset_demo()
    assert svc.list_orders() == [] and svc.audit() == []


def test_agent_without_proposal_creates_no_order():
    class Talker:
        def chat(self, messages, tools):
            return {"content": "The catalogue has no welding rods.", "tool_calls": None}
    svc = make(Talker(), FakePayPal())
    out = svc.submit_request("buy welding rods", now=NOW)
    assert out["order"] is None and "welding" in out["agent_message"] and svc.list_orders() == []


def test_web_app_is_served(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "service", make(FakeLLM("x", "sharma-tools", [("hss-bit-10", 1)]), FakePayPal()))
    monkeypatch.setattr(main, "init_db", lambda: None)
    with TestClient(main.app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert ("SpendGuard" in r.text) or ("SpendGuard API is running" in r.text)


def test_budget_override_shows_in_budget_and_audit():
    from dataclasses import replace
    svc = make(FakeLLM("HSS tool bit", "sharma-tools", [("hss-bit-10", 20)]), FakePayPal())
    svc.policy = replace(svc.policy, budget_overrides={"2026-11": 80000.0})
    svc.submit_request("20 HSS tool bits", now=NOW)
    b = svc.budget(now=NOW)
    assert b["monthly_budget_inr"] == 80000 and b["normal_monthly_budget_inr"] == 50000 and b["raised_this_month"]
    assert b["remaining_inr"] == 80000 - 3200
    assert "raised to ₹80,000" in svc.audit()[0]["note"]
    assert svc.budget(now=datetime(2026, 12, 1))["monthly_budget_inr"] == 50000
