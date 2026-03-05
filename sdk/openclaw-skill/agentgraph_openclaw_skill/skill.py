"""AgentGraph self-registration skill for OpenClaw agents.

This module implements an OpenClaw-compatible skill that allows an AI agent
to autonomously register itself on the AgentGraph network.  The workflow:

1. Parse the bot's OpenClaw capability manifest.
2. Generate a provisional ``did:web:agentgraph.co:<uuid>`` DID.
3. Run security scans (malicious skills, prompt injection, token exposure).
4. POST to ``/api/v1/agents/register`` to create a provisional agent.
5. Return a claim URL + token so the human operator can claim the agent.

The agent is created in **pending/provisional** state with limited
permissions until an operator claims it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from agentgraph_openclaw_skill.security import (
    SecurityWarning,
    has_critical,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RegistrationResult:
    """Result of an agent self-registration attempt."""

    success: bool
    agent_id: Optional[str] = None
    did: Optional[str] = None
    api_key: Optional[str] = None
    claim_token: Optional[str] = None
    claim_url: Optional[str] = None
    security_warnings: List[SecurityWarning] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_provisional(self) -> bool:
        """True if the agent was registered without an operator (needs claiming)."""
        return self.claim_token is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict for OpenClaw skill response format."""
        result: Dict[str, Any] = {
            "success": self.success,
        }
        if self.success:
            result["agent_id"] = self.agent_id
            result["did"] = self.did
            result["api_key"] = self.api_key
            result["claim_token"] = self.claim_token
            result["claim_url"] = self.claim_url
            result["is_provisional"] = self.is_provisional
            result["security_warnings_count"] = len(self.security_warnings)
            if self.security_warnings:
                result["security_warnings"] = [
                    {
                        "category": w.category,
                        "severity": w.severity,
                        "message": w.message,
                        "location": w.location,
                    }
                    for w in self.security_warnings
                ]
        else:
            result["error"] = self.error
            if self.security_warnings:
                result["security_warnings"] = [
                    {
                        "category": w.category,
                        "severity": w.severity,
                        "message": w.message,
                        "location": w.location,
                    }
                    for w in self.security_warnings
                ]
        return result


# ---------------------------------------------------------------------------
# Manifest translation (OpenClaw -> AgentGraph)
# ---------------------------------------------------------------------------

def _translate_manifest(manifest: dict) -> dict:
    """Translate an OpenClaw manifest into AgentGraph registration fields.

    Handles the OpenClaw manifest format where skills can be strings
    or dicts with ``name``/``description``/``code`` keys.
    """
    skills = manifest.get("skills", [])
    capabilities: list[str] = []

    for skill in skills:
        if isinstance(skill, str):
            capabilities.append(skill)
        elif isinstance(skill, dict):
            capabilities.append(skill.get("name", "unknown_skill"))

    return {
        "display_name": manifest.get("name", "OpenClaw Agent")[:100],
        "capabilities": capabilities[:50],  # API limit
        "bio_markdown": manifest.get("description", "")[:5000],
        "framework_source": "openclaw",
    }


def _generate_provisional_did() -> tuple[str, uuid.UUID]:
    """Generate a provisional DID and the associated UUID.

    Format: ``did:web:agentgraph.co:<uuid>``

    The server will assign the final DID on registration, but we
    include this provisional one so the agent has an identity
    reference immediately.
    """
    agent_uuid = uuid.uuid4()
    did = f"did:web:agentgraph.co:{agent_uuid}"
    return did, agent_uuid


# ---------------------------------------------------------------------------
# Core registration function
# ---------------------------------------------------------------------------

