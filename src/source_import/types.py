from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceImportResult:
    source_type: str       # github, npm, pypi, huggingface, mcp_manifest, a2a_card, moltbook
    source_url: str
    display_name: str
    bio: str
    capabilities: list[str] = field(default_factory=list)
    detected_framework: str | None = None
    autonomy_level: int | None = None
    community_signals: dict = field(default_factory=dict)
    raw_metadata: dict = field(default_factory=dict)
    readme_excerpt: str = ""
    avatar_url: str | None = None
    version: str | None = None
