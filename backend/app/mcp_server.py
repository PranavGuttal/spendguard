"""SpendGuard as an MCP server: let any MCP agent (e.g. Claude Desktop) buy through your rules.

The outside agent can search the catalogue, check the budget, propose a purchase and look
at orders. It CANNOT approve held orders or pay directly: every proposal goes through the
same policy engine as the web app, and money moves only on APPROVE. Held orders wait for
the owner in the SpendGuard web app. Orders are stored in the same database, so they
appear there too.

Run (stdio):  python backend/mcp_server.py
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .policy import DraftOrder, OrderLine
from .service import SpendGuardService
from .tools import ToolContext, search_catalogue

INSTRUCTIONS = """SpendGuard buys supplies for a small machine shop through PayPal (sandbox), within the owner's rules.
1. Use search_catalogue to find items; use only item_id and supplier_id values it returns.
2. Optionally call get_budget.
3. Call propose_purchase with ONE supplier and a short, factual reasoning.
The rules decide: APPROVE pays the supplier through PayPal at once; NEEDS_APPROVAL waits for the owner in the
SpendGuard web app; BLOCK never pays. You cannot approve or pay yourself. Report the decision and reasons to the user."""


def _order_summary(view: dict) -> dict[str, Any]:
    policy = next((d for d in view["decisions"] if d["decided_by"] == "policy"), None)
    pay = view.get("payment")
    return {
        "order_id": view["id"],
        "status": view["status"],
        "supplier": view["supplier"]["name"],
        "total_inr": view["total_inr"],
        "items": [f'{l["qty"]} x {l["name"]}' for l in view["lines"]],
        "rules": [r["message"] for r in (policy or {}).get("rules_fired", [])] or ["Passed every rule."],
        "paypal_payout": None if not pay else
        {"amount_usd": pay["amount_usd"], "status": pay["status"], "batch_id": pay["paypal_batch_id"]},
        "what_next": {
            "PAID": "Paid through PayPal sandbox.",
            "PAYING": "Payout sent; call check_order shortly to confirm it completed.",
            "PENDING_APPROVAL": "Waiting for the owner to approve in the SpendGuard web app. Nothing has been paid.",
            "BLOCKED": "Blocked by the rules. Nothing was paid.",
            "REJECTED": "The owner rejected it. Nothing was paid.",
            "FAILED": "The PayPal payout failed. Nothing was paid.",
        }.get(view["status"], ""),
    }


def build_server(service: SpendGuardService) -> MCPServer:
    server = MCPServer(name="SpendGuard", instructions=INSTRUCTIONS, version="0.1.0")

    @server.tool(name="search_catalogue",
                 description="Search the supplier catalogue. Returns items with item_id, supplier_id, INR price and whether the supplier is approved.")
    def search_catalogue_tool(query: str) -> dict:
        from datetime import datetime
        from sqlmodel import Session
        with Session(service.engine) as s:
            return search_catalogue(ToolContext(service.catalogue, service.policy, s, datetime.now()), query)

    @server.tool(description="This month's budget, spent, waiting for approval and remaining amounts in INR, plus the auto-approve limit and hard cap per order.")
    def get_budget() -> dict:
        return service.budget()

    @server.tool(description="Propose ONE purchase from ONE supplier. The owner's rules decide: APPROVE pays via PayPal sandbox, NEEDS_APPROVAL waits for the owner, BLOCK never pays. items: list of {item_id, qty}.")
    def propose_purchase(request: str, supplier_id: str, items: list[dict], reasoning: str) -> dict:
        lines = []
        for raw in items or []:
            try:
                lines.append(OrderLine(item_id=str(raw["item_id"]), qty=int(raw["qty"])))
            except (KeyError, TypeError, ValueError):
                continue
        draft = DraftOrder(supplier_id=supplier_id, lines=tuple(lines), reasoning=reasoning, request_text=request)
        return _order_summary(service.submit_proposal(request, draft))

    @server.tool(description="List recent SpendGuard orders (newest first), optionally only one status: PAID, PAYING, PENDING_APPROVAL, BLOCKED, REJECTED, FAILED.")
    def list_orders(status: str = "", limit: int = 10) -> list[dict]:
        views = [v for v in service.list_orders() if not status or v["status"] == status]
        return [_order_summary(v) for v in views[: max(1, min(limit, 50))]]

    @server.tool(description="Check one order, refreshing its PayPal payout status if it is still being paid.")
    def check_order(order_id: int) -> dict:
        return _order_summary(service.refresh_payment(order_id))

    return server
