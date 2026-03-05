"""AgentGraph bridge for Pydantic AI — register agents in < 5 lines."""
from __future__ import annotations

import functools
from typing import Any, Callable, Dict, List, Optional, TypeVar

from agentgraph_bridge_pydantic.client import AgentGraphClient

__all__ = ["AgentGraphClient", "register_agent", "agentgraph_register"]

F = TypeVar("F", bound=Callable[..., Any])


async def register_agent(
    api_url: str,
    api_key: str,
    display_name: str,
    capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Register a single Pydantic AI agent with AgentGraph.

    Args:
        api_url: AgentGraph instance URL.
        api_key: API key for authentication.
        display_name: Agent display name.
        capabilities: Optional capability list.

    Returns:
        Registration response dict.
    """
    client = AgentGraphClient(api_url, api_key)
    return await client.register(
        display_name=display_name,
        capabilities=capabilities,
        framework_source="pydantic_ai",
    )


def agentgraph_register(
    api_url: str,
    api_key: str,
    display_name: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
) -> Callable[[F], F]:
    """Decorator that registers a Pydantic AI agent factory with AgentGraph.

    The decorated function runs normally; registration happens once at
    decoration time (lazily on first call) and the result is stored as
    a ``_agentgraph_registration`` attribute on the function.

    Args:
        api_url: AgentGraph instance URL.
        api_key: API key for authentication.
        display_name: Agent display name. Defaults to the function name.
        capabilities: Optional capability list.

    Returns:
        Decorator that preserves the original function signature.

    Example::

        @agentgraph_register("https://agentgraph.co", "ag_key_...")
        def my_agent():
            return Agent(model="openai:gpt-4o", ...)
    """

    def decorator(fn: F) -> F:
        name = display_name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        # Store registration metadata for lazy async resolution
        wrapper._agentgraph_config = {  # type: ignore[attr-defined]
            "api_url": api_url,
            "api_key": api_key,
            "display_name": name,
            "capabilities": capabilities,
            "framework_source": "pydantic_ai",
        }
        wrapper._agentgraph_registration = None  # type: ignore[attr-defined]

        async def do_register() -> Dict[str, Any]:
            """Call this to trigger the actual registration."""
            if wrapper._agentgraph_registration is not None:  # type: ignore[attr-defined]
                return wrapper._agentgraph_registration  # type: ignore[attr-defined]
            client = AgentGraphClient(api_url, api_key)
            result = await client.register(
                display_name=name,
                capabilities=capabilities,
                framework_source="pydantic_ai",
            )
            wrapper._agentgraph_registration = result  # type: ignore[attr-defined]
            return result

        wrapper.agentgraph_register = do_register  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
