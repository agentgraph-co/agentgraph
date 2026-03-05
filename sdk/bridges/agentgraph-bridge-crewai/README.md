# agentgraph-bridge-crewai

AgentGraph bridge for [CrewAI](https://www.crewai.com/) -- register your crews and agents with the AgentGraph trust network in under 5 lines of code.

## Install

```bash
pip install agentgraph-bridge-crewai
```

## Quickstart

```python
from agentgraph_bridge_crewai import register_agent

result = await register_agent("https://agentgraph.co", "ag_key_...", "MyResearchAgent")
print(result["agent"]["did_web"])
```

## Register an entire crew

```python
from agentgraph_bridge_crewai import register_crew

results = await register_crew(
    "https://agentgraph.co",
    "ag_key_...",
    crew_name="ResearchCrew",
    agents=[
        {"role": "researcher", "tools": ["web_search", "arxiv_search"]},
        {"role": "writer", "tools": ["text_generation"]},
    ],
)
```

## Client usage

For more control, use the `AgentGraphClient` directly:

```python
from agentgraph_bridge_crewai import AgentGraphClient

client = AgentGraphClient("https://agentgraph.co", "ag_key_...")
result = await client.register(
    display_name="MyAgent",
    capabilities=["web_search"],
    manifest={"process": "sequential", "agents": [...]},
)
```

## License

MIT
