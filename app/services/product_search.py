import asyncio
import os
import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from app.services.product_cache import fetch_product_cached
from app.services.url_safety import MAX_REDIRECTS, next_redirect, validate_public_url


SEARCH_URLS = {
    "amazon": "https://www.amazon.co.jp/s?k={query}",
    "rakuten": "https://search.rakuten.co.jp/search/mall/{query}/",
    "yahoo": "https://shopping.yahoo.co.jp/search?p={query}",
}

YAHOO_SEARCH_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
_YAHOO_REQUEST_LOCK = asyncio.Lock()
_YAHOO_MIN_INTERVAL_SECONDS = 1.05
_yahoo_last_request_at = 0.0


def _links(html: str, marketplace: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if marketplace == "amazon":
            match = re.search(r"(https?://www\.amazon\.co\.jp)?/[^\s"']*/dp/([A-Z0-9]{10})", href, re.I)
            if match:
                url = f"https://www.amazon.co.jp/dp/{match.group(2).upper()}"
            else:
                continue
        elif marketplace == "rakuten":
            if "item.rakuten.co.jp/" not in href:
                continue
            url = href.split("?")[0]
        else:
            if "shopping.yahoo.co.jp/" not in href:
                continue
            url = href.split("?")[0]

        if url not in seen:
            seen.add(url)
            found.append(url)
        if len(found) >= 10:
            break
    return found


def _yahoo_item_to_product(item: dict) -> dict:
    price = item.get("price")
    if price is None:
        price = (item.get("priceLabel") or {}).get("defaultPrice")

    brand = item.get("brand") or {}
    seller = item.get("seller") or {}
    review = item.get("review") or {}

    return {
        "product": {
            "title": item.get("name"),
            "description": item.get("description"),
            "brand": brand.get("name"),
            "jan_code": item.get("janCode"),
        },
        "pricing": {
            "price": price,
            "currency": "JPY",
            "price_tax_included": (item.get("priceLabel") or {}).get("taxable"),
        },
        "source": {
            "marketplace": "yahoo",
            "url": item.get("url"),
            "product_id": item.get("code"),
            "seller_id": seller.get("sellerId"),
            "seller_name": seller.get("name"),
            "seller_url": seller.get("url"),
        },
        "review": {
            "rating": review.get("rate"),
            "count": review.get("count"),
            "url": review.get("url"),
        },
        "availability": {
            "in_stock": item.get("inStock"),
        },
        "image": {
            "url": (item.get("image") or {}).get("medium")
                    or (item.get("image") or {}).get("small"),
        },
    }


async def _search_yahoo_api(query: str, limit: int) -> list[dict]:
    app_id = os.getenv("YAHOO_SHOPPING_APP_ID")
    if not app_id:
        raise RuntimeError("YAHOO_SHOPPING_APP_ID is not configured")

    params = {
        "appid": app_id,
        "query": query,
        "results": min(limit, 50),
        "start": 1,
        "sort": "+price",
        "in_stock": "true",
    }
    global _yahoo_last_request_at
    async with _YAHOO_REQUEST_LOCK:
        now = asyncio.get_running_loop().time()
        wait = _YAHOO_MIN_INTERVAL_SECONDS - (now - _yahoo_last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(YAHOO_SEARCH_URL, params=params)
            _yahoo_last_request_at = asyncio.get_running_loop().time()
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), 5.0) if retry_after else 1.1
                except ValueError:
                    delay = 1.1
                await asyncio.sleep(delay)
                response = await client.get(YAHOO_SEARCH_URL, params=params)
                _yahoo_last_request_at = asyncio.get_running_loop().time()
            response.raise_for_status()
            payload = response.json()

    return [
        {
            "url": item.get("url"),
            "cache_hit": False,
            "product": _yahoo_item_to_product(item),
        }
        for item in payload.get("hits", [])[:limit]
        if item.get("url")
    ]


async def _search_marketplace(marketplace: str, query: str, limit: int) -> list[str]:
    url = SEARCH_URLS[marketplace].format(query=quote_plus(query))
    current_url = await validate_public_url(url)
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=15.0,
        headers={"User-Agent": "EC-Pulse/0.1 (+https://ec-pulse-api.vercel.app)"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = await client.get(current_url)
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect response did not include a location")
                current_url = await validate_public_url(next_redirect(current_url, location))
                continue
            response.raise_for_status()
            break
        else:
            raise ValueError("Too many redirects")
    return _links(response.text, marketplace)[:limit]


async def _search_marketplace_items(marketplace: str, query: str, limit: int) -> list[dict]:
    if marketplace == "yahoo" and os.getenv("YAHOO_SHOPPING_APP_ID"):
        return await _search_yahoo_api(query, limit)

    urls = await _search_marketplace(marketplace, query, limit)
    product_results = await asyncio.gather(
        *(fetch_product_cached(url) for url in urls),
        return_exceptions=True,
    )
    items = []
    for url, product_result in zip(urls, product_results):
        if isinstance(product_result, Exception):
            continue
        payload, cache_hit = product_result
        items.append({
            "url": url,
            "cache_hit": cache_hit,
            "product": payload,
        })
    return items


async def search_products(query: str, marketplaces: list[str], limit: int) -> dict:
    groups = await asyncio.gather(
        *(_search_marketplace_items(marketplace, query, limit) for marketplace in marketplaces),
        return_exceptions=True,
    )

    candidates = []
    for marketplace, result in zip(marketplaces, groups):
        if isinstance(result, Exception):
            candidates.append({
                "marketplace": marketplace,
                "ok": False,
                "error": type(result).__name__,
                "results": [],
            })
            continue

        candidates.append({
            "marketplace": marketplace,
            "ok": True,
            "results": result,
        })

    flat = [
        item
        for group in candidates
        for item in group["results"]
    ]
    priced = [
        item
        for item in flat
        if item["product"].get("pricing", {}).get("price") is not None
    ]
    priced.sort(key=lambda item: item["product"]["pricing"]["price"])

    return {
        "query": query,
        "marketplaces": marketplaces,
        "count": len(flat),
        "results": flat,
        "price_ranking": [
            {
                "rank": i,
                "url": item["url"],
                "title": item["product"].get("product", {}).get("title"),
                "price": item["product"].get("pricing", {}).get("price"),
                "currency": item["product"].get("pricing", {}).get("currency"),
                "marketplace": item["product"].get("source", {}).get("marketplace"),
                "product_id": item["product"].get("source", {}).get("product_id"),
            }
            for i, item in enumerate(priced, 1)
        ],
    }
