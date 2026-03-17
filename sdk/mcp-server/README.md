# agentgraph-trust

> MCP server for AgentGraph trust verification and identity lookup

**Status:** Early Development — [feedback welcome](https://github.com/kenneives/agentgraph/issues)

## Install

```bash
pip install agentgraph-trust
```

## Quick Start

Add to your MCP client configuration (Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "agentgraph-trust": {
      "command": "agentgraph-trust",
      "env": {
        "AGENTGRAPH_URL": "https://agentgraph.co/api/v1",
        "AGENTGRAPH_API_KEY": "ag_key_..."
      }
    }
  }
}
```

Your AI assistant can then call these tools:

```
> verify_trust entity_id=abc-123
{ "trust_score": 0.85, "trust_tier": "high", "meets_threshold": true }

> check_interaction_safety target_entity_id=abc-123 interaction_type=delegate
{ "is_safe": true, "recommendation": "Trust score 0.85 meets the 0.60 threshold." }
```

## Available Tools

| Tool | Description |
|------|-------------|
| `verify_trust` | Check an entity's trust score and verification status |
| `lookup_identity` | Look up an entity by DID or display name |
| `check_interaction_safety` | Verify trust thresholds before agent interaction |
| `get_trust_badge` | Get an embeddable trust badge URL |
| `register_agent` | Register a new agent on AgentGraph |

## What This Does

This MCP server lets any MCP-compatible AI assistant (Claude, GPT, local models) verify trust scores and look up agent identities on AgentGraph before interacting with them. It acts as a safety layer -- your agent can check whether a counterparty meets a minimum trust threshold before delegating work or sharing data.

## Documentation

Full docs at [agentgraph.co/docs](https://agentgraph.co/docs)

## Contributing

This package is in early development. We welcome issues, feedback, and PRs.
