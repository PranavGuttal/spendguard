"""One-month budget top-ups: used only in their month, typos ignored, other rules untouched."""
from datetime import datetime

from app.config import Policy, load_catalogue, load_policy
from app.policy import DraftOrder, OrderLine, Outcome, SpendContext, evaluate

CAT = load_catalogue()
BASE = load_policy()


def policy_with(overrides):
    d = {k: getattr(BASE, k) for k in ("monthly_budget_inr", "auto_approve_limit_inr", "hard_cap_inr",
                                        "max_orders_per_day", "price_tolerance_pct", "duplicate_window_hours",
                                        "inr_per_usd")}
    d["approved_vendors"] = sorted(BASE.approved_vendors)
    d["allowed_categories"] = sorted(BASE.allowed_categories)
    d["budget_overrides"] = overrides
    return Policy.from_dict(d)


TEN_K = DraftOrder("deccan-carbide", (OrderLine("boring-bar", 3),), reasoning="Three bars for the new job.")  # 10,200
NOV20, DEC1 = datetime(2026, 11, 20, 10), datetime(2026, 12, 1, 10)


def test_shipped_policy_has_no_override():
    assert BASE.budget_overrides == {} and BASE.budget_for(NOV20) == 50000


def test_normal_budget_blocks_when_nearly_spent():
    d = evaluate(TEN_K, policy_with({}), CAT, SpendContext(48000, 0, now=NOV20))
    assert d.outcome is Outcome.BLOCK and "monthly_budget" in {h.rule for h in d.hits}


def test_override_raises_only_that_month():
    p = policy_with({"2026-11": 80000})
    assert p.budget_for(NOV20) == 80000 and p.budget_for(DEC1) == 50000
    d = evaluate(TEN_K, p, CAT, SpendContext(48000, 0, now=NOV20))
    # budget rule passes, but the auto-approve limit still asks the owner
    assert d.outcome is Outcome.NEEDS_APPROVAL
    assert {h.rule for h in d.hits} == {"auto_approve_limit"}


def test_override_does_not_lift_the_hard_cap():
    big = DraftOrder("deccan-carbide", (OrderLine("boring-bar", 8),), reasoning="x")  # 27,200
    d = evaluate(big, policy_with({"2026-11": 200000}), CAT, SpendContext(0, 0, now=NOV20))
    assert d.outcome is Outcome.BLOCK and "hard_cap" in {h.rule for h in d.hits}


def test_block_message_mentions_raised_budget():
    d = evaluate(TEN_K, policy_with({"2026-11": 55000}), CAT, SpendContext(48000, 0, now=NOV20))
    msg = next(h.message for h in d.hits if h.rule == "monthly_budget")
    assert "raised to ₹55,000" in msg


def test_bad_entries_are_ignored():
    p = policy_with({"Nov-2026": 90000, "2026-13": 90000, "2026-11": -5, "2026-10": "lots", "2026-12": 60000})
    assert p.budget_overrides == {"2026-12": 60000.0}
    assert p.budget_for(NOV20) == 50000 and p.budget_for(DEC1) == 60000


def test_not_a_mapping_is_ignored():
    assert policy_with(["2026-11", 80000]).budget_overrides == {}
