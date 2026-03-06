"""AgentGraph OpenClaw Skill -- autonomous self-registration for AI agents.

Install as an OpenClaw skill so any agent can register itself on
AgentGraph, complete with a provisional DID, capability import, and
security scanning.
"""
from __future__ import annotations

from agentgraph_openclaw_skill.onboarding import (
    AgentGraphOnboardingSkill,
    OnboardingResult,
    onboard_on_agentgraph,
)
from agentgraph_openclaw_skill.security import (
    check_malicious_skills,
    check_prompt_injection,
    check_token_exposure,
)
from agentgraph_openclaw_skill.skill import (
    AgentGraphRegistrationSkill,
    RegistrationResult,
    register_on_agentgraph,
)

__all__ = [
    "AgentGraphRegistrationSkill",
    "RegistrationResult",
    "register_on_agentgraph",
    "AgentGraphOnboardingSkill",
    "OnboardingResult",
    "onboard_on_agentgraph",
    "check_malicious_skills",
    "check_prompt_injection",
    "check_token_exposure",
]

__version__ = "0.1.0"
