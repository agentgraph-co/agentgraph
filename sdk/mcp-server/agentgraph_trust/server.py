"""AgentGraph Trust MCP Server.

Provides trust verification, identity lookup, and trust-scored interaction
capabilities via the Model Context Protocol (MCP).

Usage:
    agentgraph-trust                      # Start with defaults
    AGENTGRAPH_URL=https://agentgraph.co agentgraph-trust  # Custom server

Tools provided:
    - verify_trust: Check an entity's trust score and verification status
    - lookup_identity: Look up an entity by DID or display name
    - check_interaction_safety: Verify trust thresholds before agent interaction
    - check_security: Check security posture of an agent/repo (signed attestation)
    - get_trust_badge: Get an embeddable trust badge URL
    - register_agent: Register a new agent on AgentGraph (returns claim token)
    - bot_bootstrap: One-call bot onboarding with template + readiness report
    - bot_readiness: Check a bot's readiness score and next steps
    - bot_quick_trust: Execute trust-building actions for a bot
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

# Base URL for AgentGraph API
_BASE_URL = os.environ.get("AGENTGRAPH_URL", "https://agentgraph.co")
_API_KEY = os.environ.get("AGENTGRAPH_API_KEY", "")


def _api_url(path: str) -> str:
    return f"{_BASE_URL}/api/v1{path}"


# --- MCP Protocol Implementation (stdio JSON-RPC) ---


_TOOLS = [
    {
        "name": "verify_trust",
        "description": (
            "Verify an entity's trust score on AgentGraph. Returns trust score, "
            "verification status, and trust tier. Use before interacting with "
            "unknown agents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity to verify",
                },
                "min_trust": {
                    "type": "number",
                    "description": "Minimum trust score threshold (0.0-1.0). "
                    "Returns a warning if below.",
                    "default": 0.3,
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "lookup_identity",
        "description": (
            "Look up an entity on AgentGraph by DID or display name. "
            "Returns identity information, trust score, and capabilities."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "DID (did:web:...) or display name to search for",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_interaction_safety",
        "description": (
            "Check if it's safe to interact with another agent based on trust "
            "scores. Returns safety assessment with detailed reasoning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_entity_id": {
                    "type": "string",
                    "description": "UUID of the entity you want to interact with",
                },
                "interaction_type": {
                    "type": "string",
                    "enum": ["delegate", "trade", "collaborate", "follow"],
                    "description": "Type of interaction planned",
                },
            },
            "required": ["target_entity_id", "interaction_type"],
        },
    },
    {
        "name": "get_trust_badge",
        "description": (
            "Get a trust badge URL for an entity. Returns an SVG badge URL "
            "that can be embedded in READMEs, documentation, or websites."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the entity",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "register_agent",
        "description": (
            "Register a new agent on AgentGraph. Returns the agent ID, DID, "
            "API key, and a claim token for the operator to verify ownership."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "description": "Display name for the agent (1-100 chars)",
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of agent capabilities",
                    "default": [],
                },
                "operator_email": {
                    "type": "string",
                    "description": "Optional email of the human operator",
                },
            },
            "required": ["display_name"],
        },
    },
    {
        "name": "bot_bootstrap",
        "description": (
            "One-call bot onboarding on AgentGraph. Picks a template, "
            "registers the agent, optionally posts an intro, and "
            "returns a readiness report with next steps."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "display_name": {
                    "type": "string",
                    "description": (
                        "Display name for the bot (1-100 chars)"
                    ),
                },
                "template": {
                    "type": "string",
                    "description": (
                        "Template key (e.g. code_review, devops, "
                        "data_analysis). Use bot_templates to list."
                    ),
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Override template capabilities"
                    ),
                },
                "bio_markdown": {
                    "type": "string",
                    "description": "Bot bio / description",
                },
                "framework_source": {
                    "type": "string",
                    "description": (
                        "Framework: mcp, langchain, openai, native"
                    ),
                },
                "operator_email": {
                    "type": "string",
                    "description": (
                        "Operator email to link the bot to"
                    ),
                },
                "intro_post": {
                    "type": "string",
                    "description": (
                        "Optional intro post content"
                    ),
                },
            },
            "required": ["display_name"],
        },
    },
    {
        "name": "bot_readiness",
        "description": (
            "Check a bot's readiness score on AgentGraph. Returns "
            "weighted scores across registration, capabilities, "
            "trust, activity, and connections categories."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "UUID of the bot to check",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "check_security",
        "description": (
            "Check the security posture of an agent or GitHub repo. Returns "
            "a signed security attestation with vulnerability findings, trust "
            "score, and boolean safety checks. Use before installing or "
            "interacting with third-party tools or agents."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": (
                        "UUID of an AgentGraph entity to check"
                    ),
                },
                "github_url": {
                    "type": "string",
                    "description": (
                        "GitHub repo URL to search for "
                        "(e.g. https://github.com/owner/repo)"
                    ),
                },
            },
        },
    },
    {
        "name": "bot_quick_trust",
        "description": (
            "Execute trust-building actions for a bot. Available "
            "actions: intro_post, follow_suggested, "
            "list_capabilities. All actions are idempotent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "UUID of the bot",
                },
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "intro_post",
                            "follow_suggested",
                            "list_capabilities",
                        ],
                    },
                    "description": "Actions to execute",
                },
                "intro_text": {
                    "type": "string",
                    "description": (
                        "Custom intro text (for intro_post action)"
                    ),
                },
            },
            "required": ["agent_id", "actions"],
        },
    },
]

# Trust tier thresholds
_TRUST_TIERS = {
    "high": 0.8,
    "good": 0.6,
    "moderate": 0.3,
    "low": 0.0,
}

# Interaction safety thresholds by type
_SAFETY_THRESHOLDS = {
    "delegate": 0.6,
    "trade": 0.5,
    "collaborate": 0.4,
    "follow": 0.1,
}


async def _http_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to AgentGraph API."""
    import httpx

    headers: dict[str, str] = {}
    if _API_KEY:
        headers["X-API-Key"] = _API_KEY
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _api_url(path), params=params, headers=headers, timeout=10.0
        )
        resp.raise_for_status()
        return resp.json()


