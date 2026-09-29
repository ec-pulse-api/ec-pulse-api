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

Plan limits, Stripe checkout, subscription synchronization, credit accounting, and usage tracking are implemented; the remaining commercial layer is self-service key management and customer-facing dashboard/docs.

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
- `GET /v1/research/runs`
- `GET /v1/research/runs/{run_id}/opportunity`
- `POST /v1/consumer-insights/analyze`
- `POST /v1/billing/checkout`
- `POST /v1/billing/portal`
- `POST /v1/billing/cancel`
- `POST /api/stripe/webhook`

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

1. Automatic monthly credit grants / top-ups
2. Customer dashboard
3. API key self-service
4. Public API documentation
5. TRACER integration

## Legal documents

Customer-facing policy drafts are maintained under `docs/legal/`:

- [Terms of Service](docs/legal/terms-of-service.md)
- [Privacy Policy](docs/legal/privacy-policy.md)
- [Billing / Refund / Cancellation Policy](docs/legal/billing-and-cancellation.md)
- [Specified Commercial Transactions Act disclosure](docs/legal/commercial-transactions.md)
- [Acceptable Use Policy](docs/legal/acceptable-use.md)

Before public launch, replace all `［要入力］` fields with the actual operator, contact, jurisdiction, retention, refund, and other business/legal details and review the final text for the applicable jurisdiction.
