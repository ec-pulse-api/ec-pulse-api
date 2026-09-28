# EC Pulse API

EC product data API and price monitoring infrastructure for Japanese e-commerce.

## Product

EC Pulse turns Japanese marketplace product pages and search results into normalized API data, then adds price history, monitoring, webhooks, and opportunity signals.

## Current API model

- REST + API key authentication
- Credit-based usage
- Per-customer usage ledger
- Per-customer monitor isolation
- Per-plan rate limits
- Response headers for remaining credits and rate limits
- Product cache to reduce duplicate upstream fetches

### Plans

| Plan | Credits | Rate limit |
|---|---:|---:|
| Free | 100 | 30 req/min |
| Pro | configurable | 300 req/min |
| Business | configurable | 3000 req/min |

The plan values are currently enforced in the API layer; commercial billing and automatic plan changes are the next layer.

## Core endpoints

- `GET /v1/products?url=...`
- `POST /v1/products`
- `POST /v1/products/search`
- `POST /v1/products/compare`
- `POST /v1/monitors`
- `GET /v1/monitors`
- `GET /v1/monitors/{id}/history`
- `GET /v1/monitors/{id}/opportunity`
- `GET /v1/account`
- `POST /v1/research/ingest`
- `GET /v1/research/runs/{run_id}/opportunity`

## Authentication

Send:

`X-API-Key: <customer-key>`

Customer keys are stored as SHA-256 hashes. The bootstrap/admin key is supplied through `EC_PULSE_API_KEY`.

## Usage headers

Successful metered responses expose:

- `X-EC-Credits-Used`
- `X-EC-Credits-Remaining`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## Architecture

```text
Client
  |
  v
EC Pulse API
  |-- API key auth
  |-- plan/rate limit
  |-- credit ledger
  |-- product cache
  |-- product normalization
  |-- marketplace search
  |-- monitor ownership
  |-- research persistence
  |-- pain/trend detection
  |-- opportunity engine
  |-- price history
  |-- webhook events
  v
PostgreSQL
```

## Next commercial layer

1. Stripe customer/subscription mapping
2. Automatic monthly credit grants
3. Paid-plan checkout
4. Customer dashboard
5. API key self-service
6. Public API documentation
7. TRACER integration
