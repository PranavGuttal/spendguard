"""Loads the policy file and the supplier catalogue."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
POLICY_PATH = BACKEND_DIR / "policy.yaml"
CATALOGUE_PATH = BACKEND_DIR / "data" / "catalogue.json"


@dataclass(frozen=True)
class Policy:
    monthly_budget_inr: float
    auto_approve_limit_inr: float
    hard_cap_inr: float
    max_orders_per_day: int
    price_tolerance_pct: float
    duplicate_window_hours: int
    approved_vendors: frozenset[str]
    allowed_categories: frozenset[str]
    inr_per_usd: float = 88.0

    @classmethod
    def from_dict(cls, d: dict) -> "Policy":
        return cls(
            monthly_budget_inr=float(d["monthly_budget_inr"]),
            auto_approve_limit_inr=float(d["auto_approve_limit_inr"]),
            hard_cap_inr=float(d["hard_cap_inr"]),
            max_orders_per_day=int(d["max_orders_per_day"]),
            price_tolerance_pct=float(d["price_tolerance_pct"]),
            duplicate_window_hours=int(d.get("duplicate_window_hours", 24)),
            approved_vendors=frozenset(d["approved_vendors"]),
            allowed_categories=frozenset(d["allowed_categories"]),
            inr_per_usd=float(d.get("inr_per_usd", 88.0)),
        )


@dataclass(frozen=True)
class Supplier:
    id: str
    name: str
    paypal_email: str
    categories: tuple[str, ...]
    approved: bool
    city: str = ""


@dataclass(frozen=True)
class Item:
    id: str
    supplier_id: str
    name: str
    category: str
    unit: str
    unit_price_inr: float
    usual_price_inr: float


@dataclass
class Catalogue:
    suppliers: dict[str, Supplier] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Catalogue":
        suppliers = {
            s["id"]: Supplier(
                id=s["id"], name=s["name"], paypal_email=s["paypal_email"],
                categories=tuple(s.get("categories", [])), approved=bool(s.get("approved", False)),
                city=s.get("city", ""),
            )
            for s in d["suppliers"]
        }
        items = {
            i["id"]: Item(
                id=i["id"], supplier_id=i["supplier_id"], name=i["name"], category=i["category"],
                unit=i.get("unit", "piece"), unit_price_inr=float(i["unit_price_inr"]),
                usual_price_inr=float(i.get("usual_price_inr", i["unit_price_inr"])),
            )
            for i in d["items"]
        }
        return cls(suppliers=suppliers, items=items)


def load_policy(path: Path = POLICY_PATH) -> Policy:
    with open(path, encoding="utf-8") as fh:
        return Policy.from_dict(yaml.safe_load(fh))


def load_catalogue(path: Path = CATALOGUE_PATH) -> Catalogue:
    with open(path, encoding="utf-8") as fh:
        return Catalogue.from_dict(json.load(fh))
