# EC Pulse Claude Code Plugin

EC Pulse is packaged as a Claude plugin bundle containing an MCP server, Agent Skills, and Claude Code commands.

Anthropic's current plugin submission flow supports a GitHub-hosted plugin bundle and explicitly supports Claude Code components including MCP servers, skills, commands, hooks, agents, and LSPs.

## Installation prerequisites

- Claude Code with plugin support
- Python 3.10+
- An EC Pulse API key

Set the API key in the environment before starting Claude Code:

```bash
export EC_PULSE_API_KEY="ecp_live_..."
```

The bundled MCP configuration uses:

`https://ec-pulse-api.vercel.app`

## Plugin contents

```text
plugins/ec-pulse/
├── .claude-plugin/
│   └── plugin.json
├── .mcp.json
├── server.py
├── commands/
│   ├── ec-search.md
│   ├── ec-research.md
│   └── ec-monitor.md
├── skills/
│   ├── ec-market-research/SKILL.md
│   ├── ec-price-monitoring/SKILL.md
│   └── ec-api-usage/SKILL.md
├── evals/
│   └── README.md
└── README.md
```

## Submission positioning

Primary use cases:

1. Japanese e-commerce product discovery and comparison.
2. Market research and customer pain-point analysis.
3. Price monitoring and opportunity analysis.

The plugin does not expose EC Pulse secrets. The customer's API key remains in the local process environment and is sent only to the configured EC Pulse API.

## Marketplace submission

Anthropic's September 25, 2026 submission flow accepts GitHub-hosted plugin bundles containing MCP servers and skills; Claude Code bundles may also include commands, hooks, agents, and LSPs. The submission portal performs automated validation and safety scanning before review.

Official submission portal: `https://platform.claude.com/plugins/submit`

Submit the GitHub repository through Anthropic's Claude Plugin Submission Portal after the MCP bridge has been smoke-tested with a real EC Pulse API key.

Before submission, verify:

- plugin manifest parses
- MCP initialization succeeds
- tools/list returns all declared tools
- product search works with a real API key
- insufficient-credit errors are surfaced cleanly
- private/internal URLs are rejected by EC Pulse
- no secret appears in plugin files, logs, or command output
- the three core user workflows in `plugins/ec-pulse/evals/README.md` pass

Do not submit a fake API key or any production secret to GitHub.
