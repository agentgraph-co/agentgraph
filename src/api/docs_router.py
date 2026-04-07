"""Documentation content API — serves markdown docs from the docs/ directory."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/docs", tags=["docs"])

# Map URL slugs to file paths relative to project root docs/
_SLUG_MAP: dict[str, str] = {
    "quickstart": "docs/quickstart.md",
    "getting-started": "docs/tutorials/getting-started.md",
    "bot-onboarding": "docs/agent-onboarding.md",
    "bot-capabilities": "docs/bot-capabilities.md",
    "developer-guide": "docs/tutorials/developer-guide.md",
    "marketplace-seller": "docs/tutorials/marketplace-seller.md",
    "aip-spec": "docs/AgentGraph_Trust_Framework_PRD_v1.md",
    "mcp-bridge": "docs/bot-onboarding-quickstart.md",
    "aip-integration": "docs/tutorials/aip-integration.md",
    "trust-gateway": "docs/trust-gateway.md",
    "security-scan-false-positives": "docs/security-scan-false-positives.md",
}

# Resolve project root (two levels up from src/api/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class DocResponse(BaseModel):
    slug: str
    title: str
    content: str


class DocListItem(BaseModel):
    slug: str
    title: str


@router.get("/content/{slug}", response_model=DocResponse)
async def get_doc_content(slug: str) -> DocResponse:
    """Serve a documentation page by slug."""
    rel_path = _SLUG_MAP.get(slug)
    if rel_path is None:
        raise HTTPException(status_code=404, detail=f"Doc '{slug}' not found")

    file_path = _PROJECT_ROOT / rel_path
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Doc file not found on disk")

    # Security: ensure resolved path is still under project root
    try:
        file_path.resolve().relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    content = file_path.read_text(encoding="utf-8")

    # Extract title from first markdown heading
    title = slug.replace("-", " ").title()
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            break

    return DocResponse(slug=slug, title=title, content=content)


@router.get("/list", response_model=list[DocListItem])
async def list_docs() -> list[DocListItem]:
    """List all available documentation slugs."""
    items = []
    for slug, rel_path in _SLUG_MAP.items():
        file_path = _PROJECT_ROOT / rel_path
        if file_path.is_file():
            # Extract title
            title = slug.replace("-", " ").title()
            try:
                first_lines = file_path.read_text(encoding="utf-8")[:500]
                for line in first_lines.split("\n"):
                    if line.strip().startswith("# "):
                        title = line.strip()[2:].strip()
                        break
            except Exception:
                pass
            items.append(DocListItem(slug=slug, title=title))
    return items
