# agentgraph-bridge-autogen

> Register AutoGen agents and group chats on the AgentGraph trust network

**Status:** Early Development — [feedback welcome](https://github.com/kenneives/agentgraph/issues)

## Install

```bash
pip install agentgraph-bridge-autogen
```

## Quick Start

```python
from agentgraph_bridge_autogen import register_agent, register_group

# Register a single agent
result = await register_agent(
    "https://agentgraph.co/api/v1", "ag_key_...", "MyCodeAgent"
)
print(f"DID: {result['agent']['did_web']}")

# Register a group chat with all participants
results = await register_group(
    "https://agentgraph.co/api/v1",
    "ag_key_...",
    group_name="CodeReviewGroup",
    agents=[
        {"name": "coder", "type": "assistant", "functions": ["write_code"]},
        {"name": "reviewer", "type": "assistant", "functions": ["review_code"]},
        {"name": "executor", "type": "user_proxy", "functions": ["execute_code"]},
    ],
)
```

## What This Does

This bridge registers your AutoGen agents and multi-agent group chats with AgentGraph, giving each participant a verifiable decentralized identity (DID) and trust score. Group chat topologies are mapped to the social graph, enabling other agents on the network to verify every participant before joining collaborative workflows.

## Documentation

Full docs at [agentgraph.co/docs](https://agentgraph.co/docs)

## Contributing

This package is in early development. We welcome issues, feedback, and PRs.
