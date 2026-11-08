"""'Ask about spending': a read-only AI analyst.

The owner asks a question in plain English ("How much did we spend on carbide
inserts this month?"). The model answers using three read-only tools: a spend
summary from SpendGuard's own orders, a list of orders, and the company's
PayPal transactions (Transaction Search API). It cannot buy, approve or pay.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from .config import Catalogue, Policy
from .llm import LLM
from .logs import step
from .models import Order, OrderLine
from .paypal import Payer, PayPalError

SYSTEM_PROMPT = """You are SpendGuard's spending analyst for a small machine shop in India.
Answer the owner's question using ONLY numbers returned by your tools. Never invent figures.
- Use spend_summary for totals by supplier, category or status, and list_orders for individual orders.
- Use paypal_transactions when the owner asks what PayPal actually recorded. Sandbox PayPal data
  can lag by up to about 3 hours, so say so if a recent payout is missing.
- Order amounts are in Indian rupees (₹). PayPal amounts are in US dollars ($).
- Keep the answer short: two to five sentences, or a short list. Name the tool data you used.
You are read-only: you cannot place, approve or pay for orders."""

TOOLS = [
    {"type": "function", "function": {
        "name": "spend_summary",
        "description": "Totals for one calendar month from SpendGuard's orders: paid, waiting for approval, blocked, by supplier and by category, in INR.",
        "parameters": {"type": "object", "properties": {
            "month": {"type": "string", "description": "YYYY-MM. Leave empty for the current month."}}}}},
    {"type": "function", "function": {
        "name": "list_orders",
        "description": "Recent SpendGuard purchase orders, newest first, optionally filtered by status.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["PAID", "PENDING_APPROVAL", "BLOCKED", "REJECTED", "FAILED", "PAYING"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50}}}}},
    {"type": "function", "function": {
        "name": "paypal_transactions",
        "description": "Successful transactions recorded by PayPal for the company's account (PayPal Transaction Search), last N days (max 31).",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 31}}}}},
]

MAX_STEPS = 5


@dataclass
class Answer:
    answer: str
    tools_used: list[str] = field(default_factory=list)


class Analyst:
    def __init__(self, catalogue: Catalogue, policy: Policy, session: Session, payer_factory, now: datetime):
        self.catalogue, self.policy, self.session, self._payer_factory, self.now = catalogue, policy, session, payer_factory, now

    # ------------------------------------------------------------- tools
    def spend_summary(self, month: str = "") -> dict:
        key = month.strip() or self.now.strftime("%Y-%m")
        try:
            start = datetime.strptime(key, "%Y-%m")
        except ValueError:
            return {"error": f"Month must look like 2026-11, got {month!r}"}
        end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
        orders = self.session.exec(select(Order).where(Order.created_at >= start, Order.created_at < end)).all()
        by_status: dict[str, float] = defaultdict(float)
        by_supplier: dict[str, float] = defaultdict(float)
        by_category: dict[str, float] = defaultdict(float)
        for o in orders:
            by_status[o.status] += o.total_inr
            if o.status in ("PAID", "PAYING"):
                name = self.catalogue.suppliers[o.supplier_id].name if o.supplier_id in self.catalogue.suppliers else o.supplier_id
                by_supplier[name] += o.total_inr
                for line in self.session.exec(select(OrderLine).where(OrderLine.order_id == o.id)).all():
                    item = self.catalogue.items.get(line.item_id)
                    by_category[item.category if item else "unknown"] += line.qty * line.unit_price_inr
        paid = by_status.get("PAID", 0) + by_status.get("PAYING", 0)
        budget = self.policy.budget_for(start)
        return {
            "month": key, "orders": len(orders), "paid_inr": paid,
            "waiting_for_approval_inr": by_status.get("PENDING_APPROVAL", 0),
            "blocked_inr": by_status.get("BLOCKED", 0), "rejected_inr": by_status.get("REJECTED", 0),
            "budget_inr": budget, "budget_left_inr": budget - paid,
            "paid_by_supplier_inr": dict(by_supplier), "paid_by_category_inr": dict(by_category),
        }

    def list_orders(self, status: str = "", limit: int = 15) -> dict:
        q = select(Order).order_by(Order.created_at.desc())
        if status:
            q = q.where(Order.status == status)
        out = []
        for o in self.session.exec(q).all()[: max(1, min(int(limit or 15), 50))]:
            lines = self.session.exec(select(OrderLine).where(OrderLine.order_id == o.id)).all()
            out.append({"order_id": o.id, "date": o.created_at.isoformat(timespec="minutes"), "status": o.status,
                        "supplier_id": o.supplier_id, "total_inr": o.total_inr,
                        "items": [f"{l.qty} x {l.item_name}" for l in lines]})
        return {"orders": out}

    def paypal_transactions(self, days: int = 31) -> dict:
        try:
            raw = self._payer_factory().list_transactions(days=days)
        except PayPalError as exc:
            msg = str(exc)
            hint = (" Tick 'Transaction search' in the app's features on the PayPal developer dashboard."
                    if "403" in msg or "NOT_AUTHORIZED" in msg else "")
            return {"error": f"PayPal transaction search is not available: {msg[:200]}.{hint}"}
        rows = []
        for t in raw.get("transaction_details", [])[:50]:
            info = t.get("transaction_info", {})
            amount = info.get("transaction_amount", {})
            rows.append({"id": info.get("transaction_id"), "date": info.get("transaction_initiation_date"),
                         "amount": amount.get("value"), "currency": amount.get("currency_code"),
                         "event_code": info.get("transaction_event_code"), "note": info.get("transaction_note", "")})
        return {"transactions": rows, "count": len(rows), "note": "Sandbox data can lag by up to about 3 hours."}

    # -------------------------------------------------------------- loop
    def _run(self, name: str, args: dict) -> dict:
        if name == "spend_summary":
            out = self.spend_summary(str(args.get("month", "") or ""))
        elif name == "list_orders":
            out = self.list_orders(str(args.get("status", "") or ""), args.get("limit") or 15)
        elif name == "paypal_transactions":
            out = self.paypal_transactions(args.get("days") or 31)
        else:
            out = {"error": f"Unknown tool {name!r}"}
        summary = out.get("error") or ", ".join(f"{k}={v}" for k, v in out.items() if not isinstance(v, (dict, list)))[:160]
        step("ASK", f"{name}({json.dumps(args)}) -> {summary or 'ok'}")
        return out

    def ask(self, question: str, llm: LLM) -> Answer:
        step("ASK", f'"{question}"')
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Today is {self.now:%d %B %Y}. {question}"}]
        used: list[str] = []
        for _ in range(MAX_STEPS):
            msg = llm.chat(messages, TOOLS)
            calls = msg.get("tool_calls") or []
            if not calls:
                answer = (msg.get("content") or "").strip() or "I could not find an answer in the data."
                step("ASK", f"answer: {answer[:160]}")
                return Answer(answer, used)
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                used.append(name)
                result = self._run(name, args)
                messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": json.dumps(result)})
        return Answer("I could not finish the answer in time. Try a narrower question.", used)
