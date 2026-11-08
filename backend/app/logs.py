"""Readable step-by-step logs in the terminal that runs the API.

Example:
  10:03:12  REQUEST   #  "20 HSS tool bits for the lathe"
  10:03:13  AGENT     search_catalogue(query='HSS tool bit') -> 3 results
  10:03:14  AGENT     propose_order: sharma-tools, 20 x hss-bit-10
  10:03:14  RULES     APPROVE  INR 3,200  (passed every rule)
  10:03:15  PAYPAL    payout created: USD 36.36 -> sb-...@personal.example.com
  10:03:18  PAYPAL    payout status: SUCCESS -> order #1 PAID
Secrets (keys, tokens) are never logged. Set LOG_LEVEL=WARNING in .env to quieten it.
"""
from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger("spendguard")


def setup_logging(stream=None) -> None:
    """Logs go to stdout for the web server. The MCP server passes stderr, because
    over stdio its stdout carries the MCP protocol itself."""
    if getattr(log, "_configured", False):
        return
    stream = stream or sys.stdout
    try:  # a Windows console that cannot print a character (e.g. ₹) must never crash the server
        stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    log.propagate = False
    log._configured = True  # type: ignore[attr-defined]


def step(kind: str, message: str) -> None:
    log.info("%-8s  %s", kind, message)


def inr(amount: float) -> str:
    return f"INR {amount:,.0f}"
