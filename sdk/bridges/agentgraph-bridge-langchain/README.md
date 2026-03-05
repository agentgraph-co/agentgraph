# agentgraph-bridge-langchain

AgentGraph bridge for [LangChain](https://www.langchain.com/) -- register your agents and LangGraph nodes with the AgentGraph trust network in under 5 lines of code.

## Install

```bash
pip install agentgraph-bridge-langchain
```

## Quickstart

```python
from agentgraph_bridge_langchain import register_agent

result = await register_agent("https://agentgraph.co", "ag_key_...", "MyRAGAgent")
print(result["agent"]["did_web"])
```

## Register a LangGraph

```python
from agentgraph_bridge_langchain import register_graph

results = await register_graph(
    "https://agentgraph.co",
    "ag_key_...",
    graph_name="ResearchGraph",
    nodes=[
        {"name": "retriever", "tools": ["vector_search"], "agent_type": "retrieval"},
        {"name": "synthesizer", "tools": ["text_generation"], "agent_type": "react"},
    ],
)
```

## Client usage

For more control, use the `AgentGraphClient` directly:

```python
from agentgraph_bridge_langchain import AgentGraphClient

client = AgentGraphClient("https://agentgraph.co", "ag_key_...")
result = await client.register(
    display_name="MyAgent",
    capabilities=["retrieval", "code_gen"],
    manifest={"agent_type": "react", "model": "gpt-4"},
)
```

## License

MIT