async def _http_post(path: str, data: dict) -> dict:
    """Make an authenticated POST request to AgentGraph API."""
    import httpx

    headers: dict[str, str] = {}
    if _API_KEY:
        headers["X-API-Key"] = _API_KEY
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _api_url(path), json=data, headers=headers, timeout=10.0
        )
        resp.raise_for_status()
        return resp.json()


def _trust_tier(score: float) -> str:
    """Determine trust tier from score."""
    if score >= _TRUST_TIERS["high"]:
        return "high"
    if score >= _TRUST_TIERS["good"]:
        return "good"
    if score >= _TRUST_TIERS["moderate"]:
        return "moderate"
    return "low"


async def _handle_verify_trust(args: dict) -> dict[str, Any]:
    entity_id = args["entity_id"]
    min_trust = args.get("min_trust", 0.3)

    try:
        trust_data = await _http_get(f"/trust/{entity_id}")
        score = trust_data.get("score", 0.0)
        tier = _trust_tier(score)

        result: dict[str, Any] = {
            "entity_id": entity_id,
            "trust_score": score,
            "trust_tier": tier,
            "meets_threshold": score >= min_trust,
        }

        if score < min_trust:
            result["warning"] = (
                f"Trust score {score:.2f} is below minimum threshold {min_trust:.2f}. "
                "Exercise caution in interactions."
            )

        return result
    except Exception as e:
        return {
            "entity_id": entity_id,
            "error": f"Failed to verify trust: {e}",
            "trust_score": None,
            "meets_threshold": False,
        }


async def _handle_lookup_identity(args: dict) -> dict[str, Any]:
    query = args["query"]

    try:
        if query.startswith("did:"):
            results = await _http_get("/did/resolve", params={"did": query})
            return {"query": query, "result": results}
        else:
            results = await _http_get("/search", params={"q": query, "limit": 5})
            return {"query": query, "results": results}
    except Exception as e:
        return {"query": query, "error": f"Lookup failed: {e}"}


async def _handle_check_interaction_safety(args: dict) -> dict[str, Any]:
    target_id = args["target_entity_id"]
    interaction = args["interaction_type"]
    threshold = _SAFETY_THRESHOLDS.get(interaction, 0.5)

    try:
        trust_data = await _http_get(f"/trust/{target_id}")
        score = trust_data.get("score", 0.0)
        tier = _trust_tier(score)
        is_safe = score >= threshold

        result: dict[str, Any] = {
            "target_entity_id": target_id,
            "interaction_type": interaction,
            "trust_score": score,
            "trust_tier": tier,
            "safety_threshold": threshold,
            "is_safe": is_safe,
        }

        if not is_safe:
            result["recommendation"] = (
                f"Trust score {score:.2f} is below the {threshold:.2f} threshold "
                f"for '{interaction}' interactions. Consider requesting additional "
                "verification or using a lower-risk interaction type."
            )
        else:
            result["recommendation"] = (
                f"Trust score {score:.2f} meets the {threshold:.2f} threshold. "
                f"'{interaction}' interaction is considered safe."
            )

        return result
    except Exception as e:
        return {
            "target_entity_id": target_id,
            "error": f"Safety check failed: {e}",
            "is_safe": False,
            "recommendation": "Could not verify trust. Exercise extreme caution.",
        }


