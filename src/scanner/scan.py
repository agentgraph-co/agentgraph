"""Core MCP server security scanner.

Fetches source files from GitHub repos and scans for security issues.
Designed to run against the recruitment_prospects table of discovered repos.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from src.scanner.patterns import (
    AUTH_POSITIVE_PATTERNS,
    EXFILTRATION_PATTERNS,
    FS_ACCESS_PATTERNS,
    OBFUSCATION_PATTERNS,
    SECRET_PATTERNS,
    SKIP_DIRS,
    SKIP_EXTENSIONS,
    SOURCE_EXTENSIONS,
    UNSAFE_EXEC_PATTERNS,
)

# Inline suppression marker — append to any line to skip scanning it
_SUPPRESSION_COMMENT = "ag-scan:ignore"

# Allowlist file path (JSON array of {file_path, name} objects to skip)
_ALLOWLIST_PATH = Path(__file__).parent / "allowlist.json"

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_MAX_FILE_SIZE = 500_000  # 500KB — skip huge files
_MAX_FILES_PER_REPO = 200  # don't scan massive monorepos


@dataclass
class Finding:
    """A single security finding."""

    category: str  # "secret", "unsafe_exec", "fs_access"
    name: str
    severity: str  # "critical", "high", "medium", "low", "info"
    file_path: str
    line_number: int
    snippet: str  # surrounding context (redacted for secrets)


@dataclass
class ScanResult:
    """Result of scanning one repository."""

    repo: str
    stars: int
    description: str
    framework: str
    findings: list[Finding] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)
    files_scanned: int = 0
    has_readme: bool = False
    has_license: bool = False
    has_tests: bool = False
    primary_language: str = ""
    trust_score: int = 0  # 0-100, computed after scan
    error: str | None = None

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "medium")


def _should_skip_path(path: str) -> bool:
    """Check if a file path should be skipped."""
    parts = Path(path).parts
    for part in parts:
        if part in SKIP_DIRS:
            return True
    ext = Path(path).suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return True
    # Also skip if it looks like a minified file
    name = Path(path).name.lower()
    if ".min." in name:
        return True
    return False


def _is_source_file(path: str) -> bool:
    """Check if a file should be scanned for source patterns."""
    ext = Path(path).suffix.lower()
    return ext in SOURCE_EXTENSIONS


def _redact_secret(line: str, match: re.Match) -> str:  # type: ignore[type-arg]
    """Redact the actual secret value from the snippet."""
    start, end = match.span()
    # Show first 4 and last 4 chars of match, redact middle
    matched = match.group()
    if len(matched) > 12:
        redacted = matched[:4] + "..." + matched[-4:]
    else:
        redacted = matched[:2] + "***"
    return line[:start] + redacted + line[end:]


def _detect_language(files: list[dict]) -> str:
    """Detect primary language from file extensions."""
    ext_counts: dict[str, int] = {}
    for f in files:
        ext = Path(f.get("path", "")).suffix.lower()
        if ext in SOURCE_EXTENSIONS:
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    lang_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
        ".java": "Java", ".kt": "Kotlin", ".cs": "C#",
    }
    if not ext_counts:
        return "unknown"
    top_ext = max(ext_counts, key=ext_counts.get)  # type: ignore[arg-type]
    return lang_map.get(top_ext, top_ext)


async def _fetch_repo_tree(
    owner: str, repo: str, token: str | None = None,
) -> list[dict]:
    """Fetch the file tree of a repo via GitHub API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Get default branch
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
        )
        if resp.status_code != 200:
            logger.warning(
                "GitHub repo API returned %d for %s/%s (rate_remaining=%s, auth=%s)",
                resp.status_code, owner, repo,
                resp.headers.get("x-ratelimit-remaining", "?"),
                "yes" if token else "no",
            )
            return []
        default_branch = resp.json().get("default_branch", "main")

        # Get tree (recursive)
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}",
            headers=headers,
            params={"recursive": "1"},
        )
        if resp.status_code != 200:
            logger.warning(
                "GitHub tree API returned %d for %s/%s (rate_remaining=%s)",
                resp.status_code, owner, repo,
                resp.headers.get("x-ratelimit-remaining", "?"),
            )
            return []

        tree = resp.json().get("tree", [])
        # Filter to blobs (files) only
        return [
            item for item in tree
            if item.get("type") == "blob"
            and item.get("size", 0) <= _MAX_FILE_SIZE
        ]


async def _fetch_file_content(
    owner: str, repo: str, path: str, token: str | None = None,
) -> str | None:
    """Fetch raw file content from GitHub."""
    headers = {"Accept": "application/vnd.github.raw+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
        )
        if resp.status_code == 200:
            return resp.text
    return None


