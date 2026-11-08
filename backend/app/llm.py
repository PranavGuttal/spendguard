"""LLM adapter. Groq by default, Gemini as a backup; both speak the
OpenAI chat-completions format, so switching is one setting (LLM_PROVIDER)."""
from __future__ import annotations

import os
import time
from typing import Any, Protocol

import httpx

from .logs import step

PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "default_model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
    },
}


class LLM(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> dict: ...


class LLMError(RuntimeError):
    pass


class OpenAICompatibleLLM:
    def __init__(self, provider: str | None = None, timeout: float = 60.0):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
        if self.provider not in PROVIDERS:
            raise LLMError(f"Unknown LLM_PROVIDER '{self.provider}'. Use one of {list(PROVIDERS)}.")
        cfg = PROVIDERS[self.provider]
        self.url = cfg["url"]
        self.key = os.getenv(cfg["key_env"], "")
        self.model = os.getenv(cfg["model_env"], cfg["default_model"])
        self.timeout = timeout
        if not self.key:
            raise LLMError(f"{cfg['key_env']} is not set in .env")

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        for attempt in range(2):
            started = time.monotonic()
            try:
                r = httpx.post(self.url, headers={"Authorization": f"Bearer {self.key}"}, json=body, timeout=self.timeout)
            except httpx.HTTPError as exc:
                raise LLMError(f"Could not reach {self.provider}: {exc}") from exc
            # Open models sometimes emit a malformed tool call (Groq: 'tool_use_failed'); one retry usually fixes it.
            took = time.monotonic() - started
            if r.status_code == 400 and "tool_use_failed" in r.text and attempt == 0:
                step("LLM", f"{self.model} sent a malformed tool call; retrying once")
                continue
            if r.status_code >= 400:
                step("LLM", f"{self.provider} error {r.status_code} after {took:.1f}s")
                raise LLMError(f"{self.provider} error {r.status_code}: {r.text[:300]}")
            usage = r.json().get("usage") or {}
            step("LLM", f"{self.provider}/{self.model} answered in {took:.1f}s"
                        + (f" ({usage.get('total_tokens')} tokens)" if usage.get("total_tokens") else ""))
            return r.json()["choices"][0]["message"]
        raise LLMError(f"{self.provider} could not produce a valid tool call")
