"""Semantic Kernel security scanner.

Scans Semantic Kernel agent code for known vulnerability patterns including
framework-specific risks (plugin injection, planner manipulation, unrestricted
native functions) plus all base patterns.
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

# --- Semantic Kernel-specific vulnerability patterns ---

SK_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        "native_function_exec",
        r"\bNativeFunctions?\b.*\bexec\b",
        "critical",
        "SK NativeFunction with exec — native code execution risk",
    ),
    (
        "native_function_unrestricted",
        r"@(kernel_function|sk_function)\s*\n.*def\s+\w+.*\bos\b",
        "critical",
        "SK kernel_function with OS access — unrestricted native function",
    ),
    (
        "kernel_manipulation",
        r"\bkernel\s*\.\s*import_native_skill_from_directory\s*\(",
        "critical",
        "SK import_native_skill_from_directory — arbitrary code loading",
    ),
    (
        "planner_manipulation",
        r"\b(SequentialPlanner|ActionPlanner|StepwisePlanner)\s*\(.*\ballow_missing\b",
        "critical",
        "SK planner with allow_missing — planner manipulation risk",
    ),
    (
        "plugin_injection",
        r"\bkernel\s*\.\s*add_plugin\s*\(.*\bfrom_directory\b",
        "warning",
        "SK add_plugin from directory — potential plugin injection",
    ),
    (
        "prompt_template_injection",
        r"\bPromptTemplateConfig\s*\(.*\{\{.*\$.*\}\}",
        "warning",
        "SK PromptTemplateConfig with template variables — injection risk",
    ),
    (
        "memory_manipulation",
        r"\bSemanticTextMemory|VolatileMemoryStore",
        "warning",
        "SK memory component — potential memory poisoning",
    ),
    (
        "unfiltered_native_function",
        r"@kernel_function\b",
        "warning",
        "SK kernel_function decorator — unverified native function",
    ),
]

VULNERABILITY_PATTERNS = BASE_PATTERNS + SK_PATTERNS
_COMPILED_PATTERNS = compile_patterns(VULNERABILITY_PATTERNS)


def scan_skill(code: str, skill_name: str = "unknown") -> ScanResult:
    """Scan code for known vulnerability patterns."""
    return _base_scan_skill(
        code, skill_name=skill_name, compiled_patterns=_COMPILED_PATTERNS,
    )


def scan_manifest(manifest: dict) -> ScanResult:
    """Scan all plugins/code in a Semantic Kernel manifest.

    The manifest may have:
    - 'plugins': list of plugin objects with functions containing code
    - 'planner_config': planner configuration to check
    - 'code': top-level code string to scan
    """
    plugins = manifest.get("plugins", [])
    planner_config = manifest.get("planner_config", {})
    top_code = manifest.get("code", "")
    all_vulns: list[Vulnerability] = []
    scan_count = 0

    if top_code:
        result = scan_skill(top_code, skill_name="agent_code")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    if planner_config:
        config_str = str(planner_config)
        result = scan_skill(config_str, skill_name="planner_config")
        all_vulns.extend(result.vulnerabilities)
        scan_count += 1

    for idx, plugin in enumerate(plugins):
        plugin_name = plugin.get("name", f"plugin_{idx}")

        plugin_code = plugin.get("code", "")
        if plugin_code:
            result = scan_skill(plugin_code, skill_name=plugin_name)
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

        for fidx, func in enumerate(plugin.get("functions", [])):
            if isinstance(func, dict):
                func_code = func.get("code", "")
                func_name = func.get("name", f"{plugin_name}_func_{fidx}")
            else:
                continue
            if not func_code:
                continue
            result = scan_skill(func_code, skill_name=func_name)
            all_vulns.extend(result.vulnerabilities)
            scan_count += 1

    return aggregate_results(all_vulns, scan_count)
