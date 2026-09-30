import os
from datetime import datetime, timezone
from app.services.product_search import search_products
from app.services.monitor_store import run_due_monitors


async def run_patrol() -> dict:
    checks = []
    repairs = []

    # 1. Database / application health
    try:
        import psycopg
        from app.services.monitor_store import _db_url
        with psycopg.connect(_db_url(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        checks.append({"name": "database", "ok": True})
    except Exception as exc:
        checks.append({"name": "database", "ok": False, "error": type(exc).__name__})

    # 2. Product discovery smoke test with bounded self-repair.
    # The patrol never charges a customer account because it calls the
    # internal search service directly.
    queries = [
        "日焼け止め レディース",
        "UVカット 日焼け対策",
        "夏 レディース UV",
    ]
    search_result = None
    for index, query in enumerate(queries):
        try:
            result = await search_products(query, ["amazon", "rakuten", "yahoo"], 3)
            items = result.get("results", result.get("items", [])) if isinstance(result, dict) else []
            if items:
                search_result = {"query": query, "count": len(items)}
                checks.append({"name": "product-search", "ok": True, **search_result})
                if index > 0:
                    repairs.append({
                        "type": "search-query-fallback",
                        "action": "alternate_query",
                        "query": query,
                        "reason": "primary smoke-test query returned no products",
                    })
                break
        except Exception as exc:
            if index == len(queries) - 1:
                checks.append({"name": "product-search", "ok": False, "error": type(exc).__name__})
    if search_result is None and not any(x["name"] == "product-search" for x in checks):
        checks.append({
            "name": "product-search",
            "ok": False,
            "error": "all smoke-test queries returned zero products",
        })
        repairs.append({
            "type": "search-degraded",
            "action": "escalate",
            "reason": "all bounded fallback queries returned zero products",
        })

    # 3. Monitor subsystem. Retry once as a bounded repair if the first pass fails.
    try:
        monitor_result = await run_due_monitors()
        checks.append({"name": "monitors", "ok": True, "result": monitor_result})
    except Exception as exc:
        checks.append({"name": "monitors", "ok": False, "error": type(exc).__name__})
        try:
            retry_result = await run_due_monitors()
            repairs.append({"type": "monitor-retry", "action": "retry_once", "result": retry_result})
            checks.append({"name": "monitors-retry", "ok": True, "result": retry_result})
        except Exception as retry_exc:
            repairs.append({
                "type": "monitor-failure",
                "action": "escalate",
                "error": type(retry_exc).__name__,
            })

    failures = [item for item in checks if item.get("ok") is False]
    return {
        "ok": not failures,
        "agent": "patrol-ai",
        "mode": "observe-repair-report",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "repairs": repairs,
        "failures": failures,
        "summary": (
            "巡回正常。修復不要。"
            if not failures and not repairs
            else "巡回完了。自己修復を実施または要監視状態を報告。"
        ),
    }
