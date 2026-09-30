import json
import os
from typing import Any

import httpx

ALLOWED_ACTIONS = {"retry_search", "retry_monitors", "refresh_report", "escalate"}

def _provider_config() -> tuple[str | None, str | None, str]:
    api_key = os.getenv("PATROL_AI_API_KEY")
    api_url = os.getenv("PATROL_AI_API_URL")
    model = os.getenv("PATROL_AI_MODEL")
    if api_key and api_url:
        return api_key, api_url, model or "gpt-4o-mini"
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        return groq_key, os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"), model or "llama-3.3-70b-versatile"
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        return openai_key, os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"), model or "gpt-4o-mini"
    return None, None, model or "gpt-4o-mini"

async def diagnose(checks: list[dict[str, Any]], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    api_key, api_url, model = _provider_config()
    fallback = _fallback(checks, repairs)
    if not api_key or not api_url:
        return {**fallback, "engine": "safe-fallback", "provider_configured": False}
    prompt = {"role": "production reliability patrol agent", "rules": ["Diagnose only from supplied observations.", "Never invent infrastructure state.", "Choose only allowed actions.", "Never execute arbitrary code.", "Prefer a bounded retry before escalation.", "If checks are healthy, choose no repair action."], "allowed_actions": sorted(ALLOWED_ACTIONS), "checks": checks, "repairs": repairs, "output": {"diagnosis": "string", "actions": ["allowed_action"], "confidence": "number 0..1"}}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(api_url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "temperature": 0, "messages": [{"role": "system", "content": "You are a production reliability AI. Return valid JSON only. Never return markdown."}, {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]})
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            decision = json.loads(content.strip())
            actions = [action for action in decision.get("actions", []) if action in ALLOWED_ACTIONS]
            return {"engine": "llm", "provider": "custom" if os.getenv("PATROL_AI_API_KEY") else ("groq" if os.getenv("GROQ_API_KEY") else "openai"), "model": model, "diagnosis": str(decision.get("diagnosis", ""))[:1000], "actions": actions[:3], "confidence": max(0.0, min(1.0, float(decision.get("confidence", 0.0)))), "provider_configured": True}
    except Exception as exc:
        return {**fallback, "engine": "safe-fallback", "provider_configured": True, "llm_error": type(exc).__name__}

def _fallback(checks: list[dict[str, Any]], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if not check.get("ok")]
    actions: list[str] = []
    if any(check.get("name") == "product-search" for check in failed): actions.append("retry_search")
    if any(check.get("name") in {"monitors", "monitors-retry"} for check in failed): actions.append("retry_monitors")
    if not failed and repairs: actions.append("refresh_report")
    if failed and not actions: actions.append("escalate")
    return {"engine": "rule", "diagnosis": " / ".join(str(check.get("name")) + " failed" for check in failed) or "No failed checks", "actions": actions, "confidence": 0.99 if not failed else 0.85}