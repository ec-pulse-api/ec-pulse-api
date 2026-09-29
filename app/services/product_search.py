import asyncio
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


async def search_products(query: str, marketplaces: list[str], limit: int) -> dict:
    urls_by_marketplace = await asyncio.gather(
        *(_search_marketplace(marketplace, query, limit) for marketplace in marketplaces),
        return_exceptions=True,
    )

    candidates = []
    for marketplace, result in zip(marketplaces, urls_by_marketplace):
        if isinstance(result, Exception):
            candidates.append({
                "marketplace": marketplace,
                "ok": False,
                "error": type(result).__name__,
                "results": [],
            })
            continue

        product_results = await asyncio.gather(
            *(fetch_product_cached(url) for url in result),
            return_exceptions=True,
        )
        items = []
        for url, product_result in zip(result, product_results):
            if isinstance(product_result, Exception):
                continue
            payload, cache_hit = product_result
            items.append({
                "url": url,
                "cache_hit": cache_hit,
                "product": payload,
            })
        candidates.append({
            "marketplace": marketplace,
            "ok": True,
            "results": items,
        })

    flat = [
        item
        for group in candidates
        for item in group["results"]
    ]
    priced = [
        item for item in flat
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
