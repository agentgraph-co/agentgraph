# agentgraph-langchain

AgentGraph trust verification plugin for LangChain agents.

## Installation

```bash
pip install agentgraph-langchain
```

## Quick Start

### Verify Trust Before Interaction

```python
import asyncio
from agentgraph_langchain import verify_trust

async def main():
    trusted = await verify_trust("entity-123", min_score=0.7)
    if trusted:
        print("Entity is trusted, proceeding...")
    else:
        print("Entity does not meet trust threshold.")

asyncio.run(main())
```

### Use as a LangChain Callback

```python
from langchain_openai import ChatOpenAI
from agentgraph_langchain import AgentGraphTrustCallback

callback = AgentGraphTrustCallback(
    did="did:agentgraph:my-agent-123",
    api_key="your-agentgraph-api-key",
    report_results=True,  # report execution results back to AgentGraph
)

llm = ChatOpenAI(callbacks=[callback])
llm.invoke("Hello, world!")
```

### Use as LangChain Tools

Give your agents the ability to verify trust and scan repos:

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_openai import ChatOpenAI
from agentgraph_langchain import TrustVerifyTool, SecurityScanTool

tools = [
    TrustVerifyTool(api_key="your-key"),
    SecurityScanTool(api_key="your-key"),
]

llm = ChatOpenAI(model="gpt-4")
# ... set up your agent with these tools
```

### Trust Badges

Embed trust badges in documentation or READMEs:

```python
from agentgraph_langchain import get_trust_badge_url

url = get_trust_badge_url("entity-123", style="compact")
# https://agentgraph.co/api/v1/trust/entity-123/badge?style=compact
```

### Security Scans

```python
import asyncio
from agentgraph_langchain import run_security_scan

async def main():
    results = await run_security_scan("owner/repo", token="ghp_optional")
    print(f"Vulnerabilities found: {results['vulnerabilities']}")

asyncio.run(main())
```

## Configuration

All functions accept a `base_url` parameter (default: `https://agentgraph.co/api/v1`).

For self-hosted instances:

```python
from agentgraph_langchain import verify_trust

await verify_trust("entity-1", base_url="https://your-instance.com/api/v1")
```

## License

MIT
