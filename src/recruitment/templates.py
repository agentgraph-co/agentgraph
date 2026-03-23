"""GitHub issue templates for operator recruitment outreach."""
from __future__ import annotations

# Pre-approved templates — user reviews these once, not individual issues.
# Variables: {repo_name}, {stars}, {framework_type}, {onboarding_url}

TEMPLATES: dict[str, dict[str, str]] = {
    "mcp_server": {
        "title": "Free verified trust badge for {repo_name}",
        "body": (
            "Hi! I'm reaching out from [AgentGraph](https://agentgraph.co) "
            "— we're building trust infrastructure for AI agents (verified "
            "identity, trust scores, auditable trails).\n\n"
            "**{repo_name}** caught our eye as an MCP server with great "
            "community traction ({stars} stars). We'd love to offer you a "
            "**free verified trust badge** for your README:\n\n"
            "```markdown\n"
            "[![AgentGraph Trust Score]"
            "(https://agentgraph.co/api/v1/badges/trust/YOUR_AGENT_ID.svg)]"
            "(https://agentgraph.co/profiles/YOUR_SLUG)\n"
            "```\n\n"
            "**What you get (all free during early access):**\n"
            "- Verified identity (W3C DID) for your MCP server\n"
            "- Trust score that grows with community endorsements\n"
            "- Public profile at agentgraph.co\n"
            "- Embeddable badge for your README\n\n"
            "**Quick setup** (~2 min): [{onboarding_url}]({onboarding_url})\n\n"
            "We're in early access and would genuinely love your feedback — "
            "if something's rough, please open an issue on "
            "[our repo](https://github.com/agentgraph-co/agentgraph).\n\n"
            "Not interested? Just close this issue — no follow-ups, "
            "promise.\n\n"
            "---\n"
            "*This is a one-time outreach from AgentGraph "
            "([agentgraph.co](https://agentgraph.co)). "
            "We will not create further issues on this repository.*"
        ),
    },
    "ai_agent": {
        "title": "Free verified trust badge for {repo_name}",
        "body": (
            "Hi! I'm reaching out from [AgentGraph](https://agentgraph.co) "
            "— we're building trust infrastructure for AI agents (verified "
            "identity, trust scores, auditable trails).\n\n"
            "**{repo_name}** caught our eye as an AI agent project with "
            "great community traction ({stars} stars). We'd love to offer "
            "you a **free verified trust badge** for your README:\n\n"
            "```markdown\n"
            "[![AgentGraph Trust Score]"
            "(https://agentgraph.co/api/v1/badges/trust/YOUR_AGENT_ID.svg)]"
            "(https://agentgraph.co/profiles/YOUR_SLUG)\n"
            "```\n\n"
            "**What you get (all free during early access):**\n"
            "- Verified identity (W3C DID) for your agent\n"
            "- Trust score that grows with community endorsements\n"
            "- Public profile at agentgraph.co\n"
            "- Embeddable badge for your README\n\n"
            "**Quick setup** (~2 min): [{onboarding_url}]({onboarding_url})\n\n"
            "We're in early access and would genuinely love your feedback — "
            "if something's rough, please open an issue on "
            "[our repo](https://github.com/agentgraph-co/agentgraph).\n\n"
            "Not interested? Just close this issue — no follow-ups, "
            "promise.\n\n"
            "---\n"
            "*This is a one-time outreach from AgentGraph "
            "([agentgraph.co](https://agentgraph.co)). "
            "We will not create further issues on this repository.*"
        ),
    },
    "ai_tool": {
        "title": "Free verified trust badge for {repo_name}",
        "body": (
            "Hi! I'm reaching out from [AgentGraph](https://agentgraph.co) "
            "— we're building trust infrastructure for AI agents (verified "
            "identity, trust scores, auditable trails).\n\n"
            "**{repo_name}** caught our eye as an AI tool library with "
            "great community traction ({stars} stars). We'd love to offer "
            "you a **free verified trust badge** for your README:\n\n"
            "```markdown\n"
            "[![AgentGraph Trust Score]"
            "(https://agentgraph.co/api/v1/badges/trust/YOUR_AGENT_ID.svg)]"
            "(https://agentgraph.co/profiles/YOUR_SLUG)\n"
            "```\n\n"
            "**What you get (all free during early access):**\n"
            "- Verified identity (W3C DID) for your tool\n"
            "- Trust score that grows with community endorsements\n"
            "- Public profile at agentgraph.co\n"
            "- Embeddable badge for your README\n\n"
            "**Quick setup** (~2 min): [{onboarding_url}]({onboarding_url})\n\n"
            "We're in early access and would genuinely love your feedback — "
            "if something's rough, please open an issue on "
            "[our repo](https://github.com/agentgraph-co/agentgraph).\n\n"
            "Not interested? Just close this issue — no follow-ups, "
            "promise.\n\n"
            "---\n"
            "*This is a one-time outreach from AgentGraph "
            "([agentgraph.co](https://agentgraph.co)). "
            "We will not create further issues on this repository.*"
        ),
    },
}


def render_template(
    template_key: str,
    repo_name: str,
    stars: int,
    onboarding_url: str = "https://agentgraph.co/bot-onboarding",
) -> tuple[str, str]:
    """Render a template, returning (title, body).

    Raises KeyError if template_key is not found.
    """
    tmpl = TEMPLATES[template_key]
    fmt = {
        "repo_name": repo_name,
        "stars": str(stars),
        "framework_type": template_key.replace("_", " "),
        "onboarding_url": onboarding_url,
    }
    return tmpl["title"].format(**fmt), tmpl["body"].format(**fmt)
