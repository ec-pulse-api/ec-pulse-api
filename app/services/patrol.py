import json
import os
from datetime import datetime, timezone

import httpx
import psycopg

from app.services.product_search import search_products
from app.services.monitor_store import run_due_monitors, _db_url
from app.services.patrol_ai import diagnose


def _store_report(report: dict) -> None:
    with psycopg.connect(_db_url(), connect_timeout=3) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patrol_reports (
                id BIGSERIAL PRIMARY KEY,
                checked_at TIMESTAMPTZ NOT NULL,
                ok BOOLEAN NOT NULL,
                report JSONB NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO patrol_reports (checked_at, ok, report) VALUES (%s, %s, %s)",
            (report["checked_at"], report["ok"], json.dumps(report, ensure_ascii=False)),
        )
        conn.commit()


async def _send_report(report: dict) -> bool:
    webhook = os.getenv("PATROL_REPORT_WEBHOOK_URL")
    if not webhook:
        return True
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.post(webhook, json=report)
            response.raise_for_status()
        return True
    except Exception:
        return False


async def _observe() -> tuple[list[dict], dict | None, list[str]]:
    checks: list[dict] = []
    queries = [
        "日焼け止め レディース",
        "UVカット 日焼け対策",
        "夏 レディース UV",
        "日焼け対策 グッズ レディース",
        "UVカット アームカバー",
    ]
    try:
        with psycopg.connect(_db_url(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        checks.append({"name": "database", "ok": True})
    except Exception as exc:
        checks.append({"name": "database", "ok": False, "error": type(exc).__name__})

    search_result = None
    errors: list[str] = []
    for query in queries:
        try:
            result = await search_products(query, ["amazon", "rakuten", "yahoo"], 3)
            items = result.get("results", result.get("items", [])) if isinstance(result, dict) else []
            if items:
                search_result = {"query": query, "count": len(items)}
                break
        except Exception as exc:
            errors.append(type(exc).__name__)
    if search_result:
        checks.append({"name": "product-search", "ok": True, **search_result})
    else:
        checks.append({
            "name": "product-search",
            "ok": False,
            "error": "all smoke-test queries returned zero products",
            "exceptions": errors[-3:],
        })

    try:
        monitor_result = await run_due_monitors()
        checks.append({"name": "monitors", "ok": True, "result": monitor_result})
    except Exception as exc:
        checks.append({"name": "monitors", "ok": False, "error": type(exc).__name__})
    return checks, search_result, errors


async def _apply_actions(actions: list[str], checks: list[dict], repairs: list[dict]) -> None:
    if "retry_search" in actions:
        try:
            retry = await search_products(
                "UVカット レディース 日焼け対策",
                ["amazon", "rakuten", "yahoo"],
                3,
            )
            items = retry.get("results", retry.get("items", [])) if isinstance(retry, dict) else []
            repairs.append({
                "type": "ai-search-retry",
                "action": "retry_search",
                "count": len(items),
                "ok": bool(items),
            })
        except Exception as exc:
            repairs.append({
                "type": "ai-search-retry-failure",
                "action": "escalate",
                "error": type(exc).__name__,
            })

    if "retry_monitors" in actions:
        try:
            retry_result = await run_due_monitors()
            repairs.append({
                "type": "ai-monitor-retry",
                "action": "retry_monitors",
                "result": retry_result,
                "ok": True,
            })
        except Exception as exc:
            repairs.append({
                "type": "ai-monitor-retry-failure",
                "action": "escalate",
                "error": type(exc).__name__,
            })


async def run_patrol() -> dict:
    repairs: list[dict] = []
    rounds: list[dict] = []
    checks: list[dict] = []
    diagnosis: dict = {}

    # Bounded autonomous loop: observe -> diagnose -> repair -> re-observe.
    # A maximum of two repair rounds prevents runaway retries.
    for round_no in range(1, 3):
        checks, search_result, errors = await _observe()
        diagnosis = await diagnose(checks, repairs)
        actions = [a for a in diagnosis.get("actions", []) if a in {
            "retry_search", "retry_monitors", "refresh_report", "escalate"
        }]
        round_record = {
            "round": round_no,
            "checks": checks,
            "diagnosis": diagnosis,
            "actions": actions,
            "repaired": False,
        }

        if not any(not item.get("ok") for item in checks):
            rounds.append(round_record)
            break
        if not actions or all(a in {"refresh_report", "escalate"} for a in actions):
            rounds.append(round_record)
            break
        if round_no == 2:
            rounds.append(round_record)
            break

        before_repairs = len(repairs)
        await _apply_actions(actions, checks, repairs)
        round_record["repaired"] = len(repairs) > before_repairs
        rounds.append(round_record)

    failures = [item for item in checks if item.get("ok") is False]
    report = {
        "ok": not failures,
        "agent": "patrol-ai",
        "mode": "observe-diagnose-repair-reaudit-report",
        "repair_policy": "allowlisted-retry-only",
        "max_repair_rounds": 2,
        "rounds": rounds,
        "ai_diagnosis": diagnosis,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "repairs": repairs,
        "failures": failures,
        "summary": (
            "巡回正常。修復不要。"
            if not failures and not repairs
            else "巡回完了。修復・再監査を実施しました。"
            if not failures
            else "巡回完了。修復後も異常が残っているため要監視です。"
        ),
    }
    try:
        _store_report(report)
    except Exception as exc:
        report["ok"] = False
        report["repairs"].append({
            "type": "report-persistence-failure",
            "action": "escalate",
            "error": type(exc).__name__,
        })
        report["failures"].append({
            "name": "report-persistence",
            "ok": False,
            "error": type(exc).__name__,
        })

    delivered = await _send_report(report)
    report["report_delivery"] = {
        "webhook_configured": bool(os.getenv("PATROL_REPORT_WEBHOOK_URL")),
        "delivered": delivered,
    }
    if not delivered:
        report["ok"] = False
        report["repairs"].append({
            "type": "report-delivery-failure",
            "action": "escalate",
            "error": "webhook_delivery_failed",
        })
        report["failures"].append({
            "name": "report-delivery",
            "ok": False,
            "error": "webhook_delivery_failed",
        })
    return report
