"""Day 1 check: can the Groq model call a tool?

Run:  python groq_tool_test.py
Needs GROQ_API_KEY (and optionally GROQ_MODEL) in .env
"""
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GROQ_API_KEY")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
if not KEY:
    sys.exit("Fill GROQ_API_KEY in .env first.")

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_catalogue",
            "description": "Search the supplier catalogue for items matching a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look for, e.g. 'HSS tool bit'"},
                    "quantity": {"type": "integer", "description": "How many are needed"},
                },
                "required": ["query", "quantity"],
            },
        },
    }
]

r = httpx.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a purchasing agent for a small machine shop. Use tools."},
            {"role": "user", "content": "We need 20 HSS tool bits for the lathe by Friday."},
        ],
        "tools": tools,
        "tool_choice": "auto",
    },
    timeout=60,
)
if r.status_code >= 400:
    sys.exit(f"Groq error {r.status_code}: {r.text}\n-> If the model name is wrong, pick a tool-use model from console.groq.com/docs/models")

msg = r.json()["choices"][0]["message"]
calls = msg.get("tool_calls") or []
if not calls:
    print("Model replied without a tool call:", msg.get("content"))
else:
    for c in calls:
        print("Tool call OK:", c["function"]["name"], json.loads(c["function"]["arguments"]))
