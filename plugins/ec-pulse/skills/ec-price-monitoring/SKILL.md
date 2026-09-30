---
name: ec-price-monitoring
description: Create and analyze EC Pulse price monitors for Japanese e-commerce products. Use when the user wants price tracking, price history, alerts, or opportunity signals.
---

# EC Price Monitoring

Use EC Pulse monitor tools for owned customer monitors.

## Workflow

1. Use `ec_monitor_create` only when the user explicitly wants a monitor created.
2. Validate that the product URL and webhook URL are intended destinations.
3. Use `ec_monitor_list` to inspect existing monitors.
4. Use `ec_monitor_history` for historical price movement.
5. Use `ec_monitor_opportunity` for derived opportunity signals.
6. Report actual observations separately from derived signals.

Never expose the customer's API key in output.