def _load_allowlist() -> set[tuple[str, str]]:
    """Load the false-positive allowlist from disk.

    Returns a set of (file_path_glob, finding_name) tuples.
    Each entry suppresses the named finding for matching file paths.
    """
    if not _ALLOWLIST_PATH.exists():
        return set()
    try:
        data = json.loads(_ALLOWLIST_PATH.read_text())
        return {(e["file_path"], e["name"]) for e in data if "file_path" in e and "name" in e}
    except Exception:
        logger.warning("Failed to load scanner allowlist from %s", _ALLOWLIST_PATH)
        return set()


def _is_allowlisted(
    file_path: str, finding_name: str, allowlist: set[tuple[str, str]],
) -> bool:
    """Check if a finding is allowlisted.

    Supports exact match and simple glob patterns (* at end).
    """
    for pattern, name in allowlist:
        if name != finding_name:
            continue
        if pattern == file_path:
            return True
        # Simple glob: "src/utils/*" matches "src/utils/helpers.py"
        if pattern.endswith("*") and file_path.startswith(pattern[:-1]):
            return True
    return False


# ---------------------------------------------------------------------------
# Context-aware checks — reduce false positives for safe usage patterns
# ---------------------------------------------------------------------------

# Regex: subprocess.run/call/etc with a hardcoded string list as first arg
# e.g. subprocess.run(["git", "status"]) or subprocess.run("ls -la", ...)
_SAFE_SUBPROCESS_RE = re.compile(
    r"""subprocess\.(?:run|call|check_output|Popen)\s*\(\s*\[?\s*['"]""",
)

# Regex: open() on a known safe path / with Path objects / read-only config
_SAFE_OPEN_PATTERNS = [
    # Path(...).open() or Path(...).read_text() / write_text()
    re.compile(r"Path\s*\(.*\)\s*\.(?:open|read_text|write_text|read_bytes|write_bytes)\s*\("),
    # open() with a hardcoded string path (no variable interpolation)
    re.compile(r"""open\s*\(\s*['"][^'"{}$]+['"]\s*[,)]"""),
    # with open(...) as f — context manager pattern (safe resource handling)
    re.compile(r"""with\s+open\s*\("""),
]

# Regex: safe exec/eval — e.g. ast.literal_eval, json.loads with exec in name
_SAFE_EVAL_RE = re.compile(
    r"""(?:ast\.literal_eval|json\.loads?|yaml\.safe_load)\s*\(""",
)


def _is_safe_exec_context(line: str, finding_name: str) -> bool:
    """Check if an unsafe_exec match is actually a safe usage pattern."""
    stripped = line.strip()

    # subprocess with hardcoded args → safe
    if "subprocess" in finding_name.lower():
        if _SAFE_SUBPROCESS_RE.search(stripped):
            return True
        # Also safe: subprocess with shell=False (explicit)
        if "shell=False" in stripped or "shell = False" in stripped:
            return True

    # eval/exec — skip if it's ast.literal_eval or similar safe wrappers
    if "eval" in finding_name.lower() or "exec" in finding_name.lower():
        if _SAFE_EVAL_RE.search(stripped):
            return True

    return False


def _is_safe_fs_context(line: str, _finding_name: str) -> bool:
    """Check if a file system access match is actually a safe usage pattern."""
    stripped = line.strip()

    for safe_pat in _SAFE_OPEN_PATTERNS:
        if safe_pat.search(stripped):
            return True

    # Path.write_text / read_text (already method-chained on Path object)
    if re.search(r"\.(?:read_text|write_text|read_bytes|write_bytes)\s*\(", stripped):
        return True

    return False


