import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone

import httpx
import psycopg

SCHEMA = """
CREATE TABLE IF NOT EXISTS monitors (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    webhook_url TEXT NOT NULL,
    last_price DOUBLE PRECISION,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    monitor_id TEXT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    price DOUBLE PRECISION,
    currency TEXT,
    captured_at TIMESTAMPTZ NOT NULL,
    source_url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history_monitor_captured
    ON price_history (monitor_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS api_accounts (
    api_key_hash TEXT PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free',
    credits_balance INTEGER NOT NULL DEFAULT 100,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    api_key_hash TEXT PRIMARY KEY,
    key_prefix TEXT NOT NULL,
    account_key_hash TEXT NOT NULL REFERENCES api_accounts(api_key_hash) ON DELETE CASCADE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_api_keys_account
    ON api_keys (account_key_hash, created_at DESC);

CREATE TABLE IF NOT EXISTS api_usage (
    id BIGSERIAL PRIMARY KEY,
    api_key_hash TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    credits INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_usage_key_created
    ON api_usage (api_key_hash, created_at DESC);
"""

def _db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url

def _account_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

def _init(conn):
    conn.execute(SCHEMA)
    master_key = os.getenv("EC_PULSE_API_KEY")
    if master_key:
        key_hash = _account_hash(master_key)
        now = datetime.now(timezone.utc)
        conn.execute(
            """INSERT INTO api_accounts
               (api_key_hash, plan, credits_balance, created_at, updated_at)
               VALUES (%s, 'free', 100, %s, %s)
               ON CONFLICT (api_key_hash) DO NOTHING""",
            (key_hash, now, now),
        )
        conn.execute(
            """INSERT INTO api_keys
               (api_key_hash, key_prefix, account_key_hash, active, created_at)
               VALUES (%s, %s, %s, TRUE, %s)
               ON CONFLICT (api_key_hash) DO NOTHING""",
            (key_hash, master_key[:12], key_hash, now),
        )
    conn.commit()

def validate_api_key(api_key: str) -> bool:
    key_hash = _account_hash(api_key)
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        row = conn.execute(
            "SELECT active FROM api_keys WHERE api_key_hash = %s",
            (key_hash,),
        ).fetchone()
        if not row or not row[0]:
            return False
        now = datetime.now(timezone.utc)
        conn.execute(
            "UPDATE api_keys SET last_used_at = %s WHERE api_key_hash = %s",
            (now, key_hash),
        )
        conn.commit()
    return True

def ensure_api_account(api_key: str) -> dict:
    key_hash = _account_hash(api_key)
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        row = conn.execute(
            "SELECT plan, credits_balance, created_at, updated_at FROM api_accounts WHERE api_key_hash = %s",
            (key_hash,),
        ).fetchone()
        if not row:
            raise RuntimeError("API key is not provisioned")
    return {
        "plan": row[0],
        "credits_balance": row[1],
        "created_at": row[2].isoformat(),
        "updated_at": row[3].isoformat(),
    }

