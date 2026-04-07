"""Regex patterns for security scanning."""
from __future__ import annotations

import re

# --- Hardcoded secrets ---
# Each tuple: (name, compiled regex, severity)
SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "AWS Access Key",
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "critical",
    ),
    (
        "AWS Secret Key",
        re.compile(
            r"""(?:aws_secret_access_key|secret_key)\s*[=:]\s*['"]([A-Za-z0-9/+=]{40})['"]""",
            re.IGNORECASE,
        ),
        "critical",
    ),
    (
        "OpenAI API Key",
        re.compile(r"sk-[a-zA-Z0-9]{20,}T3BlbkFJ[a-zA-Z0-9]{20,}"),
        "critical",
    ),
    (
        "OpenAI Project Key",
        re.compile(r"sk-proj-[a-zA-Z0-9_-]{40,}"),
        "critical",
    ),
    (
        "Anthropic API Key",
        re.compile(r"sk-ant-[a-zA-Z0-9_-]{40,}"),
        "critical",
    ),
    (
        "Generic API Key assignment",
        re.compile(
            r"""(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[=:]\s*['"]([a-zA-Z0-9_\-/+=]{20,})['"]""",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "Private Key block",
        re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
        "critical",
    ),
    (
        "GitHub Token",
        re.compile(r"gh[ps]_[a-zA-Z0-9]{36,}"),
        "critical",
    ),
    (
        "Slack Token",
        re.compile(r"xox[bpars]-[a-zA-Z0-9-]+"),
        "high",
    ),
    (
        "Base64 encoded long secret",
        re.compile(
            r"""(?:secret|key|token|password)\s*[=:]\s*['"]([A-Za-z0-9+/]{40,}={0,2})['"]""",
            re.IGNORECASE,
        ),
        "medium",
    ),
]

# --- Unsafe execution patterns ---
UNSAFE_EXEC_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "subprocess.run / Popen (Python)",
        re.compile(r"subprocess\.(run|Popen|call|check_output)\s*\("),
        "high",
    ),
    (
        "os.system / os.popen (Python)",
        re.compile(r"os\.(system|popen)\s*\("),
        "high",
    ),
    (
        "eval() call",
        re.compile(r"\beval\s*\("),
        "high",
    ),
    (
        "exec() call (Python)",
        re.compile(r"\bexec\s*\("),
        "high",
    ),
    (
        "child_process (Node.js)",
        re.compile(r"""(?:require\s*\(\s*['"]child_process['"]\)|from\s+['"]child_process['"])"""),
        "high",
    ),
    (
        "execSync / spawn (Node.js)",
        re.compile(r"\b(?:execSync|spawnSync|exec)\s*\("),
        "high",
    ),
    (
        "shell=True (Python)",
        re.compile(r"shell\s*=\s*True"),
        "critical",
    ),
    (
        "Command.new / system (Ruby)",
        re.compile(r"(?:system|`|%x)\s*[\(\[]"),
        "medium",
    ),
    (
        "os/exec (Go)",
        re.compile(r"""exec\.Command\s*\("""),
        "medium",
    ),
    (
        "std::process::Command (Rust)",
        re.compile(r"Command::new\s*\("),
        "medium",
    ),
]

# --- File system access patterns (without explicit sandboxing) ---
FS_ACCESS_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "Unrestricted file read (Python)",
        re.compile(r"open\s*\([^)]*\)\s*\.?\s*read"),
        "medium",
    ),
    (
        "Unrestricted file write (Python)",
        re.compile(r"open\s*\([^)]*['\"]w['\"][^)]*\)"),
        "medium",
    ),
    (
        "fs.readFileSync / writeFileSync (Node.js)",
        re.compile(r"fs\.(?:readFileSync|writeFileSync|readFile|writeFile)\s*\("),
        "medium",
    ),
    (
        "Path traversal risk (../ in string)",
        re.compile(r"""['"]\.\.[\\/]"""),
        "high",
    ),
    (
        "rmrf / recursive delete",
        re.compile(r"(?:shutil\.rmtree|fs\.rm.*recursive|rimraf)\s*\("),
        "high",
    ),
]

