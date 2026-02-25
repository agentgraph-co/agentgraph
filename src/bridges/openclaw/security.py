"""OpenClaw skill security scanner.

Scans skill code for known malicious patterns including:
- Prompt injection
- Command injection (os.system, subprocess, eval, exec)
- Path traversal (../, /etc/)
- SQL injection patterns
"""
from __future__ import annotations

from typing import Any

from src.bridges.scanner_base import (
    BASE_PATTERNS,
    ScanResult,
    Vulnerability,
    compile_patterns,
)
from src.bridges.scanner_base import (
    scan_skill as _base_scan_skill,
)

# OpenClaw uses only the base patterns (no framework-specific additions)
VULNERABILITY_PATTERNS = BASE_PATTERNS
_COMPILED_PATTERNS = compile_patterns(VULNERABILITY_PATTERNS)


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan a skill's code for known vulnerability patterns."""
    return _base_scan_skill(
        code, skill_name=skill_name, compiled_patterns=_COMPILED_PATTERNS,
    )


def scan_manifest(manifest: dict[str, Any]) -> ScanResult:
    """Scan all skills in an OpenClaw agent manifest.

    The manifest is expected to have a 'skills' key containing a list
    of skill objects, each with a 'code' field and optionally a 'name' field.
    """
    skills = manifest.get("skills", [])
    if not skills:
        return ScanResult(severity="clean", details="No skills to scan")

    all_vulns: list[Vulnerability] = []

    for idx, skill in enumerate(skills):
        skill_name = skill.get("name", f"skill_{idx}")
        code = skill.get("code", "")
        if not code:
            continue
        result = scan_skill(code, skill_name=skill_name)
        all_vulns.extend(result.vulnerabilities)

    if not all_vulns:
        return ScanResult(
            severity="clean",
            details=f"All {len(skills)} skills passed security scan",
        )

    # Use inline aggregation to preserve original "across N skills" wording
    if any(v.severity == "critical" for v in all_vulns):
        crit = sum(1 for v in all_vulns if v.severity == "critical")
        warn = sum(1 for v in all_vulns if v.severity == "warning")
        return ScanResult(
            vulnerabilities=all_vulns,
            severity="critical",
            details=(
                f"{crit} critical, {warn} warning vulnerabilities "
                f"found across {len(skills)} skills"
            ),
        )
    return ScanResult(
        vulnerabilities=all_vulns,
        severity="warnings",
        details=(
            f"{len(all_vulns)} warning(s) found across "
            f"{len(skills)} skills"
        ),
    )
