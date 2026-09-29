import pytest

from app.services.product_cache import fetch_product_cached


@pytest.mark.asyncio
async def test_product_cache_rejects_invalid_ttl():
    with pytest.raises(ValueError, match="ttl_seconds"):
        await fetch_product_cached("https://example.com/product", 0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        await fetch_product_cached("https://example.com/product", 86401)


def test_product_cache_write_rejects_lost_lease():
    from datetime import datetime, timezone

    from app.services.product_cache import _write_cached_payload

    class Cursor:
        rowcount = 0

    class Conn:
        def execute(self, sql, params):
            normalized = " ".join(sql.split())
            assert "clock_timestamp()" in normalized
            assert "lock_token = %s" in normalized
            return Cursor()

    import pytest

    with pytest.raises(TimeoutError, match="lease expired"):
        _write_cached_payload(
            Conn(),
            "cache-key",
            "https://example.com/product",
            {"title": "test"},
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
            "lease-token",
        )
