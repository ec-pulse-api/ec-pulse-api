---
name: ec-search
description: Search Japanese e-commerce marketplaces with EC Pulse
argument-hint: "[product or category]"
allowed-tools:
  - mcp__plugin_ec-pulse_ec-pulse__ec_product_search
  - mcp__plugin_ec-pulse_ec-pulse__ec_product_get
  - mcp__plugin_ec-pulse_ec-pulse__ec_product_compare
---

User request/context: $ARGUMENTS

Search EC Pulse for the requested product or category.

Return only data actually returned by EC Pulse:
- product title
- marketplace
- price
- currency
- source URL
- credit usage when available

If the request is ambiguous, ask for the product/category and optionally preferred marketplaces. Do not invent missing fields.
