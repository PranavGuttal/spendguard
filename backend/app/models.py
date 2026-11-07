"""Database tables (SQLite via SQLModel)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def _ts(index: bool = False):
    # plain (naive, local-time) timestamps; newer SQLModel otherwise demands timezone-aware values
    return Field(default_factory=datetime.now, sa_column=Column(DateTime, index=index, nullable=False))


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    request_text: str
    supplier_id: str = ""
    total_inr: float = 0.0
    # DRAFT -> BLOCKED | PENDING_APPROVAL | PAYING -> PAID | FAILED ; PENDING_APPROVAL -> REJECTED
    status: str = "DRAFT"
    agent_reasoning: str = ""
    created_at: datetime = _ts(index=True)


class OrderLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    item_id: str
    item_name: str
    qty: int
    unit_price_inr: float


class Decision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    outcome: str
    rules_fired_json: str = "[]"
    decided_by: str = "policy"  # policy | owner
    note: str = ""
    at: datetime = _ts()


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    sender_batch_id: str = Field(index=True, unique=True)
    paypal_batch_id: str = ""
    receiver_email: str = ""
    amount_usd: float = 0.0
    status: str = "CREATED"  # CREATED | PENDING | SUCCESS | FAILED ...
    raw_json: str = "{}"
    at: datetime = _ts()
