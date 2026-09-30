# EC Pulse Claude Code Plugin

EC Pulse connects Claude Code to the EC Pulse API for Japanese e-commerce product discovery, product comparison, public-comment research, consumer insights, price monitoring, and account usage.

## Requirements

- Claude Code with plugin support.
- Python 3.10+ available as `python3` (use `python` in .mcp.json if that is the available Windows executable).
- A valid EC Pulse API key.

## Configuration

Set the key before starting Claude Code:

```bash
export EC_PULSE_API_KEY="ecp_live_..."
```

Production API: `https://ec-pulse-api.vercel.app`.

Optional:
- `EC_PULSE_API_BASE_URL` for another deployment.
- `EC_PULSE_REQUIRE_REQUEST_SIGNATURE=true` when the API requires HMAC request signatures.

The raw API key is never stored in the repository or returned by MCP tools.

## MCP tools

- `ec_product_search` -> `POST /v1/products/search`
- `ec_product_get` -> `GET /v1/products`
- `ec_product_compare` -> `POST /v1/products/compare`
- `ec_research_ingest` -> `POST /v1/research/ingest`
- `ec_consumer_insights` -> `POST /v1/consumer-insights/analyze`
- `ec_monitor_create` -> `POST /v1/monitors` (state-changing; explicit user intent required)
- `ec_monitor_list` -> `GET /v1/monitors`
- `ec_monitor_history` -> `GET /v1/monitors/{id}/history`
- `ec_monitor_opportunity` -> `GET /v1/monitors/{id}/opportunity`
- `ec_account` -> `GET /v1/account`
- `ec_research_runs` -> `GET /v1/research/runs`
- `ec_research_opportunity` -> `GET /v1/research/runs/{run_id}/opportunity`

No endpoint is invented on the plugin side.

## Commands

- `/ec-pulse:ec-search`
- `/ec-pulse:ec-research`
- `/ec-pulse:ec-monitor`

## Skills

- `ec-market-research`
- `ec-price-monitoring`
- `ec-api-usage`

## Example prompts

1. `日本のEC市場で「折りたたみ収納ボックス」を検索して、観測された価格帯と主要商品を比較してください。`
2. `この商品の競合URLを比較して、価格・通貨・Marketplaceを事実ベースで整理してください。`
3. `この公開レビューURLを調査して、観測された顧客の不満と、それを踏まえた仮説を分けて整理してください。`
4. `現在のEC Pulse価格Monitorを確認して、最近の価格変動とAPIが返すOpportunity signalを説明してください。`
5. `EC Pulseの残りクレジットと現在のプランを確認してください。`

## Evidence rules

Treat API results as observations. Separate observations from analysis and hypotheses. Do not invent prices, reviews, ratings, inventory, market share, or customer sentiment. Do not describe a small public-comment sample as representative of an entire market.

## Security

- Authentication uses `X-API-Key` from `EC_PULSE_API_KEY`.
- No raw key is emitted in MCP results or logs.
- One upstream request per tool call; no automatic retry loop.
- 401, 402, 403, 404, 429, and 5xx errors are reduced to safe messages.
- Product/research/monitor URL safety remains enforced by the EC Pulse API, including its public-network and redirect protections.
- Monitor/history access remains account-scoped by the API key.
- Non-HTTPS custom API bases are rejected unless they are localhost/loopback.
- HMAC request signing is supported when enabled by the API.

## Credits

EC Pulse uses credit-based billing. The plugin does not hard-code paid-plan credit quotas. Use `ec_account` for current account usage. The API documents Free as 100 credits and configurable paid-plan quotas.

## Troubleshooting

- `EC_PULSE_API_KEY is not configured`: set the environment variable and restart Claude Code.
- `401`: key is missing, invalid, or revoked.
- `402`: insufficient credits; no retry is attempted.
- `429`: rate limit reached; no retry loop is attempted.
- URL rejection: do not bypass EC Pulse's server-side URL safety validation.

## Tests

Protocol/security tests are under `plugins/ec-pulse/tests/`:

```bash
python3 -m unittest discover -s plugins/ec-pulse/tests -v
```

Live API smoke tests require `EC_PULSE_API_KEY`. If it is unavailable, record exactly:

`NOT RUN: EC_PULSE_API_KEY is not configured`

## Local marketplace installation

From a checkout of this repository, the bundled marketplace can be added with:

```text
/plugin marketplace add ec-pulse-api/ec-pulse-api
/plugin install ec-pulse@ec-pulse-api
```

## Marketplace submission

The package follows the current Claude Code plugin structure: `.claude-plugin/plugin.json`, root `.mcp.json`, commands, skills, and evaluation documentation. The bundled MCP server uses ${CLAUDE_PLUGIN_ROOT} for portable paths.

Before submission, provide truthful operator/support/privacy information, any requested test account or sample data, and verify ownership/control of published endpoints and documentation. This repository does not fabricate those details.
