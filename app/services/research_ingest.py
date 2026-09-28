import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

COMMENT_SELECTORS = [
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

async def fetch_public_comments(url: str, max_comments: int = 500) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported")

    headers = {
        "User-Agent": "EC-Pulse-Research/0.11 (+public-page-analysis)",
        "Accept-Language": "ja,en;q=0.8",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for selector in COMMENT_SELECTORS:
        for node in soup.select(selector):
            text = " ".join(node.stripped_strings)
            text = re.sub(r"\s+", " ", text).strip()
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
        "title": title,
        "comments": comments,
        "comments_found": len(comments),
        "method": "public HTML selectors; source terms and robots/access rules must be respected",
    }
