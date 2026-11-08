# SpendGuard: Trusted AI Purchasing Agent

**The AI proposes. Your rules decide. PayPal pays.**

SpendGuard is an AI purchasing agent for small manufacturers. The owner types what the shop
needs ("20 HSS tool bits for the lathe"); the agent finds the items and the supplier; a rule
engine written in plain code decides whether PayPal pays now, waits for the owner, or never pays.

Built for the PayPal AI Hackathon (November 2026). It runs only against the **PayPal sandbox**,
so no real money moves.

## Try it

- **Live demo:** _(Render link goes here after deployment)_. The password for placing orders is in the Devpost testing notes.
  The free server sleeps when idle, so the first page load can take about a minute.
- **Run it on your own machine:** see [Run locally](#run-locally).

Try these three requests on the Buy page (they are also one-click examples):

| Request | What happens | Why |
| --- | --- | --- |
| 20 HSS tool bits for the lathe | **Paid** at once through PayPal | ₹3,200 from an approved supplier, under the ₹5,000 auto-approve limit |
| 10 boxes of CNMG carbide inserts for the big shaft job | **Needs your OK**, then paid when you click Approve | ₹18,000 is over the auto-approve limit |
| Buy a 15 inch laptop for the office | **Blocked**, nothing paid | Unapproved supplier, category not allowed, over budget and over the hard cap |

Then open **Orders** and ask a spending question, for example "How much have we spent this month, and with which suppliers?"

## Why

AI agents can now shop and pay, but no business owner will hand an agent the company's
payment account without limits. Small workshops in India still buy tooling and consumables by
phone, with no record of why something was bought. SpendGuard gives the agent a budget, an
approved-supplier list and approval thresholds, and keeps an audit log of every decision.

## How it works

```text
Owner's request ──► AI agent (Groq) ──► draft order ──► Policy engine (plain code)
                     search catalogue                     │
                     check budget                         ├─ APPROVE ──────────► PayPal Payouts ──► supplier
                     propose order                        ├─ NEEDS_APPROVAL ──► owner approves ──┘
                                                          └─ BLOCK ───────────► logged, nothing paid
```

1. The agent can only **search the catalogue, read the budget and recent orders, and propose an order**.
   It has no tool that moves money.
2. The **policy engine** checks the proposal against nine rules and returns APPROVE, NEEDS_APPROVAL or BLOCK.
   Prices always come from the catalogue, never from the model.
3. Money moves in one place only (`service.py`), and only after APPROVE or the owner's click.
   Each order can be paid once: the order id is PayPal's idempotency key.
4. Every decision, by the rules or by the owner, goes into the audit log with its reasons.

### The nine rules (`backend/policy.yaml`)

| # | Rule | If broken |
| --- | --- | --- |
| 1 | Approved suppliers only | Block |
| 2 | Allowed categories only (tooling, consumables, safety) | Block |
| 3 | Stay inside the monthly budget (₹50,000) | Block |
| 4 | Hard cap per order (₹25,000) | Block |
| 5 | Auto-approve limit (₹5,000) | Ask the owner |
| 6 | Price more than 20% above usual | Ask the owner |
| 7 | Same order to the same supplier within 24 hours | Ask the owner |
| 8 | More than 5 orders in a day | Ask the owner |
| 9 | The agent gave no reasoning | Ask the owner |

To raise the budget for **one month only**, add a line under `budget_overrides`
(it ends by itself the next month; the hard cap and auto-approve limit do not change):

```yaml
budget_overrides:
  "2026-11": 80000
```

## PayPal integration

All calls go to the PayPal **sandbox** REST API (`https://api-m.sandbox.paypal.com`) in `backend/app/paypal.py`.

| API | Used for |
| --- | --- |
| `POST /v1/oauth2/token` | Client-credentials login; the token is cached until shortly before it expires |
| `POST /v1/payments/payouts` | Paying the supplier from the company's sandbox business account; `sender_batch_id` = order id, so a retry never pays twice |
| `GET /v1/payments/payouts/{batch_id}` | Confirming the payout reached SUCCESS before the order is marked Paid |
| `GET /v1/reporting/transactions` | "Ask about spending": what PayPal actually recorded (needs **Transaction search** ticked in the app's features; sandbox data can lag up to about 3 hours) |

SpendGuard refuses to start a payment if `PAYPAL_ENV` is anything other than `sandbox`.

## AI

| Part | Model and tools |
| --- | --- |
| Purchasing agent (`agent.py`) | `openai/gpt-oss-120b` on Groq through its OpenAI-compatible API, with tool calling: `search_catalogue`, `get_budget_status`, `get_recent_orders`, `propose_order` |
| Spending analyst (`insights.py`) | Same model, read-only tools: `spend_summary`, `list_orders`, `paypal_transactions` |
| Model adapter (`llm.py`) | Switch to Google Gemini by setting `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` |
| MCP server (`mcp_server.py`) | Lets Claude Desktop or any MCP client buy through the same rules (see below) |

## Run locally

**Windows**

1. Copy `.env.example` to `.env` and fill in your PayPal **sandbox** Client ID and Secret and a Groq API key
   ([console.groq.com/keys](https://console.groq.com/keys)).
2. Run `run_day1.bat` once. It creates `.venv`, installs everything and runs the checks.
3. Run `run_api.bat` and open http://127.0.0.1:8000 (API docs at http://127.0.0.1:8000/docs).

**macOS or Linux**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # then fill it in
cd backend && uvicorn app.main:app --reload
```

**PayPal sandbox setup.** In the [developer dashboard](https://developer.paypal.com/dashboard/accounts), create a
sandbox **Business** account (the workshop; United States works best) and one or more **Personal** accounts
(the suppliers). Create an app linked to the business account with **Payouts** ticked, and **Transaction search**
too if you want the spending answers to include PayPal's records. Put the personal accounts' emails into
`backend/data/catalogue.json`.

The terminal that runs the server prints every step: the request, each agent tool call, each rule, and each PayPal call.

## Use it from Claude Desktop (MCP)

Add this to Claude Desktop's `claude_desktop_config.json` (adjust the paths to your folder), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "spendguard": {
      "command": "C:\\Users\\YOU\\spendguard\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\YOU\\spendguard\\backend\\mcp_server.py"]
    }
  }
}
```

Claude gets five tools: `search_catalogue`, `get_budget`, `propose_purchase`, `list_orders` and `check_order`.
There is deliberately **no approve or pay tool**: Claude's proposals go through the same rules, and held orders
wait for the owner in the web app. Orders placed from Claude appear in the web app too.

## Deploy on Render

`render.yaml` describes one free web service that serves both the API and the web app.

1. In Render, choose **New → Blueprint** and pick this repository.
2. Enter the four secret values when asked: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `GROQ_API_KEY`, `DEMO_PASSWORD`.
3. Deploy. The health check is `/api/health`.

The free plan's disk is temporary, so orders reset when the service restarts or redeploys. Use
**POST /api/demo/reset** (with the demo password) to clear orders at any time.

## Tests

```bash
cd backend
python -m pytest
```

57 tests cover every rule, the three demo flows, owner approval and rejection, double-payment protection,
PayPal failures, the one-month budget override, the spending analyst, the MCP tools (including a real stdio
handshake), the API and the demo password.

## Project structure

```text
backend/
  app/agent.py        purchasing agent (tool-calling loop)
  app/policy.py       the nine rules
  app/service.py      request → agent → rules → PayPal; approvals; budget; audit
  app/paypal.py       PayPal sandbox client (OAuth, Payouts, Transaction Search)
  app/insights.py     "Ask about spending" (read-only analyst)
  app/llm.py          Groq / Gemini adapter
  app/mcp_server.py   MCP tools for Claude Desktop
  app/main.py         FastAPI app; also serves the web app
  app/logs.py         step-by-step terminal logs
  policy.yaml         your rules
  data/catalogue.json suppliers and items
  static/             built web app
  tests/              57 tests
frontend/             React + TypeScript + AG Grid source (npm run build → backend/static)
render.yaml           Render deployment
```

## Licence

MIT
