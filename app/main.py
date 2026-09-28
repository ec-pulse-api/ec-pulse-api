import asyncio
import hashlib
import os
import httpx
import psycopg
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, HttpUrl

from app.services.billing import create_checkout, create_customer_portal, process_webhook
from app.services.monitor_store import consume_credit, create_monitor, ensure_api_account, get_account_usage, get_price_history, get_price_opportunity, list_monitors, run_due_monitors, validate_api_key, save_research_run, get_research_opportunity, list_research_runs
from app.services.product_cache import fetch_product_cached
from app.services.product_search import search_products
from app.services.consumer_insights import analyze_comments
from app.services.research_ingest import fetch_public_comments
from app.services.rate_limit import check_rate_limit

app = FastAPI(title="EC Pulse API", description="EC product data API and market research service", version="0.12.0")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

class ProductRequest(BaseModel):
    url: HttpUrl
class ProductCompareRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=2, max_length=20)
class ProductSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    marketplaces: list[str] = Field(default=["amazon", "rakuten", "yahoo"], min_length=1, max_length=3)
    limit: int = Field(default=5, ge=1, le=10)
class ConsumerInsightRequest(BaseModel):
    comments: list[str] = Field(min_length=1, max_length=5000)
    source: str | None = Field(default=None, max_length=50)
class ResearchUrlRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=20)
    max_comments_per_url: int = Field(default=500, ge=1, le=500)

class MonitorRequest(BaseModel):
    url: HttpUrl
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    webhook_url: HttpUrl

def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

def get_api_key(request: Request, api_key: str | None = Depends(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    try:
        if not validate_api_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        account = ensure_api_account(api_key)
        rate = check_rate_limit(_key_hash(api_key), account["plan"])
        request.state.rate_limit = rate
        if not rate["allowed"]:
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(rate["reset_seconds"]), "X-RateLimit-Limit": str(rate["limit"]), "X-RateLimit-Remaining": "0"})
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return api_key

def _charge(api_key: str, endpoint: str, credits: int = 1):
    try: return consume_credit(api_key, endpoint, credits)
    except RuntimeError as exc:
        message=str(exc)
        if "Insufficient API credits" in message: raise HTTPException(status_code=402, detail=message) from exc
        if "Invalid or revoked API key" in message: raise HTTPException(status_code=401, detail=message) from exc
        raise HTTPException(status_code=503, detail=message) from exc

def _usage_headers(request: Request, api_key: str, result: dict | None = None) -> dict[str,str]:
    try:
        account = ensure_api_account(api_key)
        rate = getattr(request.state, "rate_limit", None)
        if rate is None:
            rate = check_rate_limit(_key_hash(api_key), account["plan"])
            request.state.rate_limit = rate
        headers = {
            "X-RateLimit-Limit": str(rate["limit"]),
            "X-RateLimit-Remaining": str(rate["remaining"]),
            "X-RateLimit-Reset": str(rate["reset_seconds"]),
            "X-EC-Credits-Remaining": str(account["credits_balance"]),
        }
        if result:
            headers["X-EC-Credits-Used"] = str(result.get("credits_used", 0))
        return headers
    except Exception:
        return {}

async def _fetch_product_or_http_error(url: str):
    try:
        payload,cache_hit=await fetch_product_cached(url)
        return {**payload,"cache":{"hit":cache_hit,"ttl_seconds":300}}
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502,detail=f"Unable to retrieve product page: {type(exc).__name__}") from exc

@app.get("/")
def root():
    return {"name":"EC Pulse API","version":"0.12.0","status":"ok","docs":"/docs","health":"/health","pricing_model":"credit-based API with per-plan rate limits"}

@app.get("/health")
def health():
    # Verify the database dependency so a broken deployment is not reported as healthy.
    try:
        from app.services.monitor_store import _db_url
        with psycopg.connect(_db_url(), connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "ok"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "database": "unavailable", "error": type(exc).__name__},
        ) from exc

@app.post("/v1/billing/checkout")
def billing_checkout(plan: str = Query(..., pattern="^(pro|business)$"), api_key: str = Depends(get_api_key)):
    try:
        return {"url": create_checkout(api_key, plan), "plan": plan}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.post("/v1/billing/portal")
