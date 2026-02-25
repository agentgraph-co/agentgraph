"""LangChain security scanner.

Scans LangChain agent code for known vulnerability patterns including
framework-specific risks (tool injection, chain manipulation, unrestricted
agents) plus all base patterns.
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

# --- LangChain-specific vulnerability patterns ---

LANGCHAIN_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "tool_injection",
        r"\bTool\s*\(.*func\s*=.*exec\b",
        "critical",
        "LangChain Tool with exec function — code injection risk",
    ),
    (
        "chain_manipulation",
        r"\bLLMChain\s*\(.*prompt.*\{.*\}",
        "critical",
        "LangChain LLMChain with injectable prompt template",
    ),
    (
        "arbitrary_tool_call",
        r"\bagent\.run\s*\(\s*['\"].*eval\b",
        "critical",
        "LangChain agent calling eval via run()",
    ),
    (
        "unrestricted_agent",
        r"\bAgentType\s*\.\s*ZERO_SHOT",
        "warning",
        "LangChain zero-shot unrestricted agent type",
    ),
    (
        "memory_injection",
        r"\bConversationBufferMemory|ChatMessageHistory",
        "warning",
        "LangChain memory component — potential memory poisoning",
    ),
    (
        "custom_llm_chain",
        r"\bCustom.*LLM|custom_llm_chain",
        "warning",
        "Custom LLM chain — unverified model pipeline",
    ),
]

VULNERABILITY_PATTERNS = BASE_PATTERNS + LANGCHAIN_PATTERNS
_COMPILED_PATTERNS = compile_patterns(VULNERABILITY_PATTERNS)


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan code for known vulnerability patterns."""
    return _base_scan_skill(
        code, skill_name=skill_name, compiled_patterns=_COMPILED_PATTERNS,
    )


def scan_manifest(manifest: dict) -> ScanResult:
    """Scan all tools/code in a LangChain agent manifest.

    The manifest may have:
    - 'tools': list of tool objects with 'code' and optionally 'name'
    - 'code': top-level code string to scan
    """
    tools = manifest.get("tools", [])
    top_code = manifest.get("code", "")
    all_vulns: list[Vulnerability] = []
    scan_count = 0

    if top_code:
        result = scan_skill(top_code, skill_name="agent_code")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    for idx, tool in enumerate(tools):
        tool_name = tool.get("name", f"tool_{idx}")
        code = tool.get("code", "")
        if not code:
            continue
        result = scan_skill(code, skill_name=tool_name)
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    return aggregate_results(all_vulns, scan_count)
