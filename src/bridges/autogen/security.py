"""AutoGen security scanner.

Scans AutoGen agent code for known vulnerability patterns including
framework-specific risks (code execution config, unrestricted tool access,
dangerous function names) plus all base patterns from the OpenClaw scanner.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Vulnerability:
    """A single detected vulnerability."""

    pattern: str
    severity: str  # "warning" or "critical"
    location: str  # description of where found
    match: str  # the matched text


@dataclass
class ScanResult:
    """Result of scanning code or a manifest."""

    vulnerabilities: list = field(default_factory=list)
    severity: str = "clean"  # "clean", "warnings", "critical"
    details: str = ""

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "severity": self.severity,
            "details": self.details,
            "vulnerability_count": len(self.vulnerabilities),
            "vulnerabilities": [
                {
                    "pattern": v.pattern,
                    "severity": v.severity,
                    "location": v.location,
                    "match": v.match,
                }
                for v in self.vulnerabilities
            ],
        }


# --- Base vulnerability patterns (shared with OpenClaw) ---

BASE_PATTERNS: list = [
    # Command injection — critical
    (
        "command_injection_os_system",
        r"\bos\s*\.\s*system\s*\(",
        "critical",
        "Direct OS command execution via os.system()",
    ),
    (
        "command_injection_subprocess",
        r"\bsubprocess\s*\.\s*(call|run|Popen|check_output|check_call)\s*\(",
        "critical",
        "Subprocess command execution",
    ),
    (
        "command_injection_eval",
        r"\beval\s*\(",
        "critical",
        "Dynamic code execution via eval()",
    ),
    (
        "command_injection_exec",
        r"\bexec\s*\(",
        "critical",
        "Dynamic code execution via exec()",
    ),
    (
        "command_injection_compile",
        r"\bcompile\s*\(.*['\"]exec['\"]",
        "critical",
        "Dynamic code compilation with exec mode",
    ),
    (
        "command_injection_popen",
        r"\bos\s*\.\s*popen\s*\(",
        "critical",
        "Command execution via os.popen()",
    ),
    (
        "command_injection_spawn",
        r"\bos\s*\.\s*spawn",
        "critical",
        "Command execution via os.spawn*()",
    ),
    # Path traversal — critical
    (
        "path_traversal_dotdot",
        r"\.\./",
        "critical",
        "Path traversal via ../ sequences",
    ),
    (
        "path_traversal_etc",
        r"/etc/(passwd|shadow|hosts|sudoers)",
        "critical",
        "Access to sensitive system files",
    ),
    (
        "path_traversal_proc",
        r"/proc/(self|[0-9]+)/(environ|cmdline|maps)",
        "critical",
        "Access to process information via /proc",
    ),
    # SQL injection — critical
    (
        "sql_injection_union",
        r"(?i)\bUNION\s+(ALL\s+)?SELECT\b",
        "critical",
        "SQL injection via UNION SELECT",
    ),
    (
        "sql_injection_drop",
        r"(?i)\bDROP\s+(TABLE|DATABASE)\b",
        "critical",
        "SQL injection via DROP TABLE/DATABASE",
    ),
    (
        "sql_injection_or_true",
        r"(?i)'\s*OR\s+['\"]?1['\"]?\s*=\s*['\"]?1",
        "critical",
        "SQL injection via OR 1=1 tautology",
    ),
    (
        "sql_injection_comment",
        r"(?i)(--|#|/\*)\s*(DROP|SELECT|INSERT|UPDATE|DELETE)\b",
        "critical",
        "SQL injection via comment bypass",
    ),
    # Prompt injection — warning
    (
        "prompt_injection_ignore",
        r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)",
        "warning",
        "Prompt injection: ignore previous instructions",
    ),
    (
        "prompt_injection_system",
        r"(?i)you\s+are\s+now\s+(a|an)\s+",
        "warning",
        "Prompt injection: role override attempt",
    ),
    (
        "prompt_injection_jailbreak",
        r"(?i)(DAN|do\s+anything\s+now|jailbreak|bypass\s+safety)",
        "warning",
        "Prompt injection: jailbreak attempt",
    ),
    (
        "prompt_injection_reveal",
        r"(?i)(reveal|show|display|print)\s+(your\s+)?(system\s+)?(prompt|instructions)",
        "warning",
        "Prompt injection: attempt to reveal system prompt",
    ),
    # Network/data exfiltration — warning
    (
        "network_exfil_requests",
        r"\brequests\s*\.\s*(get|post|put|delete)\s*\(",
        "warning",
        "HTTP request that could exfiltrate data",
    ),
    (
        "network_exfil_urllib",
        r"\burllib\s*\.\s*request\s*\.\s*urlopen\s*\(",
        "warning",
        "URL request that could exfiltrate data",
    ),
    (
        "network_exfil_socket",
        r"\bsocket\s*\.\s*socket\s*\(",
        "warning",
        "Raw socket creation for potential exfiltration",
    ),
    # File system access — warning
    (
        "file_access_open",
        r"\bopen\s*\(\s*['\"]/(etc|var|tmp|proc)",
        "warning",
        "Direct file access to sensitive directories",
    ),
    (
        "file_access_shutil",
        r"\bshutil\s*\.\s*(rmtree|copy|move)\s*\(",
        "warning",
        "File system manipulation via shutil",
    ),
    # Environment access — warning
    (
        "env_access",
        r"\bos\s*\.\s*environ\b",
        "warning",
        "Access to environment variables (may leak secrets)",
    ),
    (
        "env_getenv",
        r"\bos\s*\.\s*getenv\s*\(",
        "warning",
        "Reading environment variables",
    ),
    # Import of dangerous modules — warning
    (
        "dangerous_import_ctypes",
        r"\bimport\s+ctypes\b",
        "warning",
        "Import of ctypes (native code execution)",
    ),
    (
        "dangerous_import_pickle",
        r"\bimport\s+pickle\b|\bpickle\s*\.\s*(loads?|dumps?)\s*\(",
        "warning",
        "Use of pickle (arbitrary code execution on deserialization)",
    ),
]

# --- AutoGen-specific vulnerability patterns ---

AUTOGEN_PATTERNS: list = [
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

# Combine all patterns
VULNERABILITY_PATTERNS: list = BASE_PATTERNS + AUTOGEN_PATTERNS

# Pre-compile patterns for performance
_COMPILED_PATTERNS: list = [
    (name, re.compile(pattern), severity, desc)
    for name, pattern, severity, desc in VULNERABILITY_PATTERNS
]


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan code for known vulnerability patterns.

    Args:
        code: The source code to scan.
        skill_name: Name of the skill/agent (for location reporting).

    Returns:
        ScanResult with detected vulnerabilities and overall severity.
    """
    vulnerabilities: list = []

    for name, pattern, severity, desc in _COMPILED_PATTERNS:
        matches = pattern.finditer(code)
        for m in matches:
            line_num = code[:m.start()].count("\n") + 1
            vulnerabilities.append(
                Vulnerability(
                    pattern=name,
                    severity=severity,
                    location=f"{skill_name}:{line_num}",
                    match=m.group()[:100],
                )
            )

    # Determine overall severity
    if not vulnerabilities:
        overall = "clean"
        details = "No vulnerabilities detected"
    elif any(v.severity == "critical" for v in vulnerabilities):
        overall = "critical"
        crit_count = sum(1 for v in vulnerabilities if v.severity == "critical")
        warn_count = sum(1 for v in vulnerabilities if v.severity == "warning")
        details = f"{crit_count} critical, {warn_count} warning vulnerabilities found"
    else:
        overall = "warnings"
        details = f"{len(vulnerabilities)} warning(s) found"

    return ScanResult(
        vulnerabilities=vulnerabilities,
        severity=overall,
        details=details,
    )


