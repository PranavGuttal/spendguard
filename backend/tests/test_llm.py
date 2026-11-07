"""LLM adapter: retries once on a malformed tool call, reports other errors clearly."""
import httpx
import pytest

from app.llm import LLMError, OpenAICompatibleLLM


class Resp:
    def __init__(self, code, payload=None, text=""):
        self.status_code, self._p, self.text = code, payload, text
    def json(self):
        return self._p


def test_retry_after_tool_use_failed(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    calls = iter([Resp(400, text='{"error":{"code":"tool_use_failed"}}'),
                  Resp(200, {"choices": [{"message": {"content": "ok"}}]})])
    monkeypatch.setattr(httpx, "post", lambda *a, **k: next(calls))
    assert OpenAICompatibleLLM("groq").chat([], [])["content"] == "ok"


def test_other_errors_are_reported(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Resp(401, text="invalid api key"))
    with pytest.raises(LLMError, match="401"):
        OpenAICompatibleLLM("groq").chat([], [])


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        OpenAICompatibleLLM("groq")


def test_paypal_refuses_live_mode(monkeypatch):
    from app.paypal import PayPalClient, PayPalError
    monkeypatch.setenv("PAYPAL_ENV", "live")
    with pytest.raises(PayPalError, match="sandbox"):
        PayPalClient()
