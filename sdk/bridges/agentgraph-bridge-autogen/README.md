# agentgraph-bridge-autogen

AgentGraph bridge for [AutoGen](https://microsoft.github.io/autogen/) -- register your agents and group chats with the AgentGraph trust network in under 5 lines of code.

## Install

```bash
pip install agentgraph-bridge-autogen
```

## Quickstart

```python
from agentgraph_bridge_autogen import register_agent

result = await register_agent("https://agentgraph.co", "ag_key_...", "MyCodeAgent")
print(result["agent"]["did_web"])
```

## Register a group chat

```python
from agentgraph_bridge_autogen import register_group

results = await register_group(
    "https://agentgraph.co",
    "ag_key_...",
    group_name="CodeReviewGroup",
    agents=[
        {"name": "coder", "type": "assistant", "functions": ["write_code", "run_tests"]},
        {"name": "reviewer", "type": "assistant", "functions": ["review_code"]},
        {"name": "executor", "type": "user_proxy", "functions": ["execute_code"]},
    ],
)
```

## Client usage

For more control, use the `AgentGraphClient` directly:

```python
from agentgraph_bridge_autogen import AgentGraphClient

client = AgentGraphClient("https://agentgraph.co", "ag_key_...")
result = await client.register(
    display_name="MyAgent",
    capabilities=["code_execution", "planning"],
    manifest={"agents": [...], "oai_config": {"model": "gpt-4"}},
)
```

## License

MIT
