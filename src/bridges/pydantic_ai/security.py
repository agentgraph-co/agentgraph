"""Pydantic AI security scanner.

Scans Pydantic AI agent code for known vulnerability patterns including
framework-specific risks (unsafe tool definitions, dynamic model loading,
unrestricted result types) plus all base patterns.
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

# --- Pydantic AI-specific vulnerability patterns ---

PYDANTIC_AI_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "unsafe_tool_decorator",
        r"@\w+\.tool\s*\(.*\bexec\b",
        "critical",
        "Pydantic AI tool decorator with exec — arbitrary code execution",
    ),
    (
        "dynamic_model_loading",
        r"\bModel\s*\.\s*from_name\s*\(\s*['\"].*\{",
        "critical",
        "Pydantic AI dynamic model loading with injectable name",
    ),
    (
        "unsafe_result_validator",
        r"@\w+\.result_validator\s*\n.*\bexec\b",
        "critical",
        "Pydantic AI result validator with exec — arbitrary code execution",
    ),
    (
        "unrestricted_system_prompt",
        r"\bsystem_prompt\s*=.*\{.*\}",
        "critical",
        "Pydantic AI system prompt with injectable template variables",
    ),
    (
        "tool_plain_exec",
        r"@\w+\.tool_plain\s*\n.*\b(exec|eval|os\.system)\b",
        "critical",
        "Pydantic AI tool_plain with dangerous function call",
    ),
    (
        "dynamic_tool_registration",
        r"\bagent\s*\.\s*tool\s*\(\s*func\s*=",
        "warning",
        "Pydantic AI dynamic tool registration — unverified tool function",
    ),
    (
        "retry_manipulation",
        r"\bretries\s*=\s*\d{3,}",
        "warning",
        "Pydantic AI excessive retries — potential resource exhaustion",
    ),
    (
        "untyped_result",
        r"\bresult_type\s*=\s*Any\b",
        "warning",
        "Pydantic AI untyped result — no output validation",
    ),
]

VULNERABILITY_PATTERNS = BASE_PATTERNS + PYDANTIC_AI_PATTERNS
_COMPILED_PATTERNS = compile_patterns(VULNERABILITY_PATTERNS)


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan code for known vulnerability patterns."""
    return _base_scan_skill(
        code, skill_name=skill_name, compiled_patterns=_COMPILED_PATTERNS,
    )


def scan_manifest(manifest: dict) -> ScanResult:
    """Scan all tools/code in a Pydantic AI agent manifest.

    The manifest may have:
    - 'tools': list of tool objects with optional code
    - 'system_prompt': system prompt string to check
    - 'code': top-level code string to scan
    """
    tools = manifest.get("tools", [])
    system_prompt = manifest.get("system_prompt", "")
    top_code = manifest.get("code", "")
    all_vulns: list[Vulnerability] = []
    scan_count = 0

    if top_code:
        result = scan_skill(top_code, skill_name="agent_code")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    if system_prompt:
        result = scan_skill(system_prompt, skill_name="system_prompt")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    for idx, tool in enumerate(tools):
        if isinstance(tool, dict):
            tool_name = tool.get("name", f"tool_{idx}")
            code = tool.get("code", "")
        else:
            continue
        if not code:
            continue
        result = scan_skill(code, skill_name=tool_name)
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    return aggregate_results(all_vulns, scan_count)
