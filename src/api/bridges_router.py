"""Bridges API router — endpoints for framework bridge operations.

Supports OpenClaw, LangChain, and CrewAI agent import, security scanning,
and framework status.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import Entity

router = APIRouter(prefix="/bridges", tags=["bridges"])


# --- Request/Response schemas ---


class OpenClawManifest(BaseModel):
    """OpenClaw agent manifest for import."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    capabilities: list[str] = Field(default_factory=list)
    version: str = Field(default="1.0.0")
    skills: list[dict[str, Any]] = Field(default_factory=list)


class LangChainManifest(BaseModel):
    """LangChain agent manifest for import."""

    name: str = Field(default="LangChain Agent", max_length=100)
    description: str = Field(default="", max_length=5000)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    agent_type: str = Field(default="zero_shot")
    model: str = Field(default="unknown")
    version: str = Field(default="1.0.0")
    code: str = Field(default="")  # Optional code to scan


class CrewAIManifest(BaseModel):
    """CrewAI agent manifest for import."""

    name: str = Field(default="CrewAI Agent", max_length=100)
    description: str = Field(default="", max_length=5000)
    agents: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    process: str = Field(default="sequential")
    version: str = Field(default="1.0.0")
    code: str = Field(default="")  # Optional code to scan


class VulnerabilityOut(BaseModel):
    pattern: str
    severity: str
    location: str
    match: str


class ScanResultOut(BaseModel):
    id: str
    entity_id: str
    framework: str
    scan_result: str
    vulnerabilities: list[VulnerabilityOut]
    scanned_at: str


class ImportResult(BaseModel):
    entity_id: str
    display_name: str
    framework_source: str
    framework_trust_modifier: float
    scan: ScanResultOut


class RescanRequest(BaseModel):
    """Manifest for rescanning an entity."""

    skills: list[dict[str, Any]] = Field(default_factory=list)


class LangChainRescanRequest(BaseModel):
    """Manifest for rescanning a LangChain entity."""

    tools: list[dict[str, Any]] = Field(default_factory=list)
    code: str = Field(default="")


class CrewAIRescanRequest(BaseModel):
    """Manifest for rescanning a CrewAI entity."""

    agents: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    code: str = Field(default="")


class FrameworkStatusOut(BaseModel):
    supported_frameworks: list[str]
    entity_counts: dict[str, int]
    scan_results: dict[str, int]


# --- Helper ---


def _scan_to_out(scan) -> ScanResultOut:
    """Convert a FrameworkSecurityScan model to response schema."""
    vulns = scan.vulnerabilities or []
    return ScanResultOut(
        id=str(scan.id),
        entity_id=str(scan.entity_id),
        framework=scan.framework,
        scan_result=scan.scan_result,
        vulnerabilities=[
            VulnerabilityOut(
                pattern=v.get("pattern", ""),
                severity=v.get("severity", ""),
                location=v.get("location", ""),
                match=v.get("match", ""),
            )
            for v in vulns
        ],
        scanned_at=scan.scanned_at.isoformat() if scan.scanned_at else "",
    )


# --- OpenClaw Endpoints ---


