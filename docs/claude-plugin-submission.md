# Claude Code Plugin Marketplace Submission

## Package

- Plugin: `ec-pulse`
- Repository: https://github.com/ec-pulse-api/ec-pulse-api
- Plugin path: `plugins/ec-pulse/`
- Production API: https://ec-pulse-api.vercel.app
- Claude Code support: local stdio MCP + commands + skills
- MCP server: `.mcp.json` -> `server.py`

## Current implementation

- 12 MCP tools
- 3 Claude Code commands
- 3 Agent Skills
- MCP JSON-RPC protocol handling
- Input validation
- Safe upstream error mapping
- API-key environment configuration
- Optional HMAC request signing
- Local/private literal URL rejection
- No automatic retry loop
- Unit tests and GitHub Actions workflow

## Public documentation

- API repository: https://github.com/ec-pulse-api/ec-pulse-api
- Privacy policy draft: https://github.com/ec-pulse-api/ec-pulse-api/blob/main/docs/legal/privacy-policy.md
- Terms draft: https://github.com/ec-pulse-api/ec-pulse-api/blob/main/docs/legal/terms-of-service.md
- Billing/cancellation draft: https://github.com/ec-pulse-api/ec-pulse-api/blob/main/docs/legal/billing-and-cancellation.md
- Acceptable use: https://github.com/ec-pulse-api/ec-pulse-api/blob/main/docs/legal/acceptable-use.md
- Commercial transactions draft: https://github.com/ec-pulse-api/ec-pulse-api/blob/main/docs/legal/commercial-transactions.md

## Marketplace form data to confirm

Do not submit until the following are truthful and complete:

- Operator/business legal name
- Support email or support URL
- Privacy-policy URL containing final operator/contact information
- Terms URL containing final operator information
- Billing/refund/cancellation policy with final refund rules
- Commercial-transactions disclosure with final business information, where applicable
- Final homepage/product landing page
- Category selected in the submission portal
- Test account or sample data requested by the reviewer
- Confirmation that the operator controls the published API endpoint and documentation
- Final pricing/credit description

## Current blockers

The legal documents still contain `［要入力］` placeholders and therefore must not be represented as final legal policies.

Production smoke testing is also not marked PASS. The audit environment cannot resolve external DNS, and no production `EC_PULSE_API_KEY` is available to the test runner.

The existing repository's Vercel status currently reports `build-rate-limit`. This is separate from the Plugin source changes and must be resolved before claiming the Production deployment is healthy.

## Evaluation status

- Product discovery: NOT RUN
- Market research: NOT RUN
- Consumer insight: NOT RUN
- Price monitoring: NOT RUN
- Credit shortage: NOT RUN
- Invalid/private URL: NOT RUN against production; local literal-private validation is covered by unit tests
- API authentication failure: NOT RUN against production
- MCP protocol: GitHub Actions plugin test suite PASS on PR #5 head

Never mark a case PASS without an actual recorded run.
