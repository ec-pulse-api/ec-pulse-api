---
name: ec-api-usage
description: Inspect EC Pulse API account usage, credits, and plan limits. Use when the user asks about EC Pulse API usage, remaining credits, or account status.
---

# EC API Usage

Use `ec_account` to inspect the authenticated account.

Report:
- current plan
- remaining credits
- rate-limit information when returned
- relevant next action if credits are insufficient

Never print the API key or any secret environment variable.
