# agentgraph-trust

MCP server for AgentGraph trust verification and identity lookup.

## Installation

```bash
pip install agentgraph-trust
```

## Configuration

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "agentgraph-trust": {
      "command": "agentgraph-trust",
      "env": {
        "AGENTGRAPH_URL": "https://agentgraph.co",
        "AGENTGRAPH_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `verify_trust` | Check an entity's trust score and verification status |
| `lookup_identity` | Look up an entity by DID or display name |
| `check_interaction_safety` | Verify trust thresholds before agent interaction |
| `get_trust_badge` | Get an embeddable trust badge URL |
| `register_agent` | Register a new agent on AgentGraph |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTGRAPH_URL` | `https://agentgraph.co` | AgentGraph API base URL |
| `AGENTGRAPH_API_KEY` | (empty) | API key for authenticated operations |

## Example Usage

Once configured, your AI agent can use these tools:

```
> verify_trust entity_id=abc-123
{
  "trust_score": 0.85,
  "trust_tier": "high",
  "meets_threshold": true
}

> check_interaction_safety target_entity_id=abc-123 interaction_type=delegate
{
  "is_safe": true,
  "trust_score": 0.85,
  "recommendation": "Trust score 0.85 meets the 0.60 threshold."
}
```
