"""The SpendGuard policy engine.

The AI agent only *proposes* an order. This module decides, with plain
deterministic rules, whether the order is paid now (APPROVE), held for the
owner (NEEDS_APPROVAL) or never paid (BLOCK). No LLM is involved here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .config import Catalogue, Policy


class Outcome(str, Enum):
    APPROVE = "APPROVE"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    BLOCK = "BLOCK"


_SEVERITY = {Outcome.APPROVE: 0, Outcome.NEEDS_APPROVAL: 1, Outcome.BLOCK: 2}


@dataclass(frozen=True)
class OrderLine:
    item_id: str
    qty: int


@dataclass(frozen=True)
class DraftOrder:
    """What the agent proposes. Prices are always looked up from the
    catalogue, never taken from the agent, so the model cannot invent them."""
    supplier_id: str
    lines: tuple[OrderLine, ...]
    reasoning: str = ""
    request_text: str = ""


@dataclass(frozen=True)
class PastOrder:
    supplier_id: str
    item_ids: frozenset[str]
    total_inr: float
    created_at: datetime
    status: str  # PAID, PENDING_APPROVAL, PAYING, ...


@dataclass(frozen=True)
class SpendContext:
    spent_this_month_inr: float
    orders_today: int
    recent_orders: tuple[PastOrder, ...] = ()
    now: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class RuleHit:
    rule: str
    outcome: Outcome
    message: str


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    total_inr: float
    hits: tuple[RuleHit, ...]

    @property
    def reasons(self) -> list[str]:
        return [h.message for h in self.hits]

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "total_inr": round(self.total_inr, 2),
            "rules_fired": [
                {"rule": h.rule, "outcome": h.outcome.value, "message": h.message} for h in self.hits
            ],
        }


def order_total_inr(draft: DraftOrder, catalogue: Catalogue) -> float:
    total = 0.0
    for line in draft.lines:
        item = catalogue.items.get(line.item_id)
        if item is not None:
            total += item.unit_price_inr * line.qty
    return total


def evaluate(draft: DraftOrder, policy: Policy, catalogue: Catalogue, ctx: SpendContext) -> Decision:
    hits: list[RuleHit] = []

    def hit(rule: str, outcome: Outcome, message: str) -> None:
        hits.append(RuleHit(rule, outcome, message))

    # --- Rule 0: the order must be well formed and refer to real catalogue items
    if not draft.lines:
        hit("valid_order", Outcome.BLOCK, "The order has no items.")
    supplier = catalogue.suppliers.get(draft.supplier_id)
    if supplier is None:
        hit("valid_order", Outcome.BLOCK, f"Supplier '{draft.supplier_id}' is not in the catalogue.")
    for line in draft.lines:
        item = catalogue.items.get(line.item_id)
        if line.qty <= 0:
            hit("valid_order", Outcome.BLOCK, f"Quantity for '{line.item_id}' must be at least 1.")
        if item is None:
            hit("valid_order", Outcome.BLOCK, f"Item '{line.item_id}' is not in the catalogue.")
        elif item.supplier_id != draft.supplier_id:
            hit("valid_order", Outcome.BLOCK,
                f"Item '{item.name}' is not sold by supplier '{draft.supplier_id}'.")

    total = order_total_inr(draft, catalogue)

    # --- Rule 1: approved vendor
    if supplier is not None and (not supplier.approved or supplier.id not in policy.approved_vendors):
        hit("approved_vendor", Outcome.BLOCK, f"{supplier.name} is not an approved supplier.")

    # --- Rule 2: allowed categories
    for line in draft.lines:
        item = catalogue.items.get(line.item_id)
        if item is not None and item.category not in policy.allowed_categories:
            hit("allowed_category", Outcome.BLOCK,
                f"Category '{item.category}' ({item.name}) is not allowed.")

    # --- Rule 3: monthly budget
    month_budget = policy.budget_for(ctx.now)
    remaining = month_budget - ctx.spent_this_month_inr
    if total > remaining:
        raised = (f" (this month's budget is raised to ₹{month_budget:,.0f})"
                  if policy.is_raised(ctx.now) else "")
        hit("monthly_budget", Outcome.BLOCK,
            f"Order of ₹{total:,.0f} exceeds the remaining monthly budget of ₹{max(remaining, 0):,.0f}{raised}.")

    # --- Rule 4: hard cap per order
    if total > policy.hard_cap_inr:
        hit("hard_cap", Outcome.BLOCK,
            f"Order of ₹{total:,.0f} is above the hard cap of ₹{policy.hard_cap_inr:,.0f} per order.")

    # --- Rule 5: auto-approve limit
    elif total > policy.auto_approve_limit_inr:
        hit("auto_approve_limit", Outcome.NEEDS_APPROVAL,
            f"Order of ₹{total:,.0f} is above the auto-approve limit of ₹{policy.auto_approve_limit_inr:,.0f}.")

    # --- Rule 6: price sanity against the usual price
    for line in draft.lines:
        item = catalogue.items.get(line.item_id)
        if item is None or item.usual_price_inr <= 0:
            continue
        change_pct = (item.unit_price_inr - item.usual_price_inr) / item.usual_price_inr * 100
        if change_pct > policy.price_tolerance_pct:
            hit("price_check", Outcome.NEEDS_APPROVAL,
                f"{item.name} costs ₹{item.unit_price_inr:,.0f}, {change_pct:.0f}% above its usual ₹{item.usual_price_inr:,.0f}.")

    # --- Rule 7: duplicate order in the recent window
    window_start = ctx.now - timedelta(hours=policy.duplicate_window_hours)
    item_ids = frozenset(l.item_id for l in draft.lines)
    for past in ctx.recent_orders:
        if (past.created_at >= window_start and past.supplier_id == draft.supplier_id
                and past.item_ids == item_ids and past.status not in ("REJECTED", "BLOCKED", "FAILED")):
            hit("duplicate", Outcome.NEEDS_APPROVAL,
                f"A matching order to the same supplier was placed in the last {policy.duplicate_window_hours} hours.")
            break

    # --- Rule 8: daily order count
    if ctx.orders_today >= policy.max_orders_per_day:
        hit("daily_limit", Outcome.NEEDS_APPROVAL,
            f"Already {ctx.orders_today} orders today; the daily limit is {policy.max_orders_per_day}.")

    # --- Rule 9: the agent must explain itself
    if not draft.reasoning.strip():
        hit("reasoning", Outcome.NEEDS_APPROVAL, "The agent gave no reasoning for this order.")

    outcome = Outcome.APPROVE
    for h in hits:
        if _SEVERITY[h.outcome] > _SEVERITY[outcome]:
            outcome = h.outcome
    return Decision(outcome=outcome, total_inr=total, hits=tuple(hits))
