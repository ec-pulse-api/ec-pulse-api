# EC Pulse Claude Code Plugin

EC Pulse gives Claude Code direct access to Japanese e-commerce product data, research, customer insight, and price monitoring through the EC Pulse API.

## Requirements

- Claude Code with plugin support
- A valid EC Pulse API key
- Python 3.10+ available as `python3`

## Configuration

Set the API key in the environment before launching Claude Code:

```bash
export EC_PULSE_API_KEY="ecp_live_..."
```

The plugin uses the production API by default:
`https://ec-pulse-api.vercel.app`

For a self-hosted or staging API, set `EC_PULSE_API_BASE_URL` before launching Claude Code.

## Included

### MCP tools

- `ec_product_search`
- `ec_product_get`
- `ec_product_compare`
- `ec_research_ingest`
- `ec_consumer_insights`
- `ec_monitor_create`
- `ec_monitor_list`
- `ec_monitor_history`
- `ec_monitor_opportunity`
- `ec_account`

### Skills

- EC market research
- EC price monitoring
- EC API usage

### Commands

- `/ec-pulse:ec-search`
- `/ec-pulse:ec-research`
- `/ec-pulse:ec-monitor`

## Security

The API key is read only from the process environment and is never written to plugin files. Keep it secret and never commit it to Git.

The plugin calls only the configured EC Pulse API base URL. URL fetching remains subject to EC Pulse's server-side public-URL safety validation.
