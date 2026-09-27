import os
import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, HttpUrl

from app.services.monitor_store import create_monitor, list_monitors, run_due_monitors
from app.services.product_parser import fetch_product
from app.services.supabase_client import check_supabase

app = FastAPI(
    title="EC Pulse API",
    description="EC product data API and price monitoring service",
    version="0.2.0",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class ProductRequest(BaseModel):
    url: HttpUrl


class MonitorRequest(BaseModel):
    url: HttpUrl
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    webhook_url: HttpUrl


def require_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    expected = os.getenv("EC_PULSE_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/")
def root():
    return {
        "name": "EC Pulse API",
        "version": "0.2.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "product_endpoint": "POST /v1/products",
        "monitor_endpoint": "POST /v1/monitors",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/supabase", dependencies=[Depends(require_api_key)])
async def supabase_health():
    try:
        return await check_supabase()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Supabase connectivity check failed: {type(exc).__name__}") from exc


@app.post("/v1/products", dependencies=[Depends(require_api_key)])
async def product(request: ProductRequest):
    try:
        return await fetch_product(str(request.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to retrieve product page: {type(exc).__name__}") from exc


@app.post("/v1/monitors", dependencies=[Depends(require_api_key)])
def monitor(request: MonitorRequest):
    try:
        return create_monitor(
            url=str(request.url),
            interval_minutes=request.interval_minutes,
            webhook_url=str(request.webhook_url),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/monitors", dependencies=[Depends(require_api_key)])
def monitors():
    try:
        return {"monitors": list_monitors()}
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
