---
name: ec-monitor
description: Inspect EC Pulse price monitors and opportunity signals
argument-hint: "[monitor ID or inspection request]"
allowed-tools:
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_list
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_history
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_opportunity
  - mcp__plugin_ec-pulse_ec-pulse__ec_monitor_create
---

User request/context: $ARGUMENTS

Inspect the authenticated EC Pulse price monitors.

- Use monitor list for discovery.
- If a monitor is named, retrieve its history and opportunity signal.
- Never create a monitor unless the user explicitly requests creation.
- Before creation, confirm the requested product URL, interval, and webhook destination.
- Never expose the customer's API key or other secrets.