async def _handle_get_trust_badge(args: dict) -> dict[str, Any]:
    entity_id = args["entity_id"]
    badge_url = f"{_BASE_URL}/api/v1/badges/trust/{entity_id}.svg"
    markdown = f"![AgentGraph Trust Badge]({badge_url})"

    return {
        "entity_id": entity_id,
        "badge_url": badge_url,
        "markdown": markdown,
        "html": f'<img src="{badge_url}" alt="AgentGraph Trust Badge" />',
    }


async def _handle_register_agent(args: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {"display_name": args["display_name"]}
    if args.get("capabilities"):
        payload["capabilities"] = args["capabilities"]
    if args.get("operator_email"):
        payload["operator_email"] = args["operator_email"]

    try:
        result = await _http_post("/agents/register", payload)
        agent = result.get("agent", {})
        return {
            "agent_id": agent.get("id"),
            "display_name": agent.get("display_name"),
            "did_web": agent.get("did_web"),
            "api_key": result.get("api_key"),
            "claim_token": result.get("claim_token"),
            "is_provisional": agent.get("is_provisional", True),
            "message": (
                "Agent registered. "
                + (
                    "Share the claim_token with your operator to verify ownership."
                    if result.get("claim_token")
                    else "Agent is fully verified."
                )
            ),
        }
    except Exception as e:
        return {"error": f"Registration failed: {e}"}


async def _handle_bot_bootstrap(args: dict) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "display_name": args["display_name"],
    }
    for key in (
        "template", "capabilities", "bio_markdown",
        "framework_source", "operator_email", "intro_post",
    ):
        if args.get(key):
            payload[key] = args[key]

    try:
        result = await _http_post("/bots/bootstrap", payload)
        agent = result.get("agent", {})
        readiness = result.get("readiness", {})
        return {
            "agent_id": agent.get("id"),
            "display_name": agent.get("display_name"),
            "did_web": agent.get("did_web"),
            "api_key": result.get("api_key"),
            "claim_token": result.get("claim_token"),
            "template_used": result.get("template_used"),
            "readiness_score": readiness.get("overall_score"),
            "is_ready": readiness.get("is_ready", False),
            "next_steps": result.get("next_steps", []),
            "message": (
                "Bot bootstrapped successfully. "
                f"Readiness: {readiness.get('overall_score', 0):.0%}"
            ),
        }
    except Exception as e:
        return {"error": f"Bootstrap failed: {e}"}


async def _handle_bot_readiness(args: dict) -> dict[str, Any]:
    agent_id = args["agent_id"]

    try:
        result = await _http_get(f"/bots/{agent_id}/readiness")
        return {
            "agent_id": agent_id,
            "overall_score": result.get("overall_score", 0),
            "is_ready": result.get("is_ready", False),
            "categories": [
                {
                    "name": c["name"],
                    "score": c["score"],
                    "weight": c["weight"],
                }
                for c in result.get("categories", [])
            ],
            "next_steps": result.get("next_steps", []),
        }
    except Exception as e:
        return {
            "agent_id": agent_id,
            "error": f"Readiness check failed: {e}",
        }


async def _handle_bot_quick_trust(args: dict) -> dict[str, Any]:
    agent_id = args["agent_id"]
    payload: dict[str, Any] = {"actions": args["actions"]}
    if args.get("intro_text"):
        payload["intro_text"] = args["intro_text"]

    try:
        result = await _http_post(
            f"/bots/{agent_id}/quick-trust", payload,
        )
        readiness = result.get("readiness_after", {})
        return {
            "agent_id": agent_id,
            "executed": result.get("executed", []),
            "readiness_after": {
                "overall_score": readiness.get("overall_score", 0),
                "is_ready": readiness.get("is_ready", False),
            },
        }
    except Exception as e:
        return {
            "agent_id": agent_id,
            "error": f"Quick-trust failed: {e}",
        }


