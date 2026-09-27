import asyncio
import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, HttpUrl

from app.services.monitor_store import (
    consume_credit,
    create_monitor,
    ensure_api_account,
    get_account_usage,
    get_price_history,
    get_price_opportunity,
    list_monitors,
    run_due_monitors,
)
from app.services.product_cache import fetch_product_cached

app = FastAPI(title="EC Pulse API", description="EC product data API and price monitoring service", version="0.7.0")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class ProductRequest(BaseModel):
    url: HttpUrl


class ProductCompareRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=2, max_length=20)


class MonitorRequest(BaseModel):
    url: HttpUrl
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    webhook_url: HttpUrl


def get_api_key(api_key: str | None = Depends(api_key_header)) -> str:
    expected = os.getenv("EC_PULSE_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


async def _fetch_product_or_http_error(url: str):
    try:
        payload, cache_hit = await fetch_product_cached(url)
        return {**payload, "cache": {"hit": cache_hit, "ttl_seconds": 300}}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to retrieve product page: {type(exc).__name__}") from exc


def _charge(api_key: str, endpoint: str, credits: int = 1):
    try:
        return consume_credit(api_key, endpoint, credits)
    except RuntimeError as exc:
        if "Insufficient API credits" in str(exc):
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/")
def root():
    return {
        "name": "EC Pulse API",
        "version": "0.7.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "product_endpoint": "GET /v1/products?url=...",
        "compare_endpoint": "POST /v1/products/compare",
        "monitor_endpoint": "POST /v1/monitors",
        "history_endpoint": "GET /v1/monitors/{monitor_id}/history",
        "opportunity_endpoint": "GET /v1/monitors/{monitor_id}/opportunity",
        "account_endpoint": "GET /v1/account",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/products")
async def product_get(url: HttpUrl = Query(...), api_key: str = Depends(get_api_key)):
    _charge(api_key, "GET /v1/products")
    return await _fetch_product_or_http_error(str(url))


@app.post("/v1/products")
async def product_post(request: ProductRequest, api_key: str = Depends(get_api_key)):
    _charge(api_key, "POST /v1/products")
    return await _fetch_product_or_http_error(str(request.url))


@app.post("/v1/products/compare")
async def product_compare(request: ProductCompareRequest, api_key: str = Depends(get_api_key)):
    urls = [str(url) for url in request.urls]
    _charge(api_key, "POST /v1/products/compare", len(urls))
    results = await asyncio.gather(
        *(fetch_product_cached(url) for url in urls),
        return_exceptions=True,
    )
    products = []
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            products.append({
                "url": url,
                "ok": False,
                "error": type(result).__name__,
            })
            continue
        payload, cache_hit = result
        products.append({
            "url": url,
            "ok": True,
            "cache": {"hit": cache_hit, "ttl_seconds": 300},
            "product": payload,
        })
    successful = [item["product"] for item in products if item["ok"]]
    ranked = sorted(
        successful,
        key=lambda item: (
            item.get("pricing", {}).get("price") is None,
            item.get("pricing", {}).get("price") or float("inf"),
        ),
    )
    return {
        "count": len(products),
        "successful": len(successful),
        "results": products,
        "price_ranking": [
            {
                "rank": index,
                "url": item.get("source", {}).get("url"),
                "title": item.get("product", {}).get("title"),
                "price": item.get("pricing", {}).get("price"),
                "currency": item.get("pricing", {}).get("currency"),
                "marketplace": item.get("source", {}).get("marketplace"),
                "product_id": item.get("source", {}).get("product_id"),
            }
            for index, item in enumerate(ranked, start=1)
        ],
    }


@app.post("/v1/monitors")
def monitor(request: MonitorRequest, api_key: str = Depends(get_api_key)):
    _charge(api_key, "POST /v1/monitors")
    try:
        return create_monitor(url=str(request.url), interval_minutes=request.interval_minutes, webhook_url=str(request.webhook_url))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/monitors")
def monitors(api_key: str = Depends(get_api_key)):
    try:
        return {"monitors": list_monitors()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/monitors/{monitor_id}/history")
def monitor_history(monitor_id: str, limit: int = 100, api_key: str = Depends(get_api_key)):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    _charge(api_key, "GET /v1/monitors/{monitor_id}/history")
    try:
        return get_price_history(monitor_id, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Monitor not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/monitors/{monitor_id}/opportunity")
def monitor_opportunity(monitor_id: str, limit: int = 100, api_key: str = Depends(get_api_key)):
    if limit < 2 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 2 and 1000")
    _charge(api_key, "GET /v1/monitors/{monitor_id}/opportunity", 2)
    try:
        return get_price_opportunity(monitor_id, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Monitor not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/account")
def account(api_key: str = Depends(get_api_key)):
    try:
        ensure_api_account(api_key)
        return get_account_usage(api_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/cron/check-monitors")
async def check_monitors(authorization: str | None = Header(default=None)):
    secret = os.getenv("CRON_SECRET")
    if not secret or authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        result = await run_due_monitors()
        return {"ok": True, "checked_at": datetime.now(timezone.utc).isoformat(), **result}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
