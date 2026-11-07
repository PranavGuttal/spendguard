# SpendGuard: Trusted AI Purchasing Agent

An AI purchasing agent that buys supplies for small manufacturers through PayPal,
within the budgets, approved vendors and approval rules you set.

**The AI proposes. Your rules decide. PayPal pays.**

> Built for the PayPal AI Hackathon (Nov 2026). Runs only against the PayPal **sandbox**; no real money moves.

## Run it on Windows

1. Copy `.env.example` to `.env` and fill in your PayPal **sandbox** Client ID and Secret and a Groq API key.
2. Double-click or run `run_day1.bat` once: it creates `.venv`, installs everything and runs the checks.
3. Start the app:

```
.\run_api.bat
```

4. Open **http://127.0.0.1:8000** for the app, or **http://127.0.0.1:8000/docs** for the API.

Try these three requests:

| Request | What happens |
| --- | --- |
| 20 HSS tool bits for the lathe | Under ₹5,000 from an approved supplier, so PayPal pays at once |
| 10 boxes of CNMG carbide inserts for the big shaft job | Over the auto-approve limit, so it waits in Approvals until you approve |
| Buy a 15 inch laptop for the office | Unapproved supplier and category, over budget and cap, so it is blocked |

## How it is built

- `backend/app/agent.py`: the AI agent (Llama on Groq). It can search the catalogue and propose an order. It cannot pay.
- `backend/app/policy.py`: nine plain-code rules that return APPROVE, NEEDS_APPROVAL or BLOCK.
- `backend/app/service.py`: the only place money moves, and only after APPROVE or the owner's click.
- `backend/app/paypal.py`: PayPal Payouts (sandbox), one payout per order (the order id is the idempotency key).
- `frontend/`: the React web app (AG Grid for tables). `npm run build` writes it to `backend/static`.
- `backend/policy.yaml` and `backend/data/catalogue.json`: the rules and the supplier catalogue.

Run the tests: `cd backend` then `..\.venv\Scripts\python.exe -m pytest`.

## Licence

MIT