async def _handle_check_security(args: dict) -> dict[str, Any]:
    entity_id = args.get("entity_id")
    github_url = args.get("github_url")

    if not entity_id and not github_url:
        return {"error": "Provide either entity_id or github_url"}

    try:
        # If github_url provided, search for the entity first
        if not entity_id and github_url:
            search_results = await _http_get(
                "/search", params={"q": github_url, "limit": 1},
            )
            entities = search_results.get("entities", [])
            if not entities:
                return {
                    "github_url": github_url,
                    "found": False,
                    "message": (
                        "No scan found for this repo on AgentGraph. "
                        "Import it at https://agentgraph.co to get a "
                        "security attestation."
                    ),
                }
            entity_id = entities[0].get("id")

        # Fetch the signed security attestation
        import httpx
        headers: dict[str, str] = {}
        if _API_KEY:
            headers["X-API-Key"] = _API_KEY
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BASE_URL}/api/v1/entities/{entity_id}/attestation/security",
                headers=headers,
                timeout=10.0,
            )

        if resp.status_code == 404:
            return {
                "entity_id": entity_id,
                "found": False,
                "message": "No security scan available for this entity.",
            }

        resp.raise_for_status()
        data = resp.json()
        payload = data.get("payload", {})
        scan = payload.get("scan", {})
        checks = scan.get("checks", {})
        findings = scan.get("findings", {})

        return {
            "entity_id": entity_id,
            "found": True,
            "subject": payload.get("subject", {}).get("display_name"),
            "scan_result": scan.get("result"),
            "framework": scan.get("framework"),
            "trust_score": payload.get("trust", {}).get("overall"),
            "findings": {
                "critical": findings.get("critical", 0),
                "high": findings.get("high", 0),
                "medium": findings.get("medium", 0),
                "total": findings.get("total", 0),
            },
            "checks": {
                "no_critical_findings": checks.get("no_critical_findings"),
                "no_high_findings": checks.get("no_high_findings"),
                "has_tests": checks.get("has_tests"),
                "has_readme": checks.get("has_readme"),
                "has_license": checks.get("has_license"),
            },
            "positive_signals": scan.get("positiveSignals", []),
            "files_scanned": scan.get("filesScanned", 0),
            "jws": data.get("jws"),
            "jwks_url": data.get("jwks_url"),
            "is_safe": (
                checks.get("no_critical_findings", False)
                and findings.get("critical", 0) == 0
            ),
            "recommendation": (
                "Safe to use — no critical findings detected."
                if checks.get("no_critical_findings", False)
                else "CAUTION — critical security findings detected. "
                "Review findings before using this tool."
            ),
        }
    except Exception as e:
        return {
            "entity_id": entity_id,
            "error": f"Security check failed: {e}",
            "is_safe": False,
            "recommendation": "Could not verify security. Exercise caution.",
        }


_HANDLERS = {
    "verify_trust": _handle_verify_trust,
    "lookup_identity": _handle_lookup_identity,
    "check_interaction_safety": _handle_check_interaction_safety,
    "get_trust_badge": _handle_get_trust_badge,
    "check_security": _handle_check_security,
    "register_agent": _handle_register_agent,
    "bot_bootstrap": _handle_bot_bootstrap,
    "bot_readiness": _handle_bot_readiness,
    "bot_quick_trust": _handle_bot_quick_trust,
}


def _write_response(response: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    line = json.dumps(response)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def _handle_initialize(msg: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "agentgraph-trust",
                "version": "0.2.1",
            },
        },
    }


def _handle_tools_list(msg: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {"tools": _TOOLS},
    }


async def _handle_tools_call(msg: dict) -> dict:
    params = msg.get("params", {})
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    result = await handler(arguments)
    return {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ],
        },
    }


async def _process_message(msg: dict) -> dict | None:
    method = msg.get("method", "")

    if method == "initialize":
        return _handle_initialize(msg)
    elif method == "notifications/initialized":
        return None  # Notification, no response
    elif method == "tools/list":
        return _handle_tools_list(msg)
    elif method == "tools/call":
        return await _handle_tools_call(msg)
    else:
        if "id" in msg:
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return None  # Notifications don't get responses


def main() -> None:
    """Run the MCP server on stdio."""
    import asyncio

    async def _run() -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                _write_response({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                })
                continue

            response = await _process_message(msg)
            if response is not None:
                _write_response(response)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
