"""Shared security scanner base for all bridge framework adapters.

Contains base vulnerability patterns, data classes, and the core
scan_skill() function used by all framework-specific scanners.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Vulnerability:
    """A single detected vulnerability."""

    pattern: str
    severity: str  # "warning" or "critical"
    location: str  # description of where found
    match: str  # the matched text


@dataclass
class ScanResult:
    """Result of scanning skill code or a manifest."""

    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    severity: str = "clean"  # "clean", "warnings", "critical"
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
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


# --- Base vulnerability pattern definitions ---
# Each pattern: (name, regex, severity, description)

BASE_PATTERNS: list[tuple[str, str, str, str]] = [
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
        r"(?i)(--|#|/\\*)\s*(DROP|SELECT|INSERT|UPDATE|DELETE)\b",
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


def compile_patterns(
    patterns: list[tuple[str, str, str, str]],
) -> list[tuple[str, re.Pattern[str], str, str]]:
    """Compile a list of (name, regex, severity, desc) tuples."""
    return [
        (name, re.compile(regex), severity, desc)
        for name, regex, severity, desc in patterns
    ]


def scan_skill(
    code: str,
    skill_name: str = "unknown",
    compiled_patterns: list[tuple[str, re.Pattern[str], str, str]] | None = None,
) -> ScanResult:
    """Scan code for known vulnerability patterns.

    Args:
        code: The source code to scan.
        skill_name: Name of the skill/tool (for location reporting).
        compiled_patterns: Pre-compiled patterns to use. If None, uses
            only the base patterns.

    Returns:
        ScanResult with detected vulnerabilities and overall severity.
    """
    if compiled_patterns is None:
        compiled_patterns = _BASE_COMPILED

    vulnerabilities: list[Vulnerability] = []

    for name, pattern, severity, desc in compiled_patterns:
        for m in pattern.finditer(code):
            line_num = code[: m.start()].count("\n") + 1
            vulnerabilities.append(
                Vulnerability(
                    pattern=name,
                    severity=severity,
                    location=f"{skill_name}:{line_num}",
                    match=m.group()[:100],
                )
            )

    if not vulnerabilities:
        return ScanResult(
            severity="clean", details="No vulnerabilities detected"
        )
    elif any(v.severity == "critical" for v in vulnerabilities):
        crit = sum(1 for v in vulnerabilities if v.severity == "critical")
        warn = sum(1 for v in vulnerabilities if v.severity == "warning")
        return ScanResult(
            vulnerabilities=vulnerabilities,
            severity="critical",
            details=f"{crit} critical, {warn} warning vulnerabilities found",
        )
    else:
        return ScanResult(
            vulnerabilities=vulnerabilities,
            severity="warnings",
            details=f"{len(vulnerabilities)} warning(s) found",
        )


def aggregate_results(
    all_vulns: list[Vulnerability],
    scan_count: int,
) -> ScanResult:
    """Build a ScanResult from aggregated vulnerabilities.

    Args:
        all_vulns: Combined vulnerability list from multiple scans.
        scan_count: Number of items that were scanned.

    Returns:
        Aggregated ScanResult.
    """
    if not all_vulns:
        if scan_count == 0:
            return ScanResult(severity="clean", details="No code to scan")
        return ScanResult(
            severity="clean",
            details=f"All {scan_count} items passed security scan",
        )
    elif any(v.severity == "critical" for v in all_vulns):
        crit = sum(1 for v in all_vulns if v.severity == "critical")
        warn = sum(1 for v in all_vulns if v.severity == "warning")
        return ScanResult(
            vulnerabilities=all_vulns,
            severity="critical",
            details=(
                f"{crit} critical, {warn} warning vulnerabilities "
                f"found across {scan_count} items"
            ),
        )
    else:
        return ScanResult(
            vulnerabilities=all_vulns,
            severity="warnings",
            details=(
                f"{len(all_vulns)} warning(s) found across "
                f"{scan_count} items"
            ),
        )


# Pre-compile base patterns at module load
_BASE_COMPILED = compile_patterns(BASE_PATTERNS)