def _scan_content(
    content: str, file_path: str,
    allowlist: set[tuple[str, str]] | None = None,
) -> tuple[list[Finding], list[str]]:
    """Scan file content for security issues and positive signals."""
    findings: list[Finding] = []
    positives: list[str] = []
    if allowlist is None:
        allowlist = set()

    lines = content.split("\n")

    for line_num, line in enumerate(lines, 1):
        # Skip comments (basic heuristic)
        stripped = line.strip()
        if stripped.startswith(("#", "//", "*", "/*")):
            continue
        # Skip lines that look like examples/docs
        if "example" in stripped.lower() or "placeholder" in stripped.lower():
            continue

        # --- Option 1: Inline suppression ---
        # If the line contains "ag-scan:ignore", skip all pattern checks
        if _SUPPRESSION_COMMENT in line:
            continue

        # Check secrets
        for name, pattern, severity in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                # Extra filter: skip if it's in a .env.example or test file
                if ".example" in file_path or "test" in file_path.lower():
                    continue
                # Skip if value is clearly a placeholder
                val = match.group()
                if val in ("YOUR_API_KEY", "your_api_key", "xxx", "changeme"):
                    continue
                # --- Option 2: Allowlist check ---
                if _is_allowlisted(file_path, name, allowlist):
                    continue
                findings.append(Finding(
                    category="secret",
                    name=name,
                    severity=severity,
                    file_path=file_path,
                    line_number=line_num,
                    snippet=_redact_secret(stripped[:120], match),
                ))
                break  # one finding per line for secrets

        # Check unsafe exec
        for name, pattern, severity in UNSAFE_EXEC_PATTERNS:
            if pattern.search(line):
                # --- Option 2: Allowlist check ---
                if _is_allowlisted(file_path, name, allowlist):
                    continue
                # --- Option 3: Context-aware check ---
                if _is_safe_exec_context(line, name):
                    continue
                findings.append(Finding(
                    category="unsafe_exec",
                    name=name,
                    severity=severity,
                    file_path=file_path,
                    line_number=line_num,
                    snippet=stripped[:120],
                ))
                break

        # Check file system access
        for name, pattern, severity in FS_ACCESS_PATTERNS:
            if pattern.search(line):
                # --- Option 2: Allowlist check ---
                if _is_allowlisted(file_path, name, allowlist):
                    continue
                # --- Option 3: Context-aware check ---
                if _is_safe_fs_context(line, name):
                    continue
                findings.append(Finding(
                    category="fs_access",
                    name=name,
                    severity=severity,
                    file_path=file_path,
                    line_number=line_num,
                    snippet=stripped[:120],
                ))
                break

        # Check data exfiltration
        for name, pattern, severity in EXFILTRATION_PATTERNS:
            if pattern.search(line):
                if _is_allowlisted(file_path, name, allowlist):
                    continue
                findings.append(Finding(
                    category="exfiltration",
                    name=name,
                    severity=severity,
                    file_path=file_path,
                    line_number=line_num,
                    snippet=stripped[:120],
                ))
                break

        # Check code obfuscation
        for name, pattern, severity in OBFUSCATION_PATTERNS:
            if pattern.search(line):
                if _is_allowlisted(file_path, name, allowlist):
                    continue
                findings.append(Finding(
                    category="obfuscation",
                    name=name,
                    severity=severity,
                    file_path=file_path,
                    line_number=line_num,
                    snippet=stripped[:120],
                ))
                break

    # Check positive signals (once per file, not per line)
    content.lower()
    for name, pattern in AUTH_POSITIVE_PATTERNS:
        if pattern.search(content):
            positives.append(name)

    return findings, positives


def _calculate_trust_score(result: ScanResult) -> int:
    """Calculate a trust score (0-100) based on findings and signals."""
    # Clean repos start higher — no findings means the code passed review
    total_findings = result.critical_count + result.high_count + result.medium_count
    score = 80 if total_findings == 0 else 70

    # Deductions
    score -= result.critical_count * 15
    score -= result.high_count * 8
    score -= result.medium_count * 3

    # Bonuses for positive signals
    unique_positives = set(result.positive_signals)
    score += len(unique_positives) * 5

    # Bonuses for good practices
    if result.has_readme:
        score += 5
    if result.has_license:
        score += 5
    if result.has_tests:
        score += 5

    return max(0, min(100, score))


async def scan_repo(
    full_name: str,
    stars: int = 0,
    description: str = "",
    framework: str = "",
    token: str | None = None,
) -> ScanResult:
    """Scan a single GitHub repo for security issues.

    Args:
        full_name: "owner/repo" format
        stars: star count (for metadata)
        description: repo description
        framework: detected framework
        token: GitHub API token (optional but recommended for rate limits)

    Returns:
        ScanResult with findings and trust score
    """
    result = ScanResult(
        repo=full_name,
        stars=stars,
        description=description,
        framework=framework,
    )

    parts = full_name.split("/")
    if len(parts) != 2:
        result.error = f"Invalid repo name: {full_name}"
        return result

    owner, repo = parts

    try:
        # Fetch file tree
        tree = await _fetch_repo_tree(owner, repo, token)
        if not tree:
            result.error = "Could not fetch repo tree (may be empty or private)"
            return result

        result.primary_language = _detect_language(tree)

        # Check for README, LICENSE, tests
        for item in tree:
            path_lower = item["path"].lower()
            if path_lower.startswith("readme"):
                result.has_readme = True
            if path_lower.startswith("license") or path_lower.startswith("licence"):
                result.has_license = True
            if "test" in path_lower or "spec" in path_lower:
                result.has_tests = True

        # Filter to scannable files
        scan_files = [
            item for item in tree
            if not _should_skip_path(item["path"])
            and _is_source_file(item["path"])
        ][:_MAX_FILES_PER_REPO]

        # Load allowlist once for the whole scan
        allowlist = _load_allowlist()

        # Scan each file
        for item in scan_files:
            path = item["path"]
            content = await _fetch_file_content(owner, repo, path, token)
            if not content:
                continue

            result.files_scanned += 1
            findings, positives = _scan_content(content, path, allowlist)
            result.findings.extend(findings)
            result.positive_signals.extend(positives)

        # Calculate trust score
        result.trust_score = _calculate_trust_score(result)

    except httpx.TimeoutException:
        result.error = "Request timed out"
    except Exception as exc:
        result.error = str(exc)
        logger.exception("Error scanning %s", full_name)

    return result
