"""SpendGuard API.

Run from the backend folder:   uvicorn app.main:app --reload
Then open http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import os
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # repo-root .env

from .config import load_catalogue, load_policy  # noqa: E402
from .db import engine, init_db  # noqa: E402
from .logs import setup_logging, step  # noqa: E402
from .llm import LLMError, OpenAICompatibleLLM  # noqa: E402
from .paypal import PayPalClient, PayPalError  # noqa: E402
from .service import InvalidState, OrderNotFound, SpendGuardService  # noqa: E402

service: SpendGuardService | None = None


def build_service() -> SpendGuardService:
    return SpendGuardService(load_catalogue(), load_policy(), OpenAICompatibleLLM, PayPalClient, engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    setup_logging()
    init_db()
    if service is None:
        service = build_service()
    for month, amount in sorted(service.policy.budget_overrides.items()):
        step("BUDGET", f"{month}: budget raised to INR {amount:,.0f} (normal INR {service.policy.monthly_budget_inr:,.0f})")
    step("START", f"SpendGuard ready: AI = {os.getenv('LLM_PROVIDER', 'groq')}, PayPal = {os.getenv('PAYPAL_ENV', 'sandbox')}. Open http://127.0.0.1:8000")
    yield


app = FastAPI(title="SpendGuard API", version="0.1.0", lifespan=lifespan,
              description="AI purchasing agent: the AI proposes, the rules decide, PayPal pays (sandbox).")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")],
    allow_methods=["*"], allow_headers=["*"],
)


def get_service() -> SpendGuardService:
    assert service is not None, "service not initialised"
    return service


def check_password(x_demo_password: str | None = Header(default=None)) -> None:
    expected = os.getenv("DEMO_PASSWORD", "")
    if expected and x_demo_password != expected:
        raise HTTPException(401, "Wrong or missing demo password (X-Demo-Password header).")


_REQUEST_TIMES: deque[float] = deque()
MAX_REQUESTS_PER_HOUR = int(os.getenv("MAX_REQUESTS_PER_HOUR", "20"))


def rate_limit() -> None:
    now = time.time()
    while _REQUEST_TIMES and now - _REQUEST_TIMES[0] > 3600:
        _REQUEST_TIMES.popleft()
    if len(_REQUEST_TIMES) >= MAX_REQUESTS_PER_HOUR:
        raise HTTPException(429, f"Demo limit reached: {MAX_REQUESTS_PER_HOUR} purchase requests an hour.")
    _REQUEST_TIMES.append(now)


class PurchaseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=500, examples=["20 HSS tool bits for the lathe"])


class OwnerNote(BaseModel):
    note: str = ""


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/requests", dependencies=[Depends(check_password), Depends(rate_limit)])
def create_request(body: PurchaseRequest, svc: SpendGuardService = Depends(get_service)):
    try:
        return svc.submit_request(body.text.strip())
    except LLMError as exc:
        step("ERROR", f"AI model error: {str(exc)[:200]}")
        raise HTTPException(502, f"AI model error: {exc}")
    except PayPalError as exc:
        raise HTTPException(502, f"PayPal error: {exc}")


@app.get("/api/orders")
def list_orders(svc: SpendGuardService = Depends(get_service)):
    return svc.list_orders()


@app.post("/api/orders/{order_id}/approve", dependencies=[Depends(check_password)])
def approve_order(order_id: int, body: OwnerNote | None = None, svc: SpendGuardService = Depends(get_service)):
    try:
        return svc.approve(order_id, (body or OwnerNote()).note)
    except OrderNotFound as exc:
        raise HTTPException(404, str(exc))
    except InvalidState as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/orders/{order_id}/reject", dependencies=[Depends(check_password)])
def reject_order(order_id: int, body: OwnerNote | None = None, svc: SpendGuardService = Depends(get_service)):
    try:
        return svc.reject(order_id, (body or OwnerNote()).note)
    except OrderNotFound as exc:
        raise HTTPException(404, str(exc))
    except InvalidState as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/orders/{order_id}/refresh")
def refresh_order(order_id: int, svc: SpendGuardService = Depends(get_service)):
    try:
        return svc.refresh_payment(order_id)
    except OrderNotFound as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/budget")
def budget(svc: SpendGuardService = Depends(get_service)):
    return svc.budget()


@app.get("/api/audit")
def audit(svc: SpendGuardService = Depends(get_service)):
    return svc.audit()


@app.get("/api/policy")
def policy(svc: SpendGuardService = Depends(get_service)):
    p = svc.policy
    from datetime import datetime
    now = datetime.now()
    return {"monthly_budget_inr": p.monthly_budget_inr, "this_month_budget_inr": p.budget_for(now),
            "budget_overrides": dict(sorted(p.budget_overrides.items())),
            "auto_approve_limit_inr": p.auto_approve_limit_inr,
            "hard_cap_inr": p.hard_cap_inr, "max_orders_per_day": p.max_orders_per_day,
            "price_tolerance_pct": p.price_tolerance_pct, "duplicate_window_hours": p.duplicate_window_hours,
            "approved_vendors": sorted(p.approved_vendors), "allowed_categories": sorted(p.allowed_categories),
            "inr_per_usd": p.inr_per_usd}


@app.get("/api/catalogue")
def catalogue(svc: SpendGuardService = Depends(get_service)):
    c = svc.catalogue
    return {"suppliers": [vars(s) for s in c.suppliers.values()], "items": [vars(i) for i in c.items.values()]}


@app.post("/api/demo/reset", dependencies=[Depends(check_password)])
def reset_demo(svc: SpendGuardService = Depends(get_service)):
    """Clear all orders so a judge can start fresh. Sandbox payouts already sent stay in PayPal."""
    svc.reset_demo()
    return {"ok": True}


# ---- the web app (built by `npm run build` in /frontend into backend/static) ----
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    page = STATIC_DIR / "index.html"
    if page.is_file():
        return FileResponse(page)
    return {"message": "SpendGuard API is running. Build the web app (frontend) or open /docs."}
