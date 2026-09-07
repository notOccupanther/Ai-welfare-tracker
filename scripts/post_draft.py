#!/usr/bin/env python3
"""
AI Welfare Watch — Daily Bluesky draft via Claude API → Telegram
Required env vars: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent / "data.json"


def load_stats():
    with open(DATA_PATH) as f:
        data = json.load(f)

    cases = data.get("cases", [])
    cats = {}
    for c in cases:
        cat = c.get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1

    dated = sorted(
        [c for c in cases if c.get("date")],
        key=lambda x: x["date"],
        reverse=True,
    )
    recent = [
        {"date": e["date"], "title": e.get("title", ""), "category": e.get("category", "")}
        for e in dated[:3]
    ]

    return {"total": len(cases), "categories": cats, "recent": recent}


def call_claude(stats: dict) -> str:
    api_key = os.environ["ANTHROPIC_API_KEY"]

    prompt = f"""You write social posts for AI Welfare Watch, a public tracker of AI welfare discourse.

Current data:
- Total cases: {stats['total']}
- Category counts: {json.dumps(stats['categories'])}
- 3 most recent entries: {json.dumps(stats['recent'], indent=2)}

Write ONE Bluesky post. Rules:
- Max 300 characters (count carefully)
- End with: aiwelfare.watch
- Tone: dry, public-interest, factual — not hype, not alarmist
- No hashtags
- Pick ONE angle: a stat, a category insight, a recent entry worth noting, or a framing observation about the debate
- Do not lead with "Half the entries are academic research"
- Output only the post text, nothing else"""

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )

    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)

    return result["content"][0]["text"].strip()


def send_telegram(text: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    body = json.dumps({
        "chat_id": chat_id,
        "text": f"AI Welfare Watch — Bluesky Draft\n\n{text}",
    }).encode()

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req) as resp:
        result = json.load(resp)

    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")

    print("Sent to Telegram ok")


def main():
    stats = load_stats()
    print(f"Stats: {stats['total']} cases, {len(stats['categories'])} categories")

    draft = call_claude(stats)
    print(f"\nDraft ({len(draft)} chars):\n{draft}\n")

    if len(draft) > 300:
        print("WARNING: draft exceeds 300 chars", file=sys.stderr)

    send_telegram(draft)


if __name__ == "__main__":
    main()