# --- Data exfiltration patterns ---
EXFILTRATION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "HTTP POST with sensitive data",
        re.compile(
            r"""(?:requests\.post|httpx\.post|fetch|axios\.post)\s*\([^)]*(?:key|secret|token|password|credential)""",
            re.IGNORECASE,
        ),
        "high",
    ),
    (
        "Outbound webhook/exfil URL",
        re.compile(
            r"""(?:webhook\.site|requestbin|pipedream|ngrok|burp|interact\.sh)""",
            re.IGNORECASE,
        ),
        "critical",
    ),
    (
        "Base64 encode + send",
        re.compile(r"base64\.b64encode.*(?:post|send|request)", re.IGNORECASE),
        "high",
    ),
    (
        "Environment variable exfil",
        re.compile(
            r"""os\.environ.*(?:post|send|request|fetch)""",
            re.IGNORECASE,
        ),
        "critical",
    ),
    (
        "DNS exfiltration pattern",
        re.compile(
            r"""(?:socket\.gethostbyname|dns\.resolve).*(?:encode|secret|key)""",
            re.IGNORECASE,
        ),
        "critical",
    ),
]

# --- Code obfuscation patterns ---
OBFUSCATION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "Hex-encoded string execution",
        re.compile(r"""\\x[0-9a-fA-F]{2}(?:\\x[0-9a-fA-F]{2}){10,}"""),
        "high",
    ),
    (
        "String char-code assembly",
        re.compile(r"""String\.fromCharCode\s*\((?:\s*\d+\s*,\s*){5,}"""),
        "high",
    ),
    (
        "Obfuscated eval (Python)",
        re.compile(r"""getattr\s*\(\s*__builtins__\s*,"""),
        "critical",
    ),
    (
        "Dynamic import with variable",
        re.compile(r"""__import__\s*\(\s*[a-zA-Z_]"""),
        "medium",
    ),
    (
        "Reversed/rotated string decode",
        re.compile(
            r"""(?:reversed|rot13|codecs\.decode)\s*\(.*(?:exec|eval|import)""",
            re.IGNORECASE,
        ),
        "high",
    ),
]

# --- Auth/security positive signals ---
# These REDUCE risk when found.
AUTH_POSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Authentication check", re.compile(
        r"(?:authenticate|verify_token|check_auth|requireAuth|isAuthenticated)",
        re.IGNORECASE,
    )),
    ("Authorization check", re.compile(
        r"(?:authorize|check_permission|has_role|requireRole)",
        re.IGNORECASE,
    )),
    ("Input validation", re.compile(
        r"(?:validate|sanitize|escape|zod\.object|pydantic|BaseModel)",
        re.IGNORECASE,
    )),
    ("Rate limiting", re.compile(r"(?:rate.?limit|throttle|RateLimiter)", re.IGNORECASE)),
    ("CORS configuration", re.compile(r"(?:cors|Access-Control-Allow)", re.IGNORECASE)),
    ("Content-Security-Policy", re.compile(r"Content-Security-Policy", re.IGNORECASE)),
    ("Helmet / security headers", re.compile(r"(?:helmet|security.?headers)", re.IGNORECASE)),
    ("Cryptographic verification", re.compile(
        r"(?:hmac|hashlib\.(?:sha|md5)|cryptography\.|jwt\.(?:encode|decode|verify)|verify_signature)",
        re.IGNORECASE,
    )),
    ("Input sanitization", re.compile(
        r"(?:html\.escape|urllib\.parse\.quote|bleach\.clean|markupsafe|nh3\.clean|DOMPurify)",
        re.IGNORECASE,
    )),
    ("Logging / audit trail", re.compile(
        r"(?:logging\.getLogger|logger\.(?:info|warning|error)|audit_log|structlog)",
        re.IGNORECASE,
    )),
    ("Error handling", re.compile(
        r"(?:try\s*:|except\s+\w|\.catch\s*\(|error\s*boundary|rescue\s+)",
        re.IGNORECASE,
    )),
    ("Type safety", re.compile(
        r"(?:from\s+typing\s+import|TypeVar|Generic\[|pydantic\.BaseModel|@dataclass|interface\s+\w+\s*\{)",
        re.IGNORECASE,
    )),
    ("Dependency pinning", re.compile(
        r"(?:requirements\.txt|poetry\.lock|package-lock\.json|Pipfile\.lock|Cargo\.lock)",
        re.IGNORECASE,
    )),
]

# --- Files to skip (binary, generated, vendor) ---
SKIP_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".zip", ".tar", ".gz", ".bz2",
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll", ".exe",
    ".lock", ".sum",
    ".min.js", ".min.css",
})

SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", "dist", "build",
    "vendor", ".venv", "venv", "env", ".env",
    "target", "coverage", ".next", ".nuxt",
})

# Source file extensions to scan
SOURCE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".rb", ".java", ".kt", ".cs",
    ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml", ".json", ".env",
    ".cfg", ".ini", ".conf",
})
