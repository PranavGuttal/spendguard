"""Start SpendGuard's MCP server over stdio (for Claude Desktop and other MCP clients).

Claude Desktop config (claude_desktop_config.json):
  "spendguard": {
    "command": "C:\\\\Users\\\\P\\\\Spend_Guard\\\\spendguard\\\\.venv\\\\Scripts\\\\python.exe",
    "args": ["C:\\\\Users\\\\P\\\\Spend_Guard\\\\spendguard\\\\backend\\\\mcp_server.py"]
  }
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND.parent / ".env")

from app.config import load_catalogue, load_policy  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.llm import OpenAICompatibleLLM  # noqa: E402
from app.logs import setup_logging, step  # noqa: E402
from app.mcp_server import build_server  # noqa: E402
from app.paypal import PayPalClient  # noqa: E402
from app.service import SpendGuardService  # noqa: E402


def main() -> None:
    setup_logging(stream=sys.stderr)  # stdout is the MCP channel
    init_db()
    service = SpendGuardService(load_catalogue(), load_policy(), OpenAICompatibleLLM, PayPalClient, engine)
    step("START", "SpendGuard MCP server ready (stdio). Purchases go through the same rules as the web app.")
    build_server(service).run("stdio")


if __name__ == "__main__":
    main()
