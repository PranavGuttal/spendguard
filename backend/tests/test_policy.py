"""Tests for every policy rule and the three demo scenarios."""
from datetime import datetime, timedelta

import pytest

from app.config import load_catalogue, load_policy
from app.policy import DraftOrder, OrderLine, Outcome, PastOrder, SpendContext, evaluate

POLICY = load_policy()
CAT = load_catalogue()
NOW = datetime(2026, 11, 8, 11, 0)


def ctx(spent=0.0, today=0, recent=()):
    return SpendContext(spent_this_month_inr=spent, orders_today=today, recent_orders=tuple(recent), now=NOW)


def order(supplier, *lines, reasoning="Matches the request; approved supplier; usual price."):
    return DraftOrder(supplier_id=supplier, lines=tuple(OrderLine(i, q) for i, q in lines), reasoning=reasoning)


def rules(decision):
    return {h.rule for h in decision.hits}


# ---- The three demo scenarios -------------------------------------------------

def test_demo_1_small_toolbits_order_is_approved():
    d = evaluate(order("sharma-tools", ("hss-bit-10", 20)), POLICY, CAT, ctx())
    assert d.outcome is Outcome.APPROVE
    assert d.total_inr == 3200
    assert d.hits == ()


def test_demo_2_large_inserts_order_needs_approval():
    d = evaluate(order("deccan-carbide", ("insert-cnmg", 10)), POLICY, CAT, ctx())
    assert d.outcome is Outcome.NEEDS_APPROVAL
    assert d.total_inr == 18000
    assert rules(d) == {"auto_approve_limit"}


def test_demo_3_laptop_from_unknown_shop_is_blocked():
    d = evaluate(order("quickbuy-online", ("laptop", 1)), POLICY, CAT, ctx())
    assert d.outcome is Outcome.BLOCK
    assert {"approved_vendor", "allowed_category", "hard_cap", "monthly_budget"} <= rules(d)


# ---- Each rule on its own -------------------------------------------------------

def test_unknown_item_is_blocked():
    d = evaluate(order("sharma-tools", ("made-up-item", 1)), POLICY, CAT, ctx())
    assert d.outcome is Outcome.BLOCK and "valid_order" in rules(d)


def test_item_from_a_different_supplier_is_blocked():
    d = evaluate(order("sharma-tools", ("insert-cnmg", 1)), POLICY, CAT, ctx())
    assert d.outcome is Outcome.BLOCK and "valid_order" in rules(d)


def test_zero_quantity_is_blocked():
    d = evaluate(order("sharma-tools", ("hss-bit-10", 0)), POLICY, CAT, ctx())
    assert d.outcome is Outcome.BLOCK


def test_empty_order_is_blocked():
    d = evaluate(order("sharma-tools"), POLICY, CAT, ctx())
    assert d.outcome is Outcome.BLOCK


def test_monthly_budget_blocks_when_nearly_spent():
    d = evaluate(order("sharma-tools", ("hss-bit-10", 20)), POLICY, CAT, ctx(spent=48_000))
    assert d.outcome is Outcome.BLOCK and "monthly_budget" in rules(d)


def test_hard_cap_blocks_big_orders_from_approved_vendors():
    d = evaluate(order("deccan-carbide", ("boring-bar", 8)), POLICY, CAT, ctx())  # 27,200
    assert d.outcome is Outcome.BLOCK and "hard_cap" in rules(d)


def test_auto_approve_limit_boundary():
    # 20 gloves x 240 = 4,800 -> approve; 25 x 240 = 6,000 -> hold for the owner
    assert evaluate(order("safeworks", ("gloves-cut", 20)), POLICY, CAT, ctx()).outcome is Outcome.APPROVE
    assert evaluate(order("safeworks", ("gloves-cut", 25)), POLICY, CAT, ctx()).outcome is Outcome.NEEDS_APPROVAL


def test_price_spike_needs_approval():
    d = evaluate(order("deccan-carbide", ("insert-wnmg", 1)), POLICY, CAT, ctx())  # 2,100 vs usual 1,700
    assert d.outcome is Outcome.NEEDS_APPROVAL and rules(d) == {"price_check"}


def test_duplicate_within_24h_needs_approval():
    past = PastOrder("sharma-tools", frozenset({"hss-bit-10"}), 3200, NOW - timedelta(hours=3), "PAID")
    d = evaluate(order("sharma-tools", ("hss-bit-10", 20)), POLICY, CAT, ctx(recent=[past]))
    assert d.outcome is Outcome.NEEDS_APPROVAL and "duplicate" in rules(d)


def test_old_or_rejected_orders_do_not_count_as_duplicates():
    old = PastOrder("sharma-tools", frozenset({"hss-bit-10"}), 3200, NOW - timedelta(hours=30), "PAID")
    rejected = PastOrder("sharma-tools", frozenset({"hss-bit-10"}), 3200, NOW - timedelta(hours=1), "REJECTED")
    d = evaluate(order("sharma-tools", ("hss-bit-10", 20)), POLICY, CAT, ctx(recent=[old, rejected]))
    assert d.outcome is Outcome.APPROVE


def test_daily_limit_needs_approval():
    d = evaluate(order("sharma-tools", ("hss-bit-10", 1)), POLICY, CAT, ctx(today=5))
    assert d.outcome is Outcome.NEEDS_APPROVAL and "daily_limit" in rules(d)


def test_missing_reasoning_needs_approval():
    d = evaluate(order("sharma-tools", ("hss-bit-10", 1), reasoning="  "), POLICY, CAT, ctx())
    assert d.outcome is Outcome.NEEDS_APPROVAL and "reasoning" in rules(d)


def test_block_beats_needs_approval():
    d = evaluate(order("quickbuy-online", ("printer-ink", 1), reasoning=""), POLICY, CAT, ctx())
    assert d.outcome is Outcome.BLOCK
    assert "reasoning" in rules(d)  # still reported, so the owner sees every reason


def test_decision_serialises_for_the_api():
    d = evaluate(order("deccan-carbide", ("insert-cnmg", 10)), POLICY, CAT, ctx()).to_dict()
    assert d["outcome"] == "NEEDS_APPROVAL" and d["total_inr"] == 18000
    assert d["rules_fired"][0]["rule"] == "auto_approve_limit"
