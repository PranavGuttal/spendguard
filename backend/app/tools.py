"""Tools the agent may call. None of them can move money: the agent can only
*propose* an order; the policy engine and the service layer decide and pay."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlmodel import Session, select

from .config import Catalogue, Policy
from .models import Order, OrderLine

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalogue",
            "description": "Search the supplier catalogue. Returns matching items with their item_id, supplier_id, price in INR and whether the supplier is approved.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Words to search for, e.g. 'carbide insert' or 'gloves'"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": "Get this month's budget, amount spent, amount remaining, and the auto-approve limit, in INR.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_orders",
            "description": "List orders placed in the last 7 days, to avoid buying the same thing twice.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_order",
            "description": "Propose ONE order to ONE supplier. Use only item_id and supplier_id values returned by search_catalogue. This does not pay; the company's rules decide what happens next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
                    "lines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"item_id": {"type": "string"}, "qty": {"type": "integer", "minimum": 1}},
                            "required": ["item_id", "qty"],
                        },
                    },
                    "reasoning": {"type": "string", "description": "One or two sentences: why these items, this quantity and this supplier."},
                },
                "required": ["supplier_id", "lines", "reasoning"],
            },
        },
    },
]

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    words = set(_WORD.findall(text.lower()))
    # crude singular form so 'bits' matches 'bit', 'boxes' matches 'box'
    return words | {w[:-2] if w.endswith("es") else w[:-1] for w in words if len(w) > 3 and w.endswith("s")}


@dataclass
class ToolContext:
    catalogue: Catalogue
    policy: Policy
    session: Session
    now: datetime


def month_spend_inr(session: Session, now: datetime) -> float:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = session.exec(select(Order).where(Order.created_at >= start, Order.status.in_(["PAID", "PAYING"]))).all()
    return sum(o.total_inr for o in rows)


def search_catalogue(ctx: ToolContext, query: str) -> dict:
    q = _words(query)
    scored = []
    for item in ctx.catalogue.items.values():
        hay = _words(f"{item.name} {item.category} {item.id}")
        score = len(q & hay)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1].unit_price_inr))
    results = []
    for _, item in scored[:8]:
        sup = ctx.catalogue.suppliers[item.supplier_id]
        results.append({
            "item_id": item.id, "name": item.name, "category": item.category, "unit": item.unit,
            "unit_price_inr": item.unit_price_inr, "supplier_id": sup.id, "supplier_name": sup.name,
            "supplier_approved": sup.approved,
        })
    return {"results": results, "count": len(results)}


def get_budget_status(ctx: ToolContext) -> dict:
    spent = month_spend_inr(ctx.session, ctx.now)
    budget = ctx.policy.budget_for(ctx.now)
    return {
        "monthly_budget_inr": budget,
        "spent_this_month_inr": spent,
        "remaining_inr": budget - spent,
        "auto_approve_limit_inr": ctx.policy.auto_approve_limit_inr,
    }


def get_recent_orders(ctx: ToolContext) -> dict:
    since = ctx.now - timedelta(days=7)
    orders = ctx.session.exec(select(Order).where(Order.created_at >= since).order_by(Order.created_at.desc())).all()
    out = []
    for o in orders[:15]:
        lines = ctx.session.exec(select(OrderLine).where(OrderLine.order_id == o.id)).all()
        out.append({
            "order_id": o.id, "supplier_id": o.supplier_id, "status": o.status, "total_inr": o.total_inr,
            "items": [f"{l.qty} x {l.item_name}" for l in lines], "created_at": o.created_at.isoformat(timespec="minutes"),
        })
    return {"orders": out}
