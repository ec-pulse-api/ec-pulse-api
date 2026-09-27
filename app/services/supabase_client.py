import os

import httpx


def _config() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SECRET_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are not configured")
    return url, key


async def check_supabase() -> dict:
    url, key = _config()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{url}/rest/v1/",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase REST check failed with HTTP {response.status_code}")
    return {"status": "ok", "url": url}
