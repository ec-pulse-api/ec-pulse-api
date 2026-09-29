import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import psycopg

from app.services.product_parser import fetch_product
from app.services.url_safety import validate_public_url


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_cache_locks (
            cache_key TEXT PRIMARY KEY,
            lock_token TEXT NOT NULL,
            locked_until TIMESTAMPTZ NOT NULL
        )
        """
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
    url = str(await validate_public_url(url))
    now = datetime.now(timezone.utc)
    cache_key = _key(url)
    _ensure_initialized()

    with psycopg.connect(_db_url()) as conn:
        row = conn.execute(
            "SELECT payload FROM product_cache WHERE cache_key = %s AND expires_at > %s",
            (cache_key, now),
        ).fetchone()
    if row:
        return row[0], True

    # Use a short-lived DB lease instead of holding a PostgreSQL connection
    # open while the external product page is being fetched.
    lock_token = sha256(f"{cache_key}:{datetime.now(timezone.utc).timestamp()}".encode()).hexdigest()
    lease_until = datetime.now(timezone.utc) + timedelta(seconds=300)
    with psycopg.connect(_db_url()) as conn:
        claimed = conn.execute(
            """
            INSERT INTO product_cache_locks (cache_key, lock_token, locked_until)
            VALUES (%s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE
            SET lock_token = EXCLUDED.lock_token,
                locked_until = EXCLUDED.locked_until
            WHERE product_cache_locks.locked_until <= CURRENT_TIMESTAMP
            RETURNING lock_token
            """,
            (cache_key, lock_token, lease_until),
        ).fetchone()

    if not claimed:
        for _ in range(150):
            await asyncio.sleep(0.2)
            with psycopg.connect(_db_url()) as conn:
                row = conn.execute(
                    "SELECT payload FROM product_cache WHERE cache_key = %s AND expires_at > %s",
                    (cache_key, datetime.now(timezone.utc)),
                ).fetchone()
            if row:
                return row[0], True
        raise TimeoutError("Timed out waiting for product cache refresh")

    try:
        with psycopg.connect(_db_url()) as conn:
            row = conn.execute(
                "SELECT payload FROM product_cache WHERE cache_key = %s AND expires_at > %s",
                (cache_key, datetime.now(timezone.utc)),
            ).fetchone()
        if row:
            return row[0], True

        payload = await fetch_product(url)
        captured_at = datetime.now(timezone.utc)
        expires_at = captured_at + timedelta(seconds=ttl_seconds)
        with psycopg.connect(_db_url()) as conn:
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
        return payload, False
    finally:
        with psycopg.connect(_db_url()) as conn:
            conn.execute(
                "DELETE FROM product_cache_locks WHERE cache_key = %s AND lock_token = %s",
                (cache_key, lock_token),
            )
            conn.commit()