@router.post(
    "/openclaw/import",
    response_model=ImportResult,
    dependencies=[Depends(rate_limit_writes)],
)
async def import_openclaw_agent(
    manifest: OpenClawManifest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Import an OpenClaw agent manifest into AgentGraph.

    Creates an entity profile, runs security scanning, and applies
    framework trust modifiers. The importing user becomes the agent operator.
    """
    from src.audit import log_action
    from src.bridges.openclaw.registry import import_openclaw_agent as do_import

    agent, scan = await do_import(
        db=db,
        manifest=manifest.dict(),
        operator_entity=current_entity,
    )

    await log_action(
        db,
        action="bridges.openclaw.import",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "agent_name": agent.display_name,
            "scan_result": scan.scan_result,
            "framework": "openclaw",
        },
    )

    return ImportResult(
        entity_id=str(agent.id),
        display_name=agent.display_name,
        framework_source=agent.framework_source or "openclaw",
        framework_trust_modifier=agent.framework_trust_modifier or 1.0,
        scan=_scan_to_out(scan),
    )


@router.get(
    "/openclaw/scan/{entity_id}",
    response_model=ScanResultOut,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_scan_result(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest security scan result for an entity."""
    from src.bridges.openclaw.registry import get_latest_scan

    scan = await get_latest_scan(db, entity_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="No scan found for this entity")

    return _scan_to_out(scan)


@router.post(
    "/openclaw/rescan/{entity_id}",
    response_model=ScanResultOut,
    dependencies=[Depends(rate_limit_writes)],
)
async def rescan_entity(
    entity_id: uuid.UUID,
    body: RescanRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a rescan of an entity with updated skills.

    Only the operator or an admin can rescan an entity.
    A clean rescan removes the trust penalty (sets modifier to 1.0).
    """
    from src.audit import log_action
    from src.bridges.openclaw.registry import rescan_entity as do_rescan

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Authorization: must be operator or admin
    if entity.operator_id != current_entity.id and not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to rescan this entity")

    manifest = {"skills": body.skills}
    scan = await do_rescan(db, entity, manifest)

    await log_action(
        db,
        action="bridges.openclaw.rescan",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={
            "scan_result": scan.scan_result,
            "framework": entity.framework_source or "openclaw",
        },
    )

    return _scan_to_out(scan)


# --- LangChain Endpoints ---


@router.post(
    "/langchain/import",
    response_model=ImportResult,
    dependencies=[Depends(rate_limit_writes)],
)
async def import_langchain_agent(
    manifest: LangChainManifest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Import a LangChain agent manifest into AgentGraph.

    Creates an entity profile, runs security scanning, and applies
    framework trust modifiers. The importing user becomes the agent operator.
    """
    from src.audit import log_action
    from src.bridges.langchain.registry import import_langchain_agent as do_import

    agent, scan = await do_import(
        db=db,
        manifest=manifest.dict(),
        operator_entity=current_entity,
    )

    await log_action(
        db,
        action="bridges.langchain.import",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "agent_name": agent.display_name,
            "scan_result": scan.scan_result,
            "framework": "langchain",
        },
    )

    return ImportResult(
        entity_id=str(agent.id),
        display_name=agent.display_name,
        framework_source=agent.framework_source or "langchain",
        framework_trust_modifier=agent.framework_trust_modifier or 1.0,
        scan=_scan_to_out(scan),
    )


@router.get(
    "/langchain/scan/{entity_id}",
    response_model=ScanResultOut,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_langchain_scan(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest security scan result for a LangChain entity."""
    from src.bridges.langchain.registry import get_latest_scan

    scan = await get_latest_scan(db, entity_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="No scan found for this entity")

    return _scan_to_out(scan)


@router.post(
    "/langchain/rescan/{entity_id}",
    response_model=ScanResultOut,
    dependencies=[Depends(rate_limit_writes)],
)
async def rescan_langchain_entity(
    entity_id: uuid.UUID,
    body: LangChainRescanRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a rescan of a LangChain entity with updated tools/code.

    Only the operator or an admin can rescan an entity.
    A clean rescan removes the trust penalty (sets modifier to 1.0).
    """
    from src.audit import log_action
    from src.bridges.langchain.registry import rescan_entity as do_rescan

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Authorization: must be operator or admin
    if entity.operator_id != current_entity.id and not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to rescan this entity")

    manifest = {"tools": body.tools, "code": body.code}
    scan = await do_rescan(db, entity, manifest)

    await log_action(
        db,
        action="bridges.langchain.rescan",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={
            "scan_result": scan.scan_result,
            "framework": entity.framework_source or "langchain",
        },
    )

    return _scan_to_out(scan)


# --- CrewAI Endpoints ---


@router.post(
    "/crewai/import",
    response_model=ImportResult,
    dependencies=[Depends(rate_limit_writes)],
)
async def import_crewai_agent(
    manifest: CrewAIManifest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Import a CrewAI manifest into AgentGraph.

    Creates an entity profile, runs security scanning, and applies
    framework trust modifiers. The importing user becomes the agent operator.
    """
    from src.audit import log_action
    from src.bridges.crewai.registry import import_crewai_agent as do_import

    agent, scan = await do_import(
        db=db,
        manifest=manifest.dict(),
        operator_entity=current_entity,
    )

    await log_action(
        db,
        action="bridges.crewai.import",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=agent.id,
        details={
            "agent_name": agent.display_name,
            "scan_result": scan.scan_result,
            "framework": "crewai",
        },
    )

    return ImportResult(
        entity_id=str(agent.id),
        display_name=agent.display_name,
        framework_source=agent.framework_source or "crewai",
        framework_trust_modifier=agent.framework_trust_modifier or 1.0,
        scan=_scan_to_out(scan),
    )


@router.get(
    "/crewai/scan/{entity_id}",
    response_model=ScanResultOut,
    dependencies=[Depends(rate_limit_reads)],
)
async def get_crewai_scan(
    entity_id: uuid.UUID,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest security scan result for a CrewAI entity."""
    from src.bridges.crewai.registry import get_latest_scan

    scan = await get_latest_scan(db, entity_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="No scan found for this entity")

    return _scan_to_out(scan)


@router.post(
    "/crewai/rescan/{entity_id}",
    response_model=ScanResultOut,
    dependencies=[Depends(rate_limit_writes)],
)
async def rescan_crewai_entity(
    entity_id: uuid.UUID,
    body: CrewAIRescanRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a rescan of a CrewAI entity with updated agents/tasks/code.

    Only the operator or an admin can rescan an entity.
    A clean rescan removes the trust penalty (sets modifier to 1.0).
    """
    from src.audit import log_action
    from src.bridges.crewai.registry import rescan_entity as do_rescan

    entity = await db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Authorization: must be operator or admin
    if entity.operator_id != current_entity.id and not current_entity.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to rescan this entity")

    manifest = {"agents": body.agents, "tasks": body.tasks, "code": body.code}
    scan = await do_rescan(db, entity, manifest)

    await log_action(
        db,
        action="bridges.crewai.rescan",
        entity_id=current_entity.id,
        resource_type="entity",
        resource_id=entity_id,
        details={
            "scan_result": scan.scan_result,
            "framework": entity.framework_source or "crewai",
        },
    )

    return _scan_to_out(scan)


# --- Status Endpoint ---


@router.get(
    "/status",
    response_model=FrameworkStatusOut,
    dependencies=[Depends(rate_limit_reads)],
)
async def bridge_status(
    db: AsyncSession = Depends(get_db),
):
    """List supported frameworks and entity counts per framework.

    Public endpoint — no authentication required for status check.
    """
    from src.bridges.openclaw.registry import get_framework_stats

    stats = await get_framework_stats(db)
    # Ensure all frameworks are listed
    stats["supported_frameworks"] = ["mcp", "openclaw", "langchain", "crewai"]
    return FrameworkStatusOut(**stats)
