import json
import os
import threading
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import psycopg

from app.services.product_parser import fetch_product


def _db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def _init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_cache (
            cache_key TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            payload JSONB NOT NULL,
            captured_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_cache_expires ON product_cache (expires_at)"
    )
    conn.commit()


_init_lock = threading.Lock()
_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        with psycopg.connect(_db_url()) as conn:
            _init(conn)
        _initialized = True


def _key(url: str) -> str:
    return sha256(url.strip().encode()).hexdigest()


async def fetch_product_cached(url: str, ttl_seconds: int = 300) -> tuple[dict, bool]:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 86400:
        raise ValueError("ttl_seconds must be between 1 and 86400")
    now = datetime.now(timezone.utc)
    cache_key = _key(url)
    _ensure_initialized()

    # Session-level advisory lock prevents a cold/stale-key thundering herd
    # across concurrent serverless instances.
    conn = psycopg.connect(_db_url())
    try:
        conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (cache_key,))
        row = conn.execute(
            "SELECT payload FROM product_cache WHERE cache_key = %s AND expires_at > %s",
            (cache_key, now),
        ).fetchone()
        if row:
            conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (cache_key,))
            return row[0], True

        payload = await fetch_product(url)
        captured_at = datetime.now(timezone.utc)
        expires_at = captured_at + timedelta(seconds=ttl_seconds)
        conn.execute(
            """
            INSERT INTO product_cache (cache_key, url, payload, captured_at, expires_at)
            VALUES (%s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                url = EXCLUDED.url,
                payload = EXCLUDED.payload,
                captured_at = EXCLUDED.captured_at,
                expires_at = EXCLUDED.expires_at
            """,
            (cache_key, url, json.dumps(payload), captured_at, expires_at),
        )
        conn.commit()
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (cache_key,))
        return payload, False
    finally:
        try:
            conn.close()
        except Exception:
            pass
