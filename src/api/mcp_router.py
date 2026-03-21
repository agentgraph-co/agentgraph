"""MCP bridge API endpoints.

Provides endpoints for MCP-compatible agents to:
- List available tools
- Execute tool calls
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.bridges.mcp_handler import MCPError, handle_tool_call
from src.bridges.mcp_tools import get_tool_definitions
from src.database import get_db
from src.models import Entity

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    tool_name: str
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    is_error: bool = False


@router.get("/tools", dependencies=[Depends(rate_limit_reads)])
async def list_tools():
    """List all available MCP tools.

    Returns tool definitions following the MCP schema.
    No authentication required — tool discovery is public.
    """
    return {"tools": get_tool_definitions()}


@router.post(
    "/tools/call", response_model=ToolCallResponse,
    dependencies=[Depends(rate_limit_writes)],
)
async def call_tool(
    body: ToolCallRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Execute an MCP tool call.

    Requires authentication via Bearer token or X-API-Key.
    """
    try:
        result = await handle_tool_call(
            tool_name=body.name,
            arguments=body.arguments,
            entity=current_entity,
            db=db,
        )

        # Audit log
        from src.audit import log_action

        await log_action(
            db,
            action="mcp.tool_call",
            entity_id=current_entity.id,
            resource_type="mcp_tool",
            details={"tool_name": body.name},
        )

        return ToolCallResponse(
            tool_name=body.name,
            result=result,
            is_error=False,
        )
    except MCPError as e:
        return ToolCallResponse(
            tool_name=body.name,
            error={"code": e.code, "message": e.message},
            is_error=True,
        )
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).exception("Tool execution failed")
        raise HTTPException(status_code=500, detail="Tool execution failed")
