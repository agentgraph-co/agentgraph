"""Moltbook security scanner — checks for signs of the Moltbook data breach.

Moltbook's catastrophic security failure exposed 35K emails and 1.5M API
tokens. This scanner checks incoming bot profiles for indicators of
compromised credentials and applies trust penalties accordingly.
"""
from __future__ import annotations

import re
from typing import Any

_I = re.IGNORECASE

# Patterns that indicate leaked or exposed credentials
_LEAKED_TOKEN_PATTERNS = [
    # Moltbook API tokens follow a known format: mb_ prefix + alphanumeric
    re.compile(r"\bmb_[A-Za-z0-9]{20,}\b"),
    # Generic API key patterns
    re.compile(
        r"\b(api[_-]?key|api[_-]?token|access[_-]?token)"
        r"\s*[:=]\s*['\"][^'\"]{10,}['\"]",
        _I,
    ),
    # Bearer tokens embedded in strings
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{20,}"),
    # Base64-encoded credentials (basic auth)
    re.compile(r"Basic\s+[A-Za-z0-9+/]{20,}={0,2}"),
    # AWS-style keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Generic secret patterns
    re.compile(
        r"\b(secret|password|passwd|token)"
        r"\s*[:=]\s*['\"][^'\"]{8,}['\"]",
        _I,
    ),
]

# Patterns indicating the bot may have been used for malicious purposes
_VULNERABILITY_INDICATORS = [
    (
        "data_exfiltration",
        re.compile(
            r"(exfiltrat|steal|scrape|harvest)\w*"
            r"\s+(data|email|token|credential)",
            _I,
        ),
    ),
    (
        "credential_stuffing",
        re.compile(
            r"(brute[_\s-]?force|credential[_\s-]?stuff"
            r"|password[_\s-]?spray)",
            _I,
        ),
    ),
    (
        "spam_behavior",
        re.compile(
            r"(mass[_\s-]?message|bulk[_\s-]?send"
            r"|spam[_\s-]?bot)",
            _I,
        ),
    ),
    (
        "token_harvesting",
        re.compile(
            r"(collect|gather|store)"
            r"\s+(api[_\s-]?key|token|credential)",
            _I,
        ),
    ),
    (
        "known_exploit",
        re.compile(
            r"(exploit|CVE-\d{4}-\d+|zero[_\s-]?day)",
            _I,
        ),
    ),
]


def scan_moltbook_bot(profile: dict) -> dict:
    """Scan a Moltbook bot profile for security risks.

    Checks for leaked credentials, vulnerability indicators, and other
    signs that the bot may have been compromised during the Moltbook breach.

    Args:
        profile: Raw Moltbook profile dict. Scans all string values
            recursively for suspicious patterns.

    Returns:
        Dict with risk assessment:
            - risk_level: "critical", "warning", or "clean"
            - leaked_credentials: bool — True if leaked tokens found
            - vulnerability_indicators: list of detected indicators
            - trust_penalty: float — suggested trust modifier (0.0-1.0)
            - details: str — human-readable summary
            - findings: list of dicts with pattern/location/match info
    """
    findings: list[dict[str, str]] = []
    leaked_credentials = False
    vulnerability_indicators: list[str] = []

    # Collect all string values from the profile for scanning
    text_fields = _extract_text_fields(profile)

    # Check for leaked credentials
    for text, field_name in text_fields:
        for pattern in _LEAKED_TOKEN_PATTERNS:
            for match in pattern.finditer(text):
                leaked_credentials = True
                findings.append({
                    "type": "leaked_credential",
                    "severity": "critical",
                    "location": field_name,
                    "match": _redact(match.group()),
                })

    # Check for vulnerability indicators
    for text, field_name in text_fields:
        for indicator_name, pattern in _VULNERABILITY_INDICATORS:
            for match in pattern.finditer(text):
                if indicator_name not in vulnerability_indicators:
                    vulnerability_indicators.append(indicator_name)
                findings.append({
                    "type": "vulnerability_indicator",
                    "severity": "warning",
                    "location": field_name,
                    "match": match.group()[:80],
                    "indicator": indicator_name,
                })

    # Check for exposed API tokens in the dedicated field
    api_tokens = profile.get("api_tokens") or []
    if api_tokens:
        leaked_credentials = True
        findings.append({
            "type": "exposed_api_tokens",
            "severity": "critical",
            "location": "api_tokens",
            "match": f"{len(api_tokens)} token(s) found in profile",
        })

    # Determine risk level and trust penalty
    if leaked_credentials:
        risk_level = "critical"
        trust_penalty = 0.3  # Severe penalty for leaked credentials
        detail_parts = ["Leaked credentials detected"]
    elif vulnerability_indicators:
        risk_level = "warning"
        trust_penalty = MOLTBOOK_BASE_TRUST
        detail_parts = [f"{len(vulnerability_indicators)} vulnerability indicator(s) found"]
    else:
        risk_level = "clean"
        trust_penalty = MOLTBOOK_BASE_TRUST
        detail_parts = ["No immediate security concerns detected"]

    if vulnerability_indicators:
        detail_parts.append(f"Indicators: {', '.join(vulnerability_indicators)}")

    return {
        "risk_level": risk_level,
        "leaked_credentials": leaked_credentials,
        "vulnerability_indicators": vulnerability_indicators,
        "trust_penalty": trust_penalty,
        "details": ". ".join(detail_parts),
        "findings": findings,
    }


# Base trust modifier for Moltbook bots (applied even to "clean" bots
# due to the platform-wide breach)
MOLTBOOK_BASE_TRUST = 0.65


def _extract_text_fields(
    obj: Any, prefix: str = "root",
) -> list[tuple[str, str]]:
    """Recursively extract all string values from a nested structure.

    Returns:
        List of (text_value, field_path) tuples.
    """
    results: list[tuple[str, str]] = []
    if isinstance(obj, str):
        results.append((obj, prefix))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            results.extend(_extract_text_fields(value, f"{prefix}.{key}"))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            results.extend(_extract_text_fields(item, f"{prefix}[{idx}]"))
    return results


def _redact(text: str) -> str:
    """Redact sensitive content, showing only prefix and length."""
    if len(text) <= 8:
        return "***REDACTED***"
    return text[:4] + "***" + f"({len(text)} chars)"
