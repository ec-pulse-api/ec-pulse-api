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
| 8. MCP protocol failure | PASS | GitHub Actions plugin test suite passed on the latest audited commit |

## Automated test

GitHub Actions workflow: `.github/workflows/ec-pulse-plugin.yml`

It runs:

```bash
python -m unittest discover -s plugins/ec-pulse/tests -v
```

The latest audited commit `7196be9ac7f7086a5385704fedc2fffbd0849b62` was verified through GitHub Actions: plugin test run `36732491028` completed successfully. The repository-wide test run `36732491058` also completed successfully.

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
