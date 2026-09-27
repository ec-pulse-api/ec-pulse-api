import time
from collections import defaultdict
from threading import Lock

_WINDOWS = {"free": 60, "pro": 60, "business": 60}
_LIMITS = {"free": 30, "pro": 300, "business": 3000}
_BUCKETS: dict[str, list[float]] = defaultdict(list)
_LOCK = Lock()

def check_rate_limit(api_key_hash: str, plan: str) -> dict:
    now = time.time()
    window = _WINDOWS.get(plan, 60)
    limit = _LIMITS.get(plan, 30)
    with _LOCK:
        bucket = _BUCKETS[api_key_hash]
        cutoff = now - window
        _BUCKETS[api_key_hash] = bucket = [t for t in bucket if t > cutoff]
        if len(bucket) >= limit:
            retry_after = max(1, int(window - (now - bucket[0])))
            return {"allowed": False, "limit": limit, "remaining": 0, "reset_seconds": retry_after}
        bucket.append(now)
        return {"allowed": True, "limit": limit, "remaining": max(0, limit - len(bucket)), "reset_seconds": window}
