# EC Pulse Plugin Evaluation

Unexecuted cases must remain **NOT RUN**. The current execution environment cannot reach GitHub from a local shell, and no production API key is exposed to this audit.

| Case | Status | Scope |
|---|---|---|
| 1. Product discovery | NOT RUN | Requires live EC Pulse API |
| 2. Market research | NOT RUN | Requires live API/public source run |
| 3. Consumer insight | NOT RUN | Requires live tool execution |
| 4. Price monitoring | NOT RUN | Requires an authenticated test account with monitor data |
| 5. Credit shortage | NOT RUN | Requires a test account with insufficient credits |
| 6. Invalid/private URL | NOT RUN | Must verify production API rejects unsafe destinations |
| 7. API authentication failure | NOT RUN | Requires a deliberately invalid live key |
| 8. MCP protocol failure | NOT RUN | Unit tests were added, but the local runner was unavailable |

## Automated test

GitHub Actions workflow: `.github/workflows/ec-pulse-plugin.yml`

It runs:

```bash
python -m unittest discover -s plugins/ec-pulse/tests -v
```

The workflow was committed, but its execution result was not available through the connected GitHub status interface during this audit. Therefore these cases are not marked PASS.

## Live smoke test

When a dedicated test key is available, run:

- `GET /`
- `GET /health`
- `ec_product_search`
- `ec_product_get`
- `ec_product_compare`
- `ec_account`

If no key is configured, record:

`NOT RUN: EC_PULSE_API_KEY is not configured`

Never paste the key into issues, logs, README files, test fixtures, or chat.
