import os
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
"""


def _db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def _init(conn):
    conn.execute(SCHEMA)
    conn.commit()


def create_monitor(url: str, interval_minutes: int, webhook_url: str) -> dict:
    now = datetime.now(timezone.utc)
    monitor_id = str(uuid.uuid4())
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        conn.execute(
            """INSERT INTO monitors
               (id, url, interval_minutes, webhook_url, created_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (monitor_id, url, interval_minutes, webhook_url, now),
        )
        conn.commit()
    return {
        "id": monitor_id,
        "url": url,
        "interval_minutes": interval_minutes,
        "webhook_url": webhook_url,
        "status": "active",
        "created_at": now.isoformat(),
    }


def list_monitors() -> list[dict]:
    with psycopg.connect(_db_url()) as conn:
        _init(conn)
        rows = conn.execute(
            """SELECT id, url, interval_minutes, webhook_url,
                      last_price, last_checked_at, created_at
               FROM monitors ORDER BY created_at DESC"""
        ).fetchall()
    return [
        {
            "id": r[0],
            "url": r[1],
            "interval_minutes": r[2],
            "webhook_url": r[3],
            "last_price": r[4],
            "last_checked_at": r[5].isoformat() if r[5] else None,
            "created_at": r[6].isoformat(),
        }
        for r in rows
    ]


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

    checked = 0
    changed = 0
    failed = 0

    async with httpx.AsyncClient(timeout=10) as client:
        for monitor_id, url, interval, webhook_url, old_price in rows:
            try:
                data = await fetch_product(url)
                pricing = data.get("pricing", {})
                new_price = pricing.get("price")
                currency = pricing.get("currency")
                source = data.get("source", {})
                source_url = source.get("url") or url

                event = None
                if old_price is not None and new_price is not None and new_price != old_price:
                    event = {
                        "event": "price_changed",
                        "monitor_id": monitor_id,
                        "old_price": old_price,
                        "new_price": new_price,
                        "currency": currency,
                        "url": url,
                        "source": {
                            "site": source.get("site"),
                            "url": source_url,
                        },
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
                        (
                            monitor_id,
                            new_price,
                            currency,
                            data["captured_at"],
                            source_url,
                        ),
                    )
                    conn.execute(
                        """UPDATE monitors
                           SET last_price = %s, last_checked_at = %s
                           WHERE id = %s""",
                        (new_price, now, monitor_id),
                    )
                    conn.commit()
                checked += 1
            except Exception:
                failed += 1

    return {"checked": checked, "changed": changed, "failed": failed}
