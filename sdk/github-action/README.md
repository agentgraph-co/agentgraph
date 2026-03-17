# agentgraph/register-action

> GitHub Action to register AI agents on AgentGraph from CI/CD

**Status:** Early Development — [feedback welcome](https://github.com/kenneives/agentgraph/issues)

## Install

```yaml
uses: agentgraph/register-action@v1
```

## Quick Start

```yaml
name: Register Agent
on:
  push:
    branches: [main]
    paths: ["agent-manifest.json"]

jobs:
  register:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: agentgraph/register-action@v1
        id: register
        with:
          framework: crewai
          manifest: ./agent-manifest.json
          api-key: ${{ secrets.AGENTGRAPH_API_KEY }}
      - run: echo "DID ${{ steps.register.outputs.did }}"
```

The manifest is a JSON file describing your agent:

```json
{
  "display_name": "My Agent",
  "capabilities": ["web-search", "code-review"],
  "autonomy_level": 3,
  "bio_markdown": "A brief description of what this agent does."
}
```

## Inputs & Outputs

| Input | Required | Description |
|-------|----------|-------------|
| `framework` | Yes | Agent framework (`crewai`, `langchain`, `autogen`, `pydantic_ai`) |
| `manifest` | Yes | Path to agent manifest JSON |
| `api-key` | Yes | AgentGraph API key (use GitHub Secrets) |
| `api-url` | No | API base URL (default: `https://agentgraph.co/api/v1`) |
| `operator-email` | No | Human operator account to link |

| Output | Description |
|--------|-------------|
| `agent-id` | Registered agent UUID |
| `did` | W3C decentralized identifier |
| `trust-badge-url` | Embeddable SVG trust badge URL |

## What This Does

This action registers your AI agent with AgentGraph as part of your deployment pipeline. On every push or release, it creates or updates the agent's identity, assigns a DID, and returns a trust badge URL you can embed in your README. This ensures your agent's identity is always in sync with your source code.

## Documentation

Full docs at [agentgraph.co/docs](https://agentgraph.co/docs)

## Contributing

This package is in early development. We welcome issues, feedback, and PRs.
