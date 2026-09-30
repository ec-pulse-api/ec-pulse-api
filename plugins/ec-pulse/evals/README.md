# EC Pulse Plugin Evaluation

Unexecuted cases must remain **NOT RUN**. Production live cases remain unexecuted because no production API key is exposed to this audit.

| Case | Status | Scope |
|---|---|---|
| 1. Product discovery | NOT RUN | Requires live EC Pulse API |
| 2. Market research | NOT RUN | Requires live API/public source run |
| 3. Consumer insight | NOT RUN | Requires live tool execution |
| 4. Price monitoring | NOT RUN | Requires an authenticated test account with monitor data |
| 5. Credit shortage | NOT RUN | Requires a test account with insufficient credits |
| 6. Invalid/private URL | NOT RUN | Must verify production API rejects unsafe destinations |
| 7. API authentication failure | NOT RUN | Requires a deliberately invalid live key |
| 8. MCP protocol failure | PASS | GitHub Actions plugin test suite passed on the current audited commit |

## Automated test

GitHub Actions workflow: `.github/workflows/ec-pulse-plugin.yml`

It runs:

```bash
python -m unittest discover -s plugins/ec-pulse/tests -v
```

The current audited commit `c9f7c54d96c5fcae785f9e8d0031992f80985e8d` was verified through GitHub Actions: plugin test run `36733563325` completed successfully. The repository-wide test run `36733563889` also completed successfully. The current-head Vercel status is NOT VERIFIED.

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
