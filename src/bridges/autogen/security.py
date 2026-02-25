"""AutoGen security scanner.

Scans AutoGen agent code for known vulnerability patterns including
framework-specific risks (code execution config, unrestricted tool access,
dangerous function names) plus all base patterns.
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

# --- AutoGen-specific vulnerability patterns ---

AUTOGEN_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "code_execution_enabled",
        r"\bcode_execution_config\s*=\s*\{",
        "critical",
        "AutoGen code_execution_config enabled — allows arbitrary code execution",
    ),
    (
        "code_execution_config_true",
        r"\bcode_execution_config\s*=\s*True",
        "critical",
        "AutoGen code_execution_config set to True — unrestricted code execution",
    ),
    (
        "unrestricted_tool_access",
        r"\bfunction_map\s*=\s*\{[^}]*\bexec\b",
        "critical",
        "AutoGen function_map includes exec — unrestricted tool access",
    ),
    (
        "dangerous_function_exec",
        r"\bregister_function\s*\(.*\bexec\b",
        "critical",
        "AutoGen register_function with exec — dangerous function registration",
    ),
    (
        "dangerous_function_eval",
        r"\bregister_function\s*\(.*\beval\b",
        "critical",
        "AutoGen register_function with eval — dangerous function registration",
    ),
    (
        "shell_command_access",
        r"\buse_docker\s*=\s*False",
        "critical",
        "AutoGen use_docker=False — shell commands run directly on host",
    ),
    (
        "unrestricted_agent",
        r"\bUserProxyAgent\s*\(",
        "warning",
        "AutoGen UserProxyAgent — can execute code with human proxy permissions",
    ),
    (
        "group_chat_unrestricted",
        r"\bGroupChat\s*\(.*max_round\s*=\s*\d{3,}",
        "warning",
        "AutoGen GroupChat with high max_round — potential runaway conversations",
    ),
    (
        "auto_reply_unrestricted",
        r"\bmax_consecutive_auto_reply\s*=\s*None",
        "warning",
        "AutoGen unlimited auto-replies — potential infinite loop",
    ),
]

VULNERABILITY_PATTERNS = BASE_PATTERNS + AUTOGEN_PATTERNS
_COMPILED_PATTERNS = compile_patterns(VULNERABILITY_PATTERNS)


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan code for known vulnerability patterns."""
    return _base_scan_skill(
        code, skill_name=skill_name, compiled_patterns=_COMPILED_PATTERNS,
    )


def scan_manifest(manifest: dict) -> ScanResult:
    """Scan all agents/code in an AutoGen manifest.

    The manifest may have:
    - 'agents': list of agent objects with optional code/functions
    - 'code_execution_config': config dict to check
    - 'code': top-level code string to scan
    """
    agents = manifest.get("agents", [])
    code_exec_config = manifest.get("code_execution_config", {})
    top_code = manifest.get("code", "")
    all_vulns: list[Vulnerability] = []
    scan_count = 0

    if top_code:
        result = scan_skill(top_code, skill_name="agent_code")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    if code_exec_config:
        config_str = str(code_exec_config)
        result = scan_skill(config_str, skill_name="code_execution_config")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    for idx, agent in enumerate(agents):
        agent_name = agent.get("name", f"agent_{idx}")
        agent_type = agent.get("type", agent.get("agent_type", "unknown"))

        agent_code = agent.get("code", "")
        if agent_code:
            result = scan_skill(
                agent_code, skill_name=f"{agent_name}_{agent_type}",
            )
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

        for fidx, func in enumerate(agent.get("functions", [])):
            if isinstance(func, dict):
                func_code = func.get("code", "")
                func_name = func.get("name", f"{agent_name}_func_{fidx}")
            else:
                continue
            if not func_code:
                continue
            result = scan_skill(func_code, skill_name=func_name)
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

    return aggregate_results(all_vulns, scan_count)
