from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

from app.services.product_parser import fetch_product

app = FastAPI(
    title="EC Pulse API",
    description="EC product data API and price monitoring service",
    version="0.1.0",
)


class ProductRequest(BaseModel):
    url: HttpUrl


@app.get("/")
def root():
    return {
        "name": "EC Pulse API",
        "version": "0.1.0",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "product_endpoint": "POST /v1/products",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/products")
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