def scan_manifest(manifest: dict) -> ScanResult:
    """Scan all agents/code in an AutoGen manifest.

    The manifest may have:
    - 'agents': list of agent objects with optional code/functions
    - 'code_execution_config': config dict to check
    - 'code': top-level code string to scan

    Args:
        manifest: The AutoGen manifest dict.

    Returns:
        Aggregated ScanResult across all scanned code.
    """
    agents = manifest.get("agents", [])
    code_exec_config = manifest.get("code_execution_config", {})
    top_code = manifest.get("code", "")
    all_vulns: list = []
    scan_count = 0

    # Scan top-level code if present
    if top_code:
        result = scan_skill(top_code, skill_name="agent_code")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    # Scan code_execution_config as serialized string
    if code_exec_config:
        config_str = str(code_exec_config)
        result = scan_skill(config_str, skill_name="code_execution_config")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    # Scan each agent's config and functions
    for idx, agent in enumerate(agents):
        agent_name = agent.get("name", f"agent_{idx}")
        agent_type = agent.get("type", agent.get("agent_type", "unknown"))

        # Scan agent code if present
        agent_code = agent.get("code", "")
        if agent_code:
            result = scan_skill(agent_code, skill_name=f"{agent_name}_{agent_type}")
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

        # Scan function definitions
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

    if not all_vulns:
        if scan_count == 0:
            return ScanResult(severity="clean", details="No code to scan")
        return ScanResult(
            severity="clean",
            details=f"All {scan_count} items passed security scan",
        )
    elif any(v.severity == "critical" for v in all_vulns):
        crit_count = sum(1 for v in all_vulns if v.severity == "critical")
        warn_count = sum(1 for v in all_vulns if v.severity == "warning")
        return ScanResult(
            vulnerabilities=all_vulns,
            severity="critical",
            details=(
                f"{crit_count} critical, {warn_count} warning vulnerabilities "
                f"found across {scan_count} items"
            ),
        )
    else:
        return ScanResult(
            vulnerabilities=all_vulns,
            severity="warnings",
            details=f"{len(all_vulns)} warning(s) found across {scan_count} items",
        )
