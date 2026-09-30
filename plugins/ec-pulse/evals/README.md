# EC Pulse Plugin Evaluation Cases

Use these cases before Marketplace submission.

1. **Product discovery** — Ask for Japanese marketplace products matching a concrete query. Verify the plugin calls product search and returns source URLs, marketplace, prices, and credits without inventing data.
2. **Research workflow** — Provide public review/comment URLs and ask for pain points and product opportunities. Verify the plugin distinguishes observations from hypotheses.
3. **Price monitoring** — Ask to inspect an existing monitor and its history. Verify ownership errors are surfaced and secrets are never exposed.
4. **Insufficient credits** — Use an account with insufficient credits and verify the API error is surfaced without retry loops or key disclosure.
5. **Invalid destination** — Attempt to create a monitor with a private/internal URL and verify EC Pulse rejects it.
