import json
import os
from typing import Any

import httpx


ALLOWED_ACTIONS = {
    "retry_search",
    "retry_monitors",
    "refresh_report",
    "escalate",
}


async def diagnose(checks: list[dict[str, Any]], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    """AI diagnosis with a safe rule-based fallback.

    If PATROL_AI_API_KEY and PATROL_AI_API_URL are configured, an
    OpenAI-compatible model chooses only from ALLOWED_ACTIONS.
    Otherwise the deterministic fallback remains fully operational.
    """
    api_key = os.getenv("PATROL_AI_API_KEY")
    api_url = os.getenv("PATROL_AI_API_URL")
    model = os.getenv("PATROL_AI_MODEL", "gpt-4o-mini")
    fallback = _fallback(checks, repairs)
    if not api_key or not api_url:
        return {**fallback, "engine": "safe-fallback"}

    prompt = {
        "role": "production reliability patrol agent",
        "rules": [
            "Diagnose only from supplied observations.",
            "Never invent infrastructure state.",
            "Choose only allowed actions.",
            "Never execute arbitrary code.",
            "Prefer retry before escalation.",
        ],
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "checks": checks,
        "repairs": repairs,
        "output": {"diagnosis": "string", "actions": ["allowed_action"], "confidence": "number 0..1"},
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": "Return JSON only."},
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            decision = json.loads(content)
            actions = [a for a in decision.get("actions", []) if a in ALLOWED_ACTIONS]
            return {
                "engine": "llm",
                "model": model,
                "diagnosis": str(decision.get("diagnosis", ""))[:1000],
                "actions": actions[:3],
                "confidence": max(0.0, min(1.0, float(decision.get("confidence", 0.0)))),
            }
    except Exception as exc:
        return {**fallback, "engine": "safe-fallback", "llm_error": type(exc).__name__}


def _fallback(checks: list[dict[str, Any]], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [c for c in checks if not c.get("ok")]
    actions: list[str] = []
    if any(c.get("name") == "product-search" and not c.get("ok") for c in failed):
        actions.append("retry_search")
    if any(c.get("name") == "monitors" and not c.get("ok") for c in failed):
        actions.append("retry_monitors")
    if not actions and repairs:
        actions.append("refresh_report")
    if failed and not actions:
        actions.append("escalate")
    return {
        "engine": "rule",
        "diagnosis": " / ".join(str(c.get("name")) + " failed" for c in failed) or "No failed checks",
        "actions": actions,
        "confidence": 0.99 if not failed else 0.85,
    }
