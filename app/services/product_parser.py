import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "EC-Pulse/0.1 (+https://ec-pulse-api.vercel.app)"

MARKETPLACES = {
    "amazon.co.jp": "amazon",
    "www.amazon.co.jp": "amazon",
    "rakuten.co.jp": "rakuten",
    "item.rakuten.co.jp": "rakuten",
    "shopping.yahoo.co.jp": "yahoo",
    "lohaco.yahoo.co.jp": "yahoo",
}

def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None

def _jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            items.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            items.append(data)
    return items

def _find_product(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if item.get("@type") == "Product":
            return item
        graph = item.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if isinstance(node, dict) and node.get("@type") == "Product":
                    return node
    return None

def _number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace(",", ""))
    return float(match.group()) if match else None

def _marketplace(host: str) -> str:
    host = host.lower().split(":")[0]
    return MARKETPLACES.get(host, "web")

def _product_id(marketplace: str, path: str) -> str | None:
    if marketplace == "amazon":
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", path, re.I)
        return match.group(1).upper() if match else None
    if marketplace == "rakuten":
        parts = [part for part in path.split("/") if part]
        return parts[-1] if parts else None
    if marketplace == "yahoo":
        parts = [part for part in path.split("/") if part]
        return parts[-1] if parts else None
    return None

async def fetch_product(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A valid http(s) URL is required")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15.0,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    product = _find_product(_jsonld(soup)) or {}
    offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
    marketplace = _marketplace(parsed.netloc)
    product_id = (
        product.get("sku")
        or product.get("mpn")
        or product.get("gtin13")
        or _product_id(marketplace, parsed.path)
    )

    title = product.get("name") or _meta(soup, "og:title") or (
        soup.title.get_text(strip=True) if soup.title else None
    )
    image = product.get("image") or _meta(soup, "og:image")

    return {
        "product": {
            "title": title,
            "brand": (
                product.get("brand", {}).get("name")
                if isinstance(product.get("brand"), dict)
                else product.get("brand")
            ),
            "model": product.get("model"),
            "sku": product.get("sku"),
            "gtin": product.get("gtin13") or product.get("gtin"),
            "product_id": product_id,
        },
        "pricing": {
            "price": _number(offers.get("price") or product.get("price")),
            "list_price": _number(
                offers.get("highPrice") if offers.get("highPrice") else None
            ),
            "currency": offers.get("priceCurrency"),
        },
        "availability": {
            "status": offers.get("availability"),
        },
        "rating": {
            "score": _number(
                product.get("aggregateRating", {}).get("ratingValue")
                if isinstance(product.get("aggregateRating"), dict)
                else None
            ),
            "count": int(
                _number(
                    product.get("aggregateRating", {}).get("reviewCount")
                    or product.get("aggregateRating", {}).get("ratingCount")
                )
                or 0
            ),
        },
        "seller": {
            "name": (
                offers.get("seller", {}).get("name")
                if isinstance(offers.get("seller"), dict)
                else offers.get("seller")
            ),
        },
        "source": {
            "site": parsed.netloc,
            "marketplace": marketplace,
            "product_id": product_id,
            "url": str(response.url),
            "image": image,
        },
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