def billing_portal(api_key: str = Depends(get_api_key)):
    try:
        return {"url": create_customer_portal(api_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    try:
        return process_webhook(await request.body(), stripe_signature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.get("/v1/pricing")
def pricing():
    return {"currency":"USD","plans":{"free":{"credits":100,"rate_limit_per_minute":30},"pro":{"credits":"configurable","rate_limit_per_minute":300},"business":{"credits":"configurable","rate_limit_per_minute":3000}},"billing":"credit_based","note":"Paid pricing and automatic subscription provisioning will be connected next."}

@app.post("/v1/consumer-insights/analyze")
def consumer_insights(request: ConsumerInsightRequest, api_key: str = Depends(get_api_key)):
    charge = _charge(api_key, "POST /v1/consumer-insights/analyze", max(1, len(request.comments) // 50))
    result = analyze_comments(request.comments, request.source, "en-US" if request.source and any(x in request.source.lower() for x in ["amazon.com", "reddit", "youtube.com", "tiktok.com"]) else None)
    result["credits"] = charge
    return result

@app.post("/v1/research/ingest")
async def research_ingest(request: ResearchUrlRequest, api_key: str = Depends(get_api_key)):
    charge = _charge(api_key, "POST /v1/research/ingest", len(request.urls))
    results = []
    for url in request.urls:
        try:
            item = await fetch_public_comments(str(url), request.max_comments_per_url)
            if item["comments"]:
                item["analysis"] = analyze_comments(item["comments"], item["source"], item.get("locale"))
                try:
                    item["trend"] = save_research_run(api_key, item, item["analysis"])
                except Exception as exc:
                    item["trend"] = {"signal": "persistence_error", "error": type(exc).__name__}
            else:
                item["analysis"] = {"comments_analyzed": 0, "pain_points": [], "top_terms": [], "recommended_angle": None}
            results.append(item)
        except httpx.HTTPStatusError as exc:
            results.append({"url": str(url), "ok": False, "error": f"http_{exc.response.status_code}"})
        except Exception as exc:
            results.append({"url": str(url), "ok": False, "error": type(exc).__name__})
    market_summary = {}
    for item in results:
        if not item.get("analysis"):
            continue
        market = item.get("market", "GLOBAL")
        bucket = market_summary.setdefault(market, {"urls": 0, "comments": 0, "pain_points": {}})
        bucket["urls"] += 1
        bucket["comments"] += item["analysis"].get("comments_analyzed", 0)
        for pain in item["analysis"].get("pain_points", []):
            bucket["pain_points"][pain["pain"]] = bucket["pain_points"].get(pain["pain"], 0) + pain["count"]

    for bucket in market_summary.values():
        bucket["top_pains"] = sorted(
            [{"pain": pain, "count": count} for pain, count in bucket["pain_points"].items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]
        del bucket["pain_points"]

    return {"count": len(results), "credits": charge, "market_summary": market_summary, "results": results}

@app.get("/v1/research/runs")
def research_runs(
    request_http: Request,
    url: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=20, ge=1, le=100),
    api_key: str = Depends(get_api_key),
):
    try:
        return {"runs": list_research_runs(api_key, url, limit)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/v1/research/runs/{run_id}/opportunity")
async def research_opportunity(run_id: str, request_http: Request, response: Response, api_key: str = Depends(get_api_key)):
    charge = _charge(api_key, "GET /v1/research/runs/{run_id}/opportunity", 1)
    for k, v in _usage_headers(request_http, api_key, charge).items():
        response.headers[k] = v
    try:
        result = get_research_opportunity(api_key, run_id)
        queries = []
        for item in result.get("product_directions", [])[:3]:
            if item["pain"] not in queries:
                queries.append(item["pain"])
        candidates = []
        for query in queries:
            try:
                found = await search_products(query, ["amazon", "rakuten", "yahoo"], 5)
                if isinstance(found, dict):
                    candidates.extend(found.get("results", found.get("items", [])))
            except Exception:
                continue
        result["product_candidates"] = candidates[:15]
        result["credits"] = charge
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research run not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.get("/v1/products")
async def product_get(request:Request,response:Response,url:HttpUrl=Query(...),api_key:str=Depends(get_api_key)):
    charge=_charge(api_key,"GET /v1/products")
    for k,v in _usage_headers(request,api_key,charge).items(): response.headers[k]=v
    return await _fetch_product_or_http_error(str(url))

@app.post("/v1/products")
async def product_post(request_http:Request,response:Response,request:ProductRequest,api_key:str=Depends(get_api_key)):
    charge=_charge(api_key,"POST /v1/products")
    for k,v in _usage_headers(request_http,api_key,charge).items(): response.headers[k]=v
    return await _fetch_product_or_http_error(str(request.url))

@app.post("/v1/products/search")
async def product_search(request_http:Request,response:Response,request:ProductSearchRequest,api_key:str=Depends(get_api_key)):
    marketplaces=[m.lower() for m in request.marketplaces]
    if any(m not in {"amazon","rakuten","yahoo"} for m in marketplaces): raise HTTPException(status_code=400,detail="marketplaces must contain only amazon, rakuten, yahoo")
    charge=_charge(api_key,"POST /v1/products/search",request.limit*len(marketplaces))
    for k,v in _usage_headers(request_http,api_key,charge).items(): response.headers[k]=v
    try: return await search_products(request.query,marketplaces,request.limit)
    except Exception as exc: raise HTTPException(status_code=502,detail=f"Product search failed: {type(exc).__name__}") from exc

@app.post("/v1/products/compare")
async def product_compare(request_http:Request,response:Response,request:ProductCompareRequest,api_key:str=Depends(get_api_key)):
    urls=[str(u) for u in request.urls]; charge=_charge(api_key,"POST /v1/products/compare",len(urls))
    for k,v in _usage_headers(request_http,api_key,charge).items(): response.headers[k]=v
    results=await asyncio.gather(*(fetch_product_cached(url) for url in urls),return_exceptions=True)
    products=[]
    for url,result in zip(urls,results):
        if isinstance(result,Exception): products.append({"url":url,"ok":False,"error":type(result).__name__}); continue
        payload,cache_hit=result; products.append({"url":url,"ok":True,"cache":{"hit":cache_hit,"ttl_seconds":300},"product":payload})
    successful=[x["product"] for x in products if x["ok"]]
    ranked=sorted(successful,key=lambda x:(x.get("pricing",{}).get("price") is None,x.get("pricing",{}).get("price") or float("inf")))
    return {"count":len(products),"successful":len(successful),"results":products,"price_ranking":[{"rank":i,"url":x.get("source",{}).get("url"),"title":x.get("product",{}).get("title"),"price":x.get("pricing",{}).get("price"),"currency":x.get("pricing",{}).get("currency"),"marketplace":x.get("source",{}).get("marketplace"),"product_id":x.get("source",{}).get("product_id")} for i,x in enumerate(ranked,1)]}

@app.post("/v1/monitors")
def monitor(request_http:Request,response:Response,request:MonitorRequest,api_key:str=Depends(get_api_key)):
    charge=_charge(api_key,"POST /v1/monitors")
    for k,v in _usage_headers(request_http,api_key,charge).items(): response.headers[k]=v
    try: return create_monitor(api_key=api_key,url=str(request.url),interval_minutes=request.interval_minutes,webhook_url=str(request.webhook_url))
    except RuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/v1/monitors")
def monitors(api_key:str=Depends(get_api_key)):
    try: return {"monitors":list_monitors(api_key)}
    except RuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/v1/monitors/{monitor_id}/history")
def monitor_history(monitor_id:str,limit:int=100,api_key:str=Depends(get_api_key)):
    if not 1<=limit<=1000: raise HTTPException(status_code=400,detail="limit must be between 1 and 1000")
    _charge(api_key,"GET /v1/monitors/{monitor_id}/history")
    try: return get_price_history(api_key,monitor_id,limit)
    except KeyError as exc: raise HTTPException(status_code=404,detail="Monitor not found") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/v1/monitors/{monitor_id}/opportunity")
def monitor_opportunity(monitor_id:str,limit:int=100,api_key:str=Depends(get_api_key)):
    if not 2<=limit<=1000: raise HTTPException(status_code=400,detail="limit must be between 2 and 1000")
    _charge(api_key,"GET /v1/monitors/{monitor_id}/opportunity",2)
    try: return get_price_opportunity(api_key,monitor_id,limit)
    except KeyError as exc: raise HTTPException(status_code=404,detail="Monitor not found") from exc
    except RuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/v1/account")
def account(api_key:str=Depends(get_api_key)):
    try: ensure_api_account(api_key); return get_account_usage(api_key)
    except RuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc

@app.get("/api/cron/check-monitors")
async def check_monitors(authorization:str|None=Header(default=None)):
    secret=os.getenv("CRON_SECRET")
    if not secret or authorization!=f"Bearer {secret}": raise HTTPException(status_code=401,detail="Unauthorized")
    try: return {"ok":True,"checked_at":datetime.now(timezone.utc).isoformat(),**await run_due_monitors()}
    except RuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
