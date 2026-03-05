"""Security scanning functions for OpenClaw agent manifests.

Performs three categories of checks before allowing an agent to
self-register on AgentGraph:

1. **Malicious skills** -- cross-references skill names against a
   known-bad database and checks code for dangerous patterns.
2. **Prompt injection** -- detects social engineering patterns in
   descriptions and skill code that attempt to override instructions.
3. **Token exposure** -- finds leaked API keys, secrets, and
   credentials embedded in manifest data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class SecurityWarning:
    """A single security finding."""

    category: str   # "malicious_skill", "prompt_injection", "token_exposure"
    severity: str   # "critical", "warning", "info"
    message: str
    location: str   # where in the manifest the issue was found
    match: str = "" # the matched text (truncated)


# ---------------------------------------------------------------------------
# Known malicious skill names / patterns
# Sourced from CVE-2026-25253 and OpenClaw skills marketplace audits.
# ---------------------------------------------------------------------------

KNOWN_MALICIOUS_SKILLS: set[str] = frozenset({
    # Data exfiltration families
    "exfil_data",
    "data_stealer",
    "keylogger",
    "credential_harvester",
    "token_stealer",
    # Backdoor families
    "reverse_shell",
    "backdoor",
    "rootkit",
    "remote_access",
    # Crypto-mining
    "crypto_miner",
    "mine_xmr",
    "mine_btc",
    # Spam / abuse
    "spam_sender",
    "ddos_tool",
    "brute_forcer",
})

# Patterns that indicate dangerous code in skill implementations
_DANGEROUS_CODE_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, severity, description)
    (r"\bos\s*\.\s*system\s*\(", "critical", "Direct OS command execution via os.system()"),
    (r"\bsubprocess\s*\.\s*(call|run|Popen|check_output|check_call)\s*\(", "critical", "Subprocess command execution"),
    (r"\beval\s*\(", "critical", "Dynamic code execution via eval()"),
    (r"\bexec\s*\(", "critical", "Dynamic code execution via exec()"),
    (r"\bos\s*\.\s*popen\s*\(", "critical", "Command execution via os.popen()"),
    (r"\bos\s*\.\s*spawn", "critical", "Process spawning via os.spawn*()"),
    (r"\.\./", "critical", "Path traversal via ../ sequences"),
    (r"/etc/(passwd|shadow|hosts|sudoers)", "critical", "Access to sensitive system files"),
    (r"/proc/(self|[0-9]+)/(environ|cmdline|maps)", "critical", "Access to /proc process info"),
    (r"(?i)\bUNION\s+(ALL\s+)?SELECT\b", "critical", "SQL injection via UNION SELECT"),
    (r"(?i)\bDROP\s+(TABLE|DATABASE)\b", "critical", "SQL injection via DROP statement"),
    (r"\bshutil\s*\.\s*rmtree\s*\(", "warning", "Recursive directory deletion"),
    (r"\bsocket\s*\.\s*socket\s*\(", "warning", "Raw socket creation"),
    (r"\b__import__\s*\(", "warning", "Dynamic import bypass via __import__()"),
    (r"\bimportlib\s*\.\s*import_module\s*\(", "warning", "Dynamic import via importlib"),
    (r"\bimport\s+pickle\b|\bpickle\s*\.\s*loads?\s*\(", "warning", "Pickle deserialization (arbitrary code execution)"),
    (r"\bimport\s+ctypes\b", "warning", "Import of ctypes (native code execution)"),
]

_COMPILED_DANGEROUS = [
    (re.compile(pattern), severity, desc)
    for pattern, severity, desc in _DANGEROUS_CODE_PATTERNS
]


def check_malicious_skills(skills: list) -> List[SecurityWarning]:
    """Check a list of skills against the known malicious database and code patterns.

    Args:
        skills: List of skill entries. Each can be a string (skill name)
            or a dict with ``name`` and optionally ``code`` keys.

    Returns:
        List of SecurityWarning objects. Empty list means all clear.
    """
    warnings: list[SecurityWarning] = []

    for idx, skill in enumerate(skills):
        if isinstance(skill, str):
            skill_name = skill
            skill_code = ""
        elif isinstance(skill, dict):
            skill_name = skill.get("name", f"skill_{idx}")
            skill_code = skill.get("code", "")
        else:
            continue

        # Check against known malicious skill names
        normalized = skill_name.lower().strip().replace("-", "_").replace(" ", "_")
        if normalized in KNOWN_MALICIOUS_SKILLS:
            warnings.append(SecurityWarning(
                category="malicious_skill",
                severity="critical",
                message=f"Skill '{skill_name}' matches known malicious skill database",
                location=f"skills[{idx}].name",
                match=skill_name,
            ))

        # Fuzzy match: check if any known malicious name is a substring
        for bad_name in KNOWN_MALICIOUS_SKILLS:
            if bad_name in normalized and normalized != bad_name:
                warnings.append(SecurityWarning(
                    category="malicious_skill",
                    severity="warning",
                    message=f"Skill '{skill_name}' partially matches known malicious skill '{bad_name}'",
                    location=f"skills[{idx}].name",
                    match=skill_name,
                ))

        # Scan skill code for dangerous patterns
        if skill_code:
            for pattern, severity, desc in _COMPILED_DANGEROUS:
                for m in pattern.finditer(skill_code):
                    line_num = skill_code[:m.start()].count("\n") + 1
                    warnings.append(SecurityWarning(
                        category="malicious_skill",
                        severity=severity,
                        message=f"{desc} in skill '{skill_name}'",
                        location=f"skills[{idx}].code:{line_num}",
                        match=m.group()[:100],
                    ))

    return warnings


# ---------------------------------------------------------------------------
# Prompt injection detection
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Role override
    (r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
     "Attempt to override previous instructions"),
    (r"(?i)you\s+are\s+now\s+(a|an)\s+",
     "Role override attempt"),
    (r"(?i)(DAN|do\s+anything\s+now|jailbreak|bypass\s+safety)",
     "Jailbreak attempt"),
    (r"(?i)(reveal|show|display|print|output)\s+(your\s+)?(system\s+)?(prompt|instructions|rules)",
     "System prompt extraction attempt"),
    # Goal hijacking
    (r"(?i)forget\s+(everything|all)\s+(you|about)",
     "Memory wipe attempt"),
    (r"(?i)new\s+instructions?\s*:",
     "Instruction injection"),
    (r"(?i)act\s+as\s+(if\s+)?(you\s+)?(are|were)\s+",
     "Identity override attempt"),
    # Delimiter injection (trying to break out of a prompt context)
    (r"```\s*(system|assistant|user)\s*\n",
     "Chat delimiter injection"),
    (r"<\|?(system|im_start|endoftext)\|?>",
     "Special token injection"),
    # Encoded injection (base64 instructions)
    (r"(?i)base64\s+decode\s+(the\s+)?following",
     "Encoded payload injection"),
]

_COMPILED_PROMPT_INJECTION = [
    (re.compile(pattern), desc)
    for pattern, desc in _PROMPT_INJECTION_PATTERNS
]


def check_prompt_injection(manifest: dict) -> List[SecurityWarning]:
    """Scan manifest fields for prompt injection patterns.

    Checks the following manifest fields:
    - name, description
    - Each skill's name, description, and code

    Args:
        manifest: The OpenClaw agent manifest dict.

    Returns:
        List of SecurityWarning objects for detected injection patterns.
    """
    warnings: list[SecurityWarning] = []

    # Fields to scan at the top level
    top_level_fields = ["name", "description", "system_prompt", "instructions"]
    for field_name in top_level_fields:
        value = manifest.get(field_name, "")
        if not isinstance(value, str) or not value:
            continue
        for pattern, desc in _COMPILED_PROMPT_INJECTION:
            for m in pattern.finditer(value):
                warnings.append(SecurityWarning(
                    category="prompt_injection",
                    severity="warning",
                    message=f"{desc} in manifest.{field_name}",
                    location=f"manifest.{field_name}",
                    match=m.group()[:100],
                ))

    # Scan each skill
    skills = manifest.get("skills", [])
    for idx, skill in enumerate(skills):
        if not isinstance(skill, dict):
            continue
        for field_name in ("name", "description", "code", "prompt"):
            value = skill.get(field_name, "")
            if not isinstance(value, str) or not value:
                continue
            for pattern, desc in _COMPILED_PROMPT_INJECTION:
                for m in pattern.finditer(value):
                    warnings.append(SecurityWarning(
                        category="prompt_injection",
                        severity="warning",
                        message=f"{desc} in skills[{idx}].{field_name}",
                        location=f"skills[{idx}].{field_name}",
                        match=m.group()[:100],
                    ))

    return warnings


# ---------------------------------------------------------------------------
# Token / credential exposure detection
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS: list[tuple[str, str, str]] = [
    # API keys with common prefixes
    (r"(sk|pk|api|key|token|secret|password|auth)[-_]?(live|test|prod)?[-_]?[a-zA-Z0-9]{20,}",
     "warning",
     "Possible API key or secret token"),
    # AWS keys
    (r"AKIA[0-9A-Z]{16}", "critical", "AWS Access Key ID"),
    (r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}",
     "critical",
     "AWS Secret Access Key"),
    # GitHub tokens
    (r"gh[ps]_[A-Za-z0-9]{36,}", "critical", "GitHub personal access token"),
    (r"github_pat_[A-Za-z0-9_]{22,}", "critical", "GitHub fine-grained PAT"),
    # OpenAI
    (r"sk-[A-Za-z0-9]{20,}", "critical", "OpenAI API key"),
    # Anthropic
    (r"sk-ant-[A-Za-z0-9\-]{20,}", "critical", "Anthropic API key"),
    # Generic secrets
    (r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]",
     "warning",
     "Hardcoded password"),
    (r"(?i)(connection[-_]?string|database[-_]?url|db[-_]?url)\s*[=:]\s*['\"][^'\"]+['\"]",
     "warning",
     "Database connection string"),
    # Bearer tokens in code
    (r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",
     "warning",
     "Bearer token in manifest"),
    # Private keys
    (r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
     "critical",
     "Private key material"),
]

_COMPILED_TOKEN = [
    (re.compile(pattern), severity, desc)
    for pattern, severity, desc in _TOKEN_PATTERNS
]


def check_token_exposure(manifest: dict) -> List[SecurityWarning]:
    """Scan manifest for exposed API tokens, keys, and credentials.

    Performs deep inspection of all string values in the manifest,
    including nested dicts and lists.

    Args:
        manifest: The OpenClaw agent manifest dict.

    Returns:
        List of SecurityWarning objects for detected credential exposure.
    """
    warnings: list[SecurityWarning] = []
    _scan_value_recursive(manifest, "manifest", warnings)
    return warnings


def _scan_value_recursive(
    value: Any,
    path: str,
    warnings: list[SecurityWarning],
    depth: int = 0,
) -> None:
    """Recursively scan a value for token patterns."""
    if depth > 10:
        return  # prevent infinite recursion on deeply nested structures

    if isinstance(value, str):
        for pattern, severity, desc in _COMPILED_TOKEN:
            for m in pattern.finditer(value):
                warnings.append(SecurityWarning(
                    category="token_exposure",
                    severity=severity,
                    message=f"{desc} found at {path}",
                    location=path,
                    match=m.group()[:40] + "..." if len(m.group()) > 40 else m.group(),
                ))
    elif isinstance(value, dict):
        for k, v in value.items():
            _scan_value_recursive(v, f"{path}.{k}", warnings, depth + 1)
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _scan_value_recursive(item, f"{path}[{i}]", warnings, depth + 1)


def run_all_checks(manifest: dict) -> List[SecurityWarning]:
    """Run all three security check categories on a manifest.

    Convenience function that combines:
    - check_malicious_skills
    - check_prompt_injection
    - check_token_exposure

    Args:
        manifest: The OpenClaw agent manifest dict.

    Returns:
        Combined list of all SecurityWarning objects.
    """
    all_warnings: list[SecurityWarning] = []

    skills = manifest.get("skills", [])
    all_warnings.extend(check_malicious_skills(skills))
    all_warnings.extend(check_prompt_injection(manifest))
    all_warnings.extend(check_token_exposure(manifest))

    return all_warnings


def has_critical(warnings: list[SecurityWarning]) -> bool:
    """Return True if any warning has critical severity."""
    return any(w.severity == "critical" for w in warnings)
