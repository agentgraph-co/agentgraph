"""CrewAI security scanner.

Scans CrewAI agent code for known vulnerability patterns including
framework-specific risks (role escalation, task injection, delegation
risks) plus all base patterns.
"""
from __future__ import annotations

from src.bridges.scanner_base import (
    BASE_PATTERNS,
    ScanResult,
    Vulnerability,
    aggregate_results,
    compile_patterns,
)
from src.bridges.scanner_base import (
    scan_skill as _base_scan_skill,
)

# --- CrewAI-specific vulnerability patterns ---

CREWAI_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "role_escalation",
        r"\brole\s*=\s*['\"].*(?:admin|root|system)",
        "critical",
        "CrewAI role escalation — agent assigned admin/root/system role",
    ),
    (
        "task_injection",
        r"\bTask\s*\(.*description\s*=.*\{.*\}",
        "critical",
        "CrewAI task description injection via template variables",
    ),
    (
        "crew_override",
        r"\bCrew\s*\(.*process\s*=.*sequential",
        "warning",
        "CrewAI sequential process — limited orchestration flexibility",
    ),
    (
        "delegation_risk",
        r"\ballow_delegation\s*=\s*True",
        "warning",
        "CrewAI unrestricted delegation enabled",
    ),
    (
        "custom_tool_risk",
        r"\b@tool\s*\n.*def\s+\w+.*:",
        "warning",
        "CrewAI custom tool definition — unverified tool code",
    ),
]

VULNERABILITY_PATTERNS = BASE_PATTERNS + CREWAI_PATTERNS
_COMPILED_PATTERNS = compile_patterns(VULNERABILITY_PATTERNS)


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan code for known vulnerability patterns."""
    return _base_scan_skill(
        code, skill_name=skill_name, compiled_patterns=_COMPILED_PATTERNS,
    )


def scan_manifest(manifest: dict) -> ScanResult:
    """Scan all agents/tasks/code in a CrewAI manifest.

    The manifest may have:
    - 'agents': list of agent objects with 'tools' containing code
    - 'tasks': list of task objects
    - 'code': top-level code string to scan
    """
    agents = manifest.get("agents", [])
    tasks = manifest.get("tasks", [])
    top_code = manifest.get("code", "")
    all_vulns: list[Vulnerability] = []
    scan_count = 0

    if top_code:
        result = scan_skill(top_code, skill_name="crew_code")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    for idx, agent in enumerate(agents):
        agent_role = agent.get("role", f"agent_{idx}")
        for tidx, tool in enumerate(agent.get("tools", [])):
            if isinstance(tool, dict):
                code = tool.get("code", "")
                tool_name = tool.get("name", f"{agent_role}_tool_{tidx}")
            else:
                continue
            if not code:
                continue
            result = scan_skill(code, skill_name=tool_name)
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

    for tidx, task in enumerate(tasks):
        desc = task.get("description", "")
        if desc:
            result = scan_skill(desc, skill_name=f"task_{tidx}")
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

    return aggregate_results(all_vulns, scan_count)
