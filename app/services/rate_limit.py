import os
from datetime import datetime, timezone

import psycopg

_WINDOWS = {"free": 60, "pro": 60, "business": 60}
_LIMITS = {"free": 30, "pro": 300, "business": 3000}


def _db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def check_rate_limit(api_key_hash: str, plan: str) -> dict:
    """Enforce a shared fixed-window limit in Postgres across Vercel instances."""
    window = _WINDOWS.get(plan, 60)
    limit = _LIMITS.get(plan, 30)

    with psycopg.connect(_db_url()) as conn:
        row = conn.execute(
            """
            SELECT window_start, request_count
            FROM api_rate_limits
            WHERE api_key_hash = %s
            FOR UPDATE
            """,
            (api_key_hash,),
        ).fetchone()

        now = datetime.now(timezone.utc)
        current_window = now.replace(second=0, microsecond=0)

        if row is None or row[0] != current_window:
            conn.execute(
                """
                INSERT INTO api_rate_limits (api_key_hash, window_start, request_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (api_key_hash) DO UPDATE
                SET window_start = EXCLUDED.window_start,
                    request_count = EXCLUDED.request_count
                """,
                (api_key_hash, current_window),
            )
            return {
                "allowed": True,
                "limit": limit,
                "remaining": max(0, limit - 1),
                "reset_seconds": window,
            }

        request_count = row[1]
        if request_count >= limit:
            elapsed = max(0, (now - row[0]).total_seconds())
            return {
                "allowed": False,
                "limit": limit,
                "remaining": 0,
                "reset_seconds": max(1, int(window - elapsed)),
            }

        request_count += 1
        conn.execute(
            "UPDATE api_rate_limits SET request_count = %s WHERE api_key_hash = %s",
            (request_count, api_key_hash),
        )
        elapsed = max(0, (now - row[0]).total_seconds())
        return {
            "allowed": True,
            "limit": limit,
            "remaining": max(0, limit - request_count),
            "reset_seconds": max(1, int(window - elapsed)),
        }
