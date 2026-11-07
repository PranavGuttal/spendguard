"""SpendGuard's core flow: request -> agent -> policy -> (maybe) PayPal payout.

The agent can only propose. Money moves in exactly one place: `_pay`, which is
reached only from an APPROVE decision or an owner's explicit approval."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

from sqlmodel import Session, select

from .agent import AgentResult, run_agent
from .config import Catalogue, Policy
from .llm import LLM
from .models import Decision, Order, OrderLine, Payment
from .paypal import Payer, PayPalError
from .policy import Outcome, PastOrder, SpendContext, evaluate
from .tools import ToolContext, month_spend_inr

ACTIVE = ("PAID", "PAYING", "PENDING_APPROVAL")
PAID_STATES = {"SUCCESS"}
FAILED_STATES = {"FAILED", "RETURNED", "BLOCKED", "DENIED", "REFUNDED", "REVERSED"}


class OrderNotFound(LookupError):
    pass


class InvalidState(ValueError):
    pass


class SpendGuardService:
    def __init__(self, catalogue: Catalogue, policy: Policy, llm_factory, payer_factory, engine,
                 poll_attempts: int = 3, poll_delay_s: float = 2.0):
        self.catalogue = catalogue
        self.policy = policy
        self._llm_factory = llm_factory
        self._payer_factory = payer_factory
        self._llm: LLM | None = None
        self._payer: Payer | None = None
        self.engine = engine
        self.poll_attempts = poll_attempts
        self.poll_delay_s = poll_delay_s

    # -- lazily built clients, so the API starts even before keys are set
    @property
    def llm(self) -> LLM:
        if self._llm is None:
            self._llm = self._llm_factory()
        return self._llm

    @property
    def payer(self) -> Payer:
        if self._payer is None:
            self._payer = self._payer_factory()
        return self._payer

    # ------------------------------------------------------------------ flow
    def submit_request(self, text: str, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        with Session(self.engine) as s:
            ctx = ToolContext(self.catalogue, self.policy, s, now)
            result: AgentResult = run_agent(text, self.llm, ctx)
            if result.draft is None:
                return {"order": None, "agent_message": result.message, "agent_steps": result.steps}

            decision = evaluate(result.draft, self.policy, self.catalogue, self._spend_context(s, now))
            order = Order(request_text=text, supplier_id=result.draft.supplier_id, total_inr=decision.total_inr,
                          agent_reasoning=result.draft.reasoning, created_at=now)
            order.status = {Outcome.APPROVE: "PAYING", Outcome.NEEDS_APPROVAL: "PENDING_APPROVAL",
                            Outcome.BLOCK: "BLOCKED"}[decision.outcome]
            s.add(order)
            s.commit()
            s.refresh(order)
            for line in result.draft.lines:
                item = self.catalogue.items.get(line.item_id)
                s.add(OrderLine(order_id=order.id, item_id=line.item_id, qty=line.qty,
                                item_name=item.name if item else f"(unknown) {line.item_id}",
                                unit_price_inr=item.unit_price_inr if item else 0.0))
            s.add(Decision(order_id=order.id, outcome=decision.outcome.value,
                           rules_fired_json=json.dumps(decision.to_dict()["rules_fired"]), decided_by="policy"))
            s.commit()

            if decision.outcome is Outcome.APPROVE:
                self._pay(s, order)
            return {"order": self.order_view(s, order.id), "agent_message": result.message,
                    "agent_steps": result.steps}

    def approve(self, order_id: int, note: str = "") -> dict:
        with Session(self.engine) as s:
            order = self._get(s, order_id)
            if order.status != "PENDING_APPROVAL":
                raise InvalidState(f"Order {order_id} is {order.status}; only PENDING_APPROVAL orders can be approved.")
            s.add(Decision(order_id=order.id, outcome="APPROVE", decided_by="owner", note=note))
            order.status = "PAYING"
            s.add(order)
            s.commit()
            self._pay(s, order)
            return self.order_view(s, order.id)

    def reject(self, order_id: int, note: str = "") -> dict:
        with Session(self.engine) as s:
            order = self._get(s, order_id)
            if order.status != "PENDING_APPROVAL":
                raise InvalidState(f"Order {order_id} is {order.status}; only PENDING_APPROVAL orders can be rejected.")
            s.add(Decision(order_id=order.id, outcome="REJECT", decided_by="owner", note=note))
            order.status = "REJECTED"
            s.add(order)
            s.commit()
            return self.order_view(s, order.id)

    def refresh_payment(self, order_id: int) -> dict:
        with Session(self.engine) as s:
            order = self._get(s, order_id)
            payment = s.exec(select(Payment).where(Payment.order_id == order.id)).first()
            if payment and payment.paypal_batch_id and order.status == "PAYING":
                self._poll(s, order, payment, attempts=1)
            return self.order_view(s, order.id)

    def reset_demo(self) -> None:
        """Delete all orders, decisions and payment records (sandbox demo only)."""
        with Session(self.engine) as s:
            for model in (Payment, Decision, OrderLine, Order):
                for row in s.exec(select(model)).all():
                    s.delete(row)
            s.commit()

    # --------------------------------------------------------------- payment
    def _pay(self, s: Session, order: Order) -> None:
        sender_batch_id = f"spendguard-order-{order.id}"  # idempotency key: one payout per order, ever
        existing = s.exec(select(Payment).where(Payment.sender_batch_id == sender_batch_id)).first()
        if existing is not None:
            return
        supplier = self.catalogue.suppliers[order.supplier_id]
        amount_usd = round(order.total_inr / self.policy.inr_per_usd, 2)
        payment = Payment(order_id=order.id, sender_batch_id=sender_batch_id,
                          receiver_email=supplier.paypal_email, amount_usd=amount_usd)
        s.add(payment)
        s.commit()
        try:
            resp = self.payer.create_payout(sender_batch_id, supplier.paypal_email, amount_usd,
                                            f"SpendGuard order #{order.id}: {order.request_text[:200]}")
        except PayPalError as exc:
            payment.status, payment.raw_json = "FAILED", json.dumps({"error": str(exc)})
            order.status = "FAILED"
            s.add(payment)
            s.add(order)
            s.commit()
            return
        header = resp.get("batch_header", {})
        payment.paypal_batch_id = header.get("payout_batch_id", "")
        payment.status = header.get("batch_status", "PENDING")
        payment.raw_json = json.dumps(resp)[:5000]
        s.add(payment)
        s.commit()
        self._poll(s, order, payment, attempts=self.poll_attempts)

    def _poll(self, s: Session, order: Order, payment: Payment, attempts: int) -> None:
        for i in range(attempts):
            try:
                data = self.payer.get_payout(payment.paypal_batch_id)
            except PayPalError:
                return
            items = data.get("items") or []
            item_status = (items[0].get("transaction_status") if items else "") or ""
            batch_status = data.get("batch_header", {}).get("batch_status", "")
            payment.status = item_status or batch_status or payment.status
            payment.raw_json = json.dumps(data)[:5000]
            if item_status in PAID_STATES:
                order.status = "PAID"
            elif item_status in FAILED_STATES or batch_status in ("DENIED", "CANCELED"):
                order.status = "FAILED"
            s.add(payment)
            s.add(order)
            s.commit()
            if order.status != "PAYING":
                return
            if i + 1 < attempts:
                time.sleep(self.poll_delay_s)

    # ----------------------------------------------------------------- reads
    def _spend_context(self, s: Session, now: datetime) -> SpendContext:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today = s.exec(select(Order).where(Order.created_at >= day_start, Order.status.in_(ACTIVE))).all()
        recent = []
        for o in s.exec(select(Order).where(Order.created_at >= now - timedelta(days=2))).all():
            ids = frozenset(l.item_id for l in s.exec(select(OrderLine).where(OrderLine.order_id == o.id)).all())
            recent.append(PastOrder(o.supplier_id, ids, o.total_inr, o.created_at, o.status))
        return SpendContext(spent_this_month_inr=month_spend_inr(s, now), orders_today=len(today),
                            recent_orders=tuple(recent), now=now)

    def _get(self, s: Session, order_id: int) -> Order:
        order = s.get(Order, order_id)
        if order is None:
            raise OrderNotFound(f"Order {order_id} not found")
        return order

    def order_view(self, s: Session, order_id: int) -> dict:
        o = self._get(s, order_id)
        sup = self.catalogue.suppliers.get(o.supplier_id)
        lines = s.exec(select(OrderLine).where(OrderLine.order_id == o.id)).all()
        decisions = s.exec(select(Decision).where(Decision.order_id == o.id).order_by(Decision.at)).all()
        pay = s.exec(select(Payment).where(Payment.order_id == o.id)).first()
        return {
            "id": o.id, "request_text": o.request_text, "status": o.status, "total_inr": o.total_inr,
            "supplier": {"id": o.supplier_id, "name": sup.name if sup else o.supplier_id,
                         "approved": bool(sup and sup.approved)},
            "lines": [{"item_id": l.item_id, "name": l.item_name, "qty": l.qty, "unit_price_inr": l.unit_price_inr,
                       "line_total_inr": l.qty * l.unit_price_inr} for l in lines],
            "agent_reasoning": o.agent_reasoning,
            "decisions": [{"outcome": d.outcome, "decided_by": d.decided_by, "note": d.note,
                           "rules_fired": json.loads(d.rules_fired_json), "at": d.at.isoformat(timespec="seconds")}
                          for d in decisions],
            "payment": None if pay is None else {
                "paypal_batch_id": pay.paypal_batch_id, "amount_usd": pay.amount_usd, "status": pay.status,
                "receiver_email": pay.receiver_email},
            "created_at": o.created_at.isoformat(timespec="seconds"),
        }

    def list_orders(self) -> list[dict]:
        with Session(self.engine) as s:
            ids = [o.id for o in s.exec(select(Order).order_by(Order.created_at.desc())).all()]
            return [self.order_view(s, i) for i in ids]

    def budget(self, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        with Session(self.engine) as s:
            spent = month_spend_inr(s, now)
            held = sum(o.total_inr for o in s.exec(select(Order).where(Order.status == "PENDING_APPROVAL")).all())
            return {"monthly_budget_inr": self.policy.monthly_budget_inr, "spent_inr": spent,
                    "pending_approval_inr": held, "remaining_inr": self.policy.monthly_budget_inr - spent,
                    "auto_approve_limit_inr": self.policy.auto_approve_limit_inr,
                    "hard_cap_inr": self.policy.hard_cap_inr}

    def audit(self) -> list[dict]:
        with Session(self.engine) as s:
            rows = s.exec(select(Decision).order_by(Decision.at.desc())).all()
            return [{"order_id": d.order_id, "outcome": d.outcome, "decided_by": d.decided_by, "note": d.note,
                     "rules_fired": json.loads(d.rules_fired_json), "at": d.at.isoformat(timespec="seconds")}
                    for d in rows]
