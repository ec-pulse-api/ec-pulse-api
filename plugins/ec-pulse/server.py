#!/usr/bin/env python3
"""Minimal stdio MCP bridge for the EC Pulse REST API.

No third-party Python package is required. Claude Code launches this process
through the plugin's .mcp.json configuration.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.getenv("EC_PULSE_API_BASE_URL", "https://ec-pulse-api.vercel.app").rstrip("/")
API_KEY = os.getenv("EC_PULSE_API_KEY", "")

TOOLS = [
    {
        "name": "ec_product_search",
        "description": "Search Japanese marketplace products across Amazon, Rakuten, and Yahoo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "marketplaces": {"type": "array", "items": {"type": "string"}, "default": ["amazon", "rakuten", "yahoo"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "ec_product_get",
        "description": "Fetch normalized product data from a public product URL.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"]
        }
    },
    {
        "name": "ec_product_compare",
        "description": "Compare 2 to 20 public product URLs and return normalized price ranking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "minItems": 2, "maxItems": 20, "items": {"type": "string", "format": "uri"}}
            },
            "required": ["urls"]
        }
    },
    {
        "name": "ec_research_ingest",
        "description": "Ingest public URLs for market research, comment analysis, pain points, and trend signals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string", "format": "uri"}},
                "max_comments_per_url": {"type": "integer", "minimum": 1, "maximum": 500, "default": 500}
            },
            "required": ["urls"]
        }
    },
    {
        "name": "ec_consumer_insights",
        "description": "Analyze customer comments for pain points, terms, and recommended product angles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "comments": {"type": "array", "minItems": 1, "maxItems": 5000, "items": {"type": "string"}},
                "source": {"type": "string"}
            },
            "required": ["comments"]
        }
    },
    {
        "name": "ec_monitor_create",
        "description": "Create a price monitor with a webhook destination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "format": "uri"},
                "interval_minutes": {"type": "integer", "minimum": 5, "maximum": 10080, "default": 60},
                "webhook_url": {"type": "string", "format": "uri"}
            },
            "required": ["url", "webhook_url"]
        }
    },
    {
        "name": "ec_monitor_list",
        "description": "List the authenticated customer's price monitors.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "ec_monitor_history",
        "description": "Read price history for one owned monitor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "monitor_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}
            },
            "required": ["monitor_id"]
        }
    },
    {
        "name": "ec_monitor_opportunity",
        "description": "Analyze a monitor's price history for opportunity signals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "monitor_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 2, "maximum": 1000, "default": 100}
            },
            "required": ["monitor_id"]
        }
    },
    {
        "name": "ec_account",
        "description": "Return the authenticated EC Pulse API account plan and current usage.",
        "inputSchema": {"type": "object", "properties": {}}
    }
]


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def api_request(method: str, path: str, payload: dict | None = None, query: dict | None = None) -> dict:
    if not API_KEY:
        raise RuntimeError("EC_PULSE_API_KEY is not configured")
    url = BASE_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    body = None
    headers = {"Accept": "application/json", "X-API-Key": API_KEY}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(f"EC Pulse API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"EC Pulse API connection failed: {exc.reason}") from exc


def call_tool(name: str, args: dict) -> dict:
    if name == "ec_product_search":
        return api_request("POST", "/v1/products/search", {
            "query": args["query"],
            "marketplaces": args.get("marketplaces", ["amazon", "rakuten", "yahoo"]),
            "limit": args.get("limit", 5),
        })
    if name == "ec_product_get":
        return api_request("GET", "/v1/products", query={"url": args["url"]})
    if name == "ec_product_compare":
        return api_request("POST", "/v1/products/compare", {"urls": args["urls"]})
    if name == "ec_research_ingest":
        return api_request("POST", "/v1/research/ingest", {
            "urls": args["urls"],
            "max_comments_per_url": args.get("max_comments_per_url", 500),
        })
    if name == "ec_consumer_insights":
        payload = {"comments": args["comments"]}
        if args.get("source"):
            payload["source"] = args["source"]
        return api_request("POST", "/v1/consumer-insights/analyze", payload)
    if name == "ec_monitor_create":
        return api_request("POST", "/v1/monitors", {
            "url": args["url"],
            "interval_minutes": args.get("interval_minutes", 60),
            "webhook_url": args["webhook_url"],
        })
    if name == "ec_monitor_list":
        return api_request("GET", "/v1/monitors")
    if name == "ec_monitor_history":
        return api_request("GET", f"/v1/monitors/{urllib.parse.quote(args['monitor_id'], safe='')}/history", query={"limit": args.get("limit", 100)})
    if name == "ec_monitor_opportunity":
        return api_request("GET", f"/v1/monitors/{urllib.parse.quote(args['monitor_id'], safe='')}/opportunity", query={"limit": args.get("limit", 100)})
    if name == "ec_account":
        return api_request("GET", "/v1/account")
    raise ValueError(f"Unknown tool: {name}")


def handle(message: dict) -> dict | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ec-pulse", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = call_tool(name, args)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle(message)
            if response is not None:
                send(response)
        except Exception as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}})


if __name__ == "__main__":
    main()
