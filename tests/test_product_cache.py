import pytest

from app.services.product_cache import fetch_product_cached


@pytest.mark.asyncio
async def test_product_cache_rejects_invalid_ttl():
    with pytest.raises(ValueError, match="ttl_seconds"):
        await fetch_product_cached("https://example.com/product", 0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        await fetch_product_cached("https://example.com/product", 86401)