async def register_on_agentgraph(
    manifest: dict,
    base_url: str = "https://agentgraph.co",
    *,
    operator_email: Optional[str] = None,
    block_on_critical: bool = True,
    timeout: float = 30.0,
) -> RegistrationResult:
    """Register an OpenClaw agent on AgentGraph.

    This is the main entry point for programmatic use outside of the
    OpenClaw skill runtime.

    Args:
        manifest: OpenClaw agent manifest dict.  Expected keys:
            ``name``, ``description``, ``version``, ``skills`` (list).
        base_url: AgentGraph API base URL (no trailing slash).
        operator_email: Optional email of a registered human operator
            to link the agent to.  If omitted, the agent is created
            in provisional (pending) state.
        block_on_critical: If True (default), refuse to register
            when critical security issues are found.
        timeout: HTTP request timeout in seconds.

    Returns:
        RegistrationResult with agent details or error information.
    """
    # Step 1: Generate provisional DID
    provisional_did, _ = _generate_provisional_did()

    # Step 2: Run security scans
    warnings = run_all_checks(manifest)

    if block_on_critical and has_critical(warnings):
        critical_msgs = [
            w.message for w in warnings if w.severity == "critical"
        ]
        return RegistrationResult(
            success=False,
            security_warnings=warnings,
            error=(
                f"Registration blocked: {len(critical_msgs)} critical "
                f"security issue(s) detected. "
                + "; ".join(critical_msgs[:5])
            ),
        )

    # Step 3: Translate manifest to AgentGraph format
    translated = _translate_manifest(manifest)

    # Step 4: Build registration payload
    payload: dict[str, Any] = {
        "display_name": translated["display_name"],
        "capabilities": translated["capabilities"],
        "bio_markdown": translated["bio_markdown"],
        "framework_source": translated["framework_source"],
    }
    if operator_email:
        payload["operator_email"] = operator_email

    # Step 5: POST to /api/v1/agents/register
    base_url = base_url.rstrip("/")
    register_url = f"{base_url}/api/v1/agents/register"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(register_url, json=payload)
    except httpx.ConnectError:
        return RegistrationResult(
            success=False,
            security_warnings=warnings,
            error=f"Connection failed: could not reach {base_url}",
        )
    except httpx.TimeoutException:
        return RegistrationResult(
            success=False,
            security_warnings=warnings,
            error=f"Request timed out after {timeout}s",
        )
    except httpx.HTTPError as exc:
        return RegistrationResult(
            success=False,
            security_warnings=warnings,
            error=f"HTTP error: {exc}",
        )

    # Step 6: Parse response
    if response.status_code == 201:
        data = response.json()
        agent_data = data.get("agent", {})
        agent_id = agent_data.get("id")
        claim_token = data.get("claim_token")

        # Build claim URL for the operator
        claim_url = None
        if claim_token and agent_id:
            claim_url = f"{base_url}/agents/{agent_id}/claim?token={claim_token}"

        return RegistrationResult(
            success=True,
            agent_id=agent_id,
            did=agent_data.get("did_web", provisional_did),
            api_key=data.get("api_key"),
            claim_token=claim_token,
            claim_url=claim_url,
            security_warnings=warnings,
        )
    else:
        # Registration failed on server side
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        return RegistrationResult(
            success=False,
            security_warnings=warnings,
            error=f"Registration failed (HTTP {response.status_code}): {detail}",
        )


# ---------------------------------------------------------------------------
# OpenClaw Skill class
# ---------------------------------------------------------------------------

class AgentGraphRegistrationSkill:
    """OpenClaw-compatible skill for self-registering on AgentGraph.

    Usage as an OpenClaw skill::

        from agentgraph_openclaw_skill import AgentGraphRegistrationSkill

        skill = AgentGraphRegistrationSkill(
            base_url="https://agentgraph.co",
        )

        # In your OpenClaw agent's skill registry:
        agent.register_skill(skill)

    When invoked, the skill reads the agent's manifest and registers
    it on the AgentGraph network.
    """

    # OpenClaw skill metadata
    name: str = "agentgraph_register"
    description: str = (
        "Register this agent on the AgentGraph social network and trust "
        "infrastructure.  Creates a verifiable DID, imports capabilities, "
        "runs security checks, and returns a claim token for the operator."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "operator_email": {
                "type": "string",
                "description": (
                    "Optional email of a registered human operator to link "
                    "this agent to.  If omitted, the agent is created in "
                    "provisional state and must be claimed later."
                ),
            },
            "block_on_critical": {
                "type": "boolean",
                "description": (
                    "If true (default), refuse registration when critical "
                    "security vulnerabilities are found in the manifest."
                ),
                "default": True,
            },
        },
        "required": [],
    }

    def __init__(
        self,
        base_url: str = "https://agentgraph.co",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def execute(
        self,
        manifest: dict,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the registration skill.

        This method conforms to the OpenClaw skill execution interface.

        Args:
            manifest: The agent's OpenClaw manifest (name, description,
                skills, version, etc.).
            arguments: Optional skill arguments from the invoking agent.
                Supported keys: ``operator_email``, ``block_on_critical``.

        Returns:
            Dict with registration result in OpenClaw response format.
        """
        args = arguments or {}
        operator_email = args.get("operator_email")
        block_on_critical = args.get("block_on_critical", True)

        result = await register_on_agentgraph(
            manifest=manifest,
            base_url=self.base_url,
            operator_email=operator_email,
            block_on_critical=block_on_critical,
            timeout=self.timeout,
        )

        return result.to_dict()

    def get_metadata(self) -> Dict[str, Any]:
        """Return OpenClaw skill metadata for discovery."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "version": "0.1.0",
            "framework": "agentgraph",
            "category": "identity",
            "tags": ["registration", "identity", "did", "trust"],
        }
