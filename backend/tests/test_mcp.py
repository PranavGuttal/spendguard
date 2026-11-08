"""The MCP server: an outside agent can propose purchases, but only the rules decide and it cannot approve."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.mcp_server import build_server
from tests.test_flow import FakeLLM, FakePayPal, make


def call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    assert not getattr(result, "is_error", False) and not getattr(result, "isError", False), result
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured is not None:
        return structured.get("result", structured)
    return json.loads(result.content[0].text)


@pytest.fixture
def setup():
    payer = FakePayPal()
    svc = make(FakeLLM("x", "sharma-tools", [("hss-bit-10", 1)]), payer)
    return svc, payer, build_server(svc)


def test_tool_list_has_no_approve_or_pay(setup):
    _, _, server = setup
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"search_catalogue", "get_budget", "propose_purchase", "list_orders", "check_order"}
    assert not any("approve" in n or "pay" == n for n in names)


def test_search_and_budget(setup):
    _, _, server = setup
    found = call(server, "search_catalogue", {"query": "carbide insert"})
    assert any(r["item_id"] == "insert-cnmg" for r in found["results"])
    assert call(server, "get_budget", {})["remaining_inr"] == 50000


def test_small_purchase_is_paid(setup):
    svc, payer, server = setup
    out = call(server, "propose_purchase", {"request": "20 tool bits", "supplier_id": "sharma-tools",
                                            "items": [{"item_id": "hss-bit-10", "qty": 20}], "reasoning": "Usual bits."})
    assert out["status"] == "PAID" and out["paypal_payout"]["status"] == "SUCCESS" and len(payer.payouts) == 1
    assert svc.list_orders()[0]["id"] == out["order_id"]  # same database as the web app


def test_big_purchase_waits_for_owner(setup):
    _, payer, server = setup
    out = call(server, "propose_purchase", {"request": "10 boxes of inserts", "supplier_id": "deccan-carbide",
                                            "items": [{"item_id": "insert-cnmg", "qty": 10}], "reasoning": "Big job."})
    assert out["status"] == "PENDING_APPROVAL" and payer.payouts == []
    assert "web app" in out["what_next"]
    assert [o["status"] for o in call(server, "list_orders", {"status": "PENDING_APPROVAL"})] == ["PENDING_APPROVAL"]


def test_unapproved_supplier_is_blocked(setup):
    _, payer, server = setup
    out = call(server, "propose_purchase", {"request": "a laptop", "supplier_id": "quickbuy-online",
                                            "items": [{"item_id": "laptop", "qty": 1}], "reasoning": "Asked for a laptop."})
    assert out["status"] == "BLOCKED" and payer.payouts == []
    assert any("not an approved supplier" in r for r in out["rules"])


def test_made_up_item_is_blocked(setup):
    _, payer, server = setup
    out = call(server, "propose_purchase", {"request": "gold bars", "supplier_id": "sharma-tools",
                                            "items": [{"item_id": "gold-bar", "qty": 1}], "reasoning": "x"})
    assert out["status"] == "BLOCKED" and payer.payouts == []


def test_real_stdio_handshake(tmp_path):
    """Start backend/mcp_server.py as Claude Desktop would and list its tools over stdio."""
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    backend = Path(__file__).resolve().parents[1]
    env = {**os.environ, "SPENDGUARD_DB": str(tmp_path / "mcp.db")}
    params = StdioServerParameters(command=sys.executable, args=[str(backend / "mcp_server.py")], env=env)

    async def go():
        async with Client(params) as client:
            tools = await client.list_tools()
            return sorted(t.name for t in tools.tools)

    assert asyncio.run(go()) == ["check_order", "get_budget", "list_orders", "propose_purchase", "search_catalogue"]
