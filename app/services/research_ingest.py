import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

SOURCE_CONFIG = {
    "amazon": {
        "domains": ("amazon.",),
        "selectors": ['[data-hook="review-body"]', '[data-testid="review-body"]', '[itemprop="reviewBody"]'],
    },
    "rakuten": {
        "domains": ("review.rakuten.co.jp", "rakuten.co.jp"),
        "selectors": ['[class*="review"]', '[class*="comment"]'],
    },
    "yahoo": {
        "domains": ("shopping.yahoo.co.jp", "shopping.yahoo.com"),
        "selectors": ['[class*="review"]', '[class*="comment"]'],
    },
    "reddit": {
        "domains": ("reddit.com", "www.reddit.com"),
        "selectors": ['[data-testid="comment"]', 'div[data-comment-body]', 'blockquote'],
    },
    "youtube": {
        "domains": ("youtube.com", "www.youtube.com", "m.youtube.com"),
        "selectors": ['yt-attributed-string#content-text', '#content-text', 'ytd-comment-thread-renderer #content-text'],
    },
    "tiktok": {
        "domains": ("tiktok.com", "www.tiktok.com"),
        "selectors": ['[data-e2e="comment-text"]', '[class*="CommentItem"]', '[class*="comment"]'],
    },
}

GENERIC_SELECTORS = [
    '[data-hook="review-body"]',
    '[data-testid="review-body"]',
    '[data-comment-body]',
    '.review-text',
    '.review-content',
    '.comment-content',
    '.comment-body',
    '[itemprop="reviewBody"]',
    'blockquote',
]

def detect_source(host: str) -> str:
    host = host.lower()
    for source, config in SOURCE_CONFIG.items():
        if any(domain in host for domain in config["domains"]):
            return source
    return "generic"

def detect_market(host: str, language_hint: str | None = None) -> str:
    host = host.lower()
    if ".co.jp" in host or "rakuten.co.jp" in host or language_hint == "ja":
        return "JP"
    if host == "amazon.com" or host.endswith(".amazon.com"):
        return "US"
    # Global social/community domains do not imply a US market by themselves.
    return "GLOBAL"

def detect_locale(market: str) -> str:
    return {"JP": "ja-JP", "US": "en-US"}.get(market, "en")

def _selectors_for(source: str) -> list[str]:
    return SOURCE_CONFIG.get(source, {}).get("selectors", []) + GENERIC_SELECTORS

def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()

async def fetch_public_comments(url: str, max_comments: int = 500) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported")

    source = detect_source(parsed.netloc)
    market = detect_market(parsed.netloc)
    locale = detect_locale(market)
    headers = {
        "User-Agent": "EC-Pulse-Research/0.12 (+public-page-analysis)",
        "Accept-Language": "ja,en;q=0.8",
    }

    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for selector in _selectors_for(source):
        for node in soup.select(selector):
            text = _clean_text(" ".join(node.stripped_strings))
            if 8 <= len(text) <= 2000:
                candidates.append(text)

    seen = set()
    comments = []
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        comments.append(item)
        if len(comments) >= max_comments:
            break

    title = soup.title.get_text(" ", strip=True) if soup.title else None
    return {
        "url": url,
        "source": parsed.netloc,
        "source_type": source,
        "market": market,
        "locale": locale,
        "title": title,
        "comments": comments,
        "comments_found": len(comments),
        "access": "public_html",
        "method": "source-aware public HTML selectors; official/public APIs should be preferred where available and source terms/robots/access rules must be respected",
    }
