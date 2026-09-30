---
name: ec-research
description: Run an evidence-based EC Pulse market research workflow
argument-hint: "[product, category, or research question]"
allowed-tools:
  - mcp__plugin_ec-pulse_ec-pulse__ec_product_search
  - mcp__plugin_ec-pulse_ec-pulse__ec_product_get
  - mcp__plugin_ec-pulse_ec-pulse__ec_product_compare
  - mcp__plugin_ec-pulse_ec-pulse__ec_research_ingest
  - mcp__plugin_ec-pulse_ec-pulse__ec_consumer_insights
---

User request/context: $ARGUMENTS

Run an evidence-based EC Pulse research workflow.

1. Search products first when discovery is needed.
2. Compare concrete products when URLs are available.
3. Ingest public review/comment URLs only when the user supplies them or explicitly asks to research them.
4. Use consumer insights on returned comments.
5. Clearly separate observed facts, derived signals, and hypotheses.

Do not invent prices, reviews, ratings, market share, or customer sentiment.
