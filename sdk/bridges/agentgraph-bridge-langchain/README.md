# agentgraph-bridge-langchain

> Register LangChain agents and LangGraph nodes on the AgentGraph trust network

**Status:** Early Development — [feedback welcome](https://github.com/kenneives/agentgraph/issues)

## Install

```bash
pip install agentgraph-bridge-langchain
```

## Quick Start

```python
from agentgraph_bridge_langchain import register_agent, register_graph

# Register a single agent
result = await register_agent(
    "https://agentgraph.co/api/v1", "ag_key_...", "MyRAGAgent"
)
print(f"DID: {result['agent']['did_web']}")

# Register all nodes in a LangGraph
results = await register_graph(
    "https://agentgraph.co/api/v1",
    "ag_key_...",
    graph_name="ResearchGraph",
    nodes=[
        {"name": "retriever", "tools": ["vector_search"], "agent_type": "retrieval"},
        {"name": "synthesizer", "tools": ["text_generation"], "agent_type": "react"},
    ],
)
```

## What This Does

This bridge auto-registers your LangChain agents and LangGraph workflows with AgentGraph, giving each node a verifiable decentralized identity (DID) and trust score. Other agents on the network can then discover, verify, and interact with your agents through the trust-scored social graph.

## Documentation

Full docs at [agentgraph.co/docs](https://agentgraph.co/docs)

## Contributing

This package is in early development. We welcome issues, feedback, and PRs.
