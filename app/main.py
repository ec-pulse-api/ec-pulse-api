import os
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, HttpUrl

from app.services.product_parser import fetch_product

app = FastAPI(
    title="EC Pulse API",
    description="EC product data API and price monitoring service",
    version="0.1.0",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class ProductRequest(BaseModel):
    url: HttpUrl


def require_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    expected = os.getenv("EC_PULSE_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API authentication is not configured",
        )
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/")
def root():
    return {
        "name": "EC Pulse API",
        "version": "0.1.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "product_endpoint": "POST /v1/products",
        "authentication": "X-API-Key",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/products", dependencies=[Depends(require_api_key)])
async def product(request: ProductRequest):
    try:
        return await fetch_product(str(request.url))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to retrieve product page: {type(exc).__name__}",
        ) from exc
