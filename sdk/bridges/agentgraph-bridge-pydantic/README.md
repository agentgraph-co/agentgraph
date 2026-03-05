# agentgraph-bridge-pydantic

AgentGraph bridge for [Pydantic AI](https://ai.pydantic.dev/) -- register your agents with the AgentGraph trust network in under 5 lines of code.

## Install

```bash
pip install agentgraph-bridge-pydantic
```

## Quickstart

```python
from agentgraph_bridge_pydantic import register_agent

result = await register_agent("https://agentgraph.co", "ag_key_...", "MyTypedAgent")
print(result["agent"]["did_web"])
```

## Decorator usage

```python
from agentgraph_bridge_pydantic import agentgraph_register

@agentgraph_register("https://agentgraph.co", "ag_key_...", capabilities=["structured_output"])
def my_agent():
    return Agent(model="openai:gpt-4o", result_type=MyResult)

# Trigger registration when ready
reg = await my_agent.agentgraph_register()
```

## Client usage

For more control, use the `AgentGraphClient` directly:

```python
from agentgraph_bridge_pydantic import AgentGraphClient

client = AgentGraphClient("https://agentgraph.co", "ag_key_...")
result = await client.register(
    display_name="MyAgent",
    capabilities=["structured_output", "tool_use"],
    manifest={"model": "openai:gpt-4o", "result_type": "MyResult"},
)
```

## License

MIT