def create_api_key(plan: str = "free", credits: int = 100) -> dict:
    if plan not in {"free", "pro", "business"}:
        raise ValueError("plan must be free, pro, or business")
    if credits < 0:
        raise ValueError("credits must be non-negative")

    raw_key = f"ecp_live_{secrets.token_urlsafe(32)}"
    key_hash = _account_hash(raw_key)
    now = datetime.now(timezone.utc)

    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        conn.execute(
            """INSERT INTO api_accounts
               (api_key_hash, plan, credits_balance, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (key_hash, plan, credits, now, now),
        )
        conn.execute(
            """INSERT INTO api_keys
               (api_key_hash, key_prefix, account_key_hash, active, created_at)
               VALUES (%s, %s, %s, TRUE, %s)""",
            (key_hash, raw_key[:12], key_hash, now),
        )
        conn.commit()

    return {
        "api_key": raw_key,
        "key_prefix": raw_key[:12],
        "plan": plan,
        "credits_balance": credits,
        "created_at": now.isoformat(),
        "warning": "Store this API key securely. It will not be shown again.",
    }

def list_api_keys() -> list[dict]:
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        rows = conn.execute(
            """SELECT k.key_prefix, k.active, k.created_at, k.last_used_at, k.account_key_hash,
                      a.plan, a.credits_balance
               FROM api_keys k
               JOIN api_accounts a ON a.api_key_hash = k.account_key_hash
               ORDER BY k.created_at DESC"""
        ).fetchall()
    return [
        {
            "key_prefix": r[0],
            "active": r[1],
            "created_at": r[2].isoformat(),
            "last_used_at": r[3].isoformat() if r[3] else None,
            "plan": r[5],
            "credits_balance": r[6],
        }
        for r in rows
    ]

def revoke_api_key(api_key: str) -> bool:
    key_hash = _account_hash(api_key)
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        cur = conn.execute(
            "UPDATE api_keys SET active = FALSE WHERE api_key_hash = %s",
            (key_hash,),
        )
        conn.commit()
        return cur.rowcount > 0

def consume_credit(api_key: str, endpoint: str, credits: int = 1) -> dict:
    if credits < 1:
        raise ValueError("credits must be positive")
    key_hash = _account_hash(api_key)
    now = datetime.now(timezone.utc)
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        row = conn.execute(
            """SELECT a.credits_balance
               FROM api_accounts a
               JOIN api_keys k ON k.account_key_hash = a.api_key_hash
               WHERE k.api_key_hash = %s AND k.active = TRUE
               FOR UPDATE""",
            (key_hash,),
        ).fetchone()
        if not row:
            raise RuntimeError("Invalid or revoked API key")
        if row[0] < credits:
            raise RuntimeError("Insufficient API credits")
        remaining = row[0] - credits
        conn.execute(
            "UPDATE api_accounts SET credits_balance = %s, updated_at = %s WHERE api_key_hash = %s",
            (remaining, now, key_hash),
        )
        conn.execute(
            "UPDATE api_keys SET last_used_at = %s WHERE api_key_hash = %s",
            (now, key_hash),
        )
        conn.execute(
            "INSERT INTO api_usage (api_key_hash, endpoint, credits, created_at) VALUES (%s, %s, %s, %s)",
            (key_hash, endpoint, credits, now),
        )
        conn.commit()
    return {"credits_used": credits, "credits_remaining": remaining}

def get_account_usage(api_key: str) -> dict:
    key_hash = _account_hash(api_key)
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        account = conn.execute(
            "SELECT plan, credits_balance, created_at, updated_at FROM api_accounts WHERE api_key_hash = %s",
            (key_hash,),
        ).fetchone()
        if not account:
            raise RuntimeError("API key is not provisioned")
        rows = conn.execute(
            """SELECT endpoint, SUM(credits), COUNT(*)
               FROM api_usage WHERE api_key_hash = %s
               GROUP BY endpoint ORDER BY SUM(credits) DESC""",
            (key_hash,),
        ).fetchall()
    return {
        "plan": account[0],
        "credits_balance": account[1],
        "total_credits_used": sum(r[1] for r in rows),
        "created_at": account[2].isoformat(),
        "updated_at": account[3].isoformat(),
        "usage": [{"endpoint": r[0], "credits": r[1], "requests": r[2]} for r in rows],
    }

def create_monitor(url: str, interval_minutes: int, webhook_url: str) -> dict:
    now = datetime.now(timezone.utc)
    monitor_id = str(uuid.uuid4())
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        conn.execute(
            "INSERT INTO monitors (id, url, interval_minutes, webhook_url, created_at) VALUES (%s, %s, %s, %s, %s)",
            (monitor_id, url, interval_minutes, webhook_url, now),
        )
        conn.commit()
    return {"id": monitor_id, "url": url, "interval_minutes": interval_minutes, "webhook_url": webhook_url, "status": "active", "created_at": now.isoformat()}

def list_monitors() -> list[dict]:
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        rows = conn.execute(
            """SELECT id, url, interval_minutes, webhook_url, last_price, last_checked_at, created_at
               FROM monitors ORDER BY created_at DESC"""
        ).fetchall()
    return [
        {"id": r[0], "url": r[1], "interval_minutes": r[2], "webhook_url": r[3], "last_price": r[4], "last_checked_at": r[5].isoformat() if r[5] else None, "created_at": r[6].isoformat()}
        for r in rows
    ]

def _history_rows(conn, monitor_id: str, limit: int):
    return conn.execute(
        """SELECT price, currency, captured_at, source_url
           FROM price_history WHERE monitor_id = %s
           ORDER BY captured_at DESC LIMIT %s""",
        (monitor_id, limit),
    ).fetchall()

def get_price_history(monitor_id: str, limit: int = 100) -> dict:
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        monitor = conn.execute(
            "SELECT id, url, last_price, last_checked_at FROM monitors WHERE id = %s",
            (monitor_id,),
        ).fetchone()
        if not monitor:
            raise KeyError(monitor_id)
        rows = _history_rows(conn, monitor_id, limit)
    points = [{"price": r[0], "currency": r[1], "captured_at": r[2].isoformat(), "source_url": r[3]} for r in rows]
    numeric = [p["price"] for p in points if p["price"] is not None]
    current = numeric[0] if numeric else monitor[2]
    lowest = min(numeric) if numeric else None
    highest = max(numeric) if numeric else None
    first = numeric[-1] if numeric else None
    change_percent = round(((current - first) / first) * 100, 2) if first not in (None, 0) and current is not None else None
    return {
        "monitor": {"id": monitor[0], "url": monitor[1], "last_price": monitor[2], "last_checked_at": monitor[3].isoformat() if monitor[3] else None},
        "summary": {"points": len(points), "current_price": current, "lowest_price": lowest, "highest_price": highest, "change_percent": change_percent},
        "history": points,
    }

def get_price_opportunity(monitor_id: str, limit: int = 100) -> dict:
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        monitor = conn.execute(
            "SELECT id, url, last_price, last_checked_at FROM monitors WHERE id = %s",
            (monitor_id,),
        ).fetchone()
        if not monitor:
            raise KeyError(monitor_id)
        rows = _history_rows(conn, monitor_id, limit)
    prices = [r[0] for r in rows if r[0] is not None]
    current = prices[0] if prices else monitor[2]
    lowest = min(prices) if prices else None
    highest = max(prices) if prices else None
    baseline = sum(prices) / len(prices) if prices else None
    discount_vs_high = round(((highest - current) / highest) * 100, 2) if highest and current is not None else None
    discount_vs_average = round(((baseline - current) / baseline) * 100, 2) if baseline and current is not None else None
    is_historical_low = bool(current is not None and lowest is not None and current <= lowest)
    signal = "historical_low" if is_historical_low else "below_average" if discount_vs_average and discount_vs_average > 10 else "normal"
    return {
        "monitor_id": monitor_id,
        "url": monitor[1],
        "current_price": current,
        "currency": rows[0][1] if rows else None,
        "metrics": {
            "historical_low": lowest,
            "historical_high": highest,
            "average_price": round(baseline, 2) if baseline is not None else None,
            "discount_vs_high_percent": discount_vs_high,
            "discount_vs_average_percent": discount_vs_average,
        },
        "signal": signal,
        "captured_at": monitor[3].isoformat() if monitor[3] else None,
    }

async def run_due_monitors() -> dict:
    from app.services.product_parser import fetch_product
    now = datetime.now(timezone.utc)
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        rows = conn.execute(
            """SELECT id, url, interval_minutes, webhook_url, last_price
               FROM monitors
               WHERE last_checked_at IS NULL
                  OR last_checked_at <= %s - (interval_minutes * INTERVAL '1 minute')""",
            (now,),
        ).fetchall()
    checked = changed = failed = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for monitor_id, url, interval, webhook_url, old_price in rows:
            try:
                data = await fetch_product(url)
                pricing = data.get("pricing", {})
                new_price = pricing.get("price")
                currency = pricing.get("currency")
                source = data.get("source", {})
                source_url = source.get("url") or url
                if old_price is not None and new_price is not None and new_price != old_price:
                    event = {
                        "event": "price_changed", "monitor_id": monitor_id,
                        "old_price": old_price, "new_price": new_price,
                        "change_amount": round(new_price - old_price, 2),
                        "change_percent": round(((new_price - old_price) / old_price) * 100, 2) if old_price else None,
                        "direction": "down" if new_price < old_price else "up",
                        "currency": currency, "url": url,
                        "source": {"site": source.get("site"), "url": source_url},
                        "captured_at": data["captured_at"],
                    }
                    response = await client.post(webhook_url, json=event)
                    response.raise_for_status()
                    changed += 1
                with psycopg.connect(_db_url()) as conn:
                    conn.execute(
                        """INSERT INTO price_history
                           (monitor_id, price, currency, captured_at, source_url)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (monitor_id, new_price, currency, data["captured_at"], source_url),
                    )
                    conn.execute(
                        "UPDATE monitors SET last_price = %s, last_checked_at = %s WHERE id = %s",
                        (new_price, now, monitor_id),
                    )
                    conn.commit()
                checked += 1
            except Exception:
                failed += 1
    return {"checked": checked, "changed": changed, "failed": failed}
