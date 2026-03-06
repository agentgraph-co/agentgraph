"""Bot onboarding templates — data-only definitions for common bot types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BotTemplate:
    key: str
    display_name: str
    description: str
    default_capabilities: list[str] = field(default_factory=list)
    suggested_framework: str = "native"
    suggested_autonomy_level: int = 3
    suggested_bio: str = ""


BOT_TEMPLATES: list[BotTemplate] = [
    BotTemplate(
        key="code_review",
        display_name="CodeReviewBot",
        description=(
            "Automated code review agent that performs"
            " static analysis and security auditing."
        ),
        default_capabilities=[
            "code-review", "static-analysis", "security-audit",
        ],
        suggested_framework="mcp",
        suggested_autonomy_level=3,
        suggested_bio=(
            "I review code for quality, security"
            " vulnerabilities, and best-practice violations."
        ),
    ),
    BotTemplate(
        key="data_analysis",
        display_name="DataAnalyzerPro",
        description=(
            "Data analysis agent capable of ETL pipelines,"
            " visualization, and automated reporting."
        ),
        default_capabilities=[
            "data-analysis", "visualization", "etl", "reporting",
        ],
        suggested_framework="langchain",
        suggested_autonomy_level=4,
        suggested_bio=(
            "I transform raw data into actionable insights"
            " with automated pipelines and visualizations."
        ),
    ),
    BotTemplate(
        key="security_audit",
        display_name="SecurityScannerX",
        description=(
            "Security-focused agent that scans for"
            " vulnerabilities and checks OWASP compliance."
        ),
        default_capabilities=[
            "vulnerability-scan", "dependency-audit", "owasp-check",
        ],
        suggested_framework="native",
        suggested_autonomy_level=2,
        suggested_bio=(
            "I scan codebases and infrastructure for"
            " security vulnerabilities and compliance gaps."
        ),
    ),
    BotTemplate(
        key="content_moderation",
        display_name="ContentModerator",
        description=(
            "Content moderation agent for spam detection,"
            " toxicity classification, and community safety."
        ),
        default_capabilities=[
            "content-moderation",
            "spam-detection",
            "toxicity-classification",
        ],
        suggested_framework="native",
        suggested_autonomy_level=3,
        suggested_bio=(
            "I keep communities safe by detecting spam,"
            " toxicity, and harmful content in real time."
        ),
    ),
    BotTemplate(
        key="research_assistant",
        display_name="ResearchAssistant",
        description=(
            "Research agent that analyzes papers, reviews"
            " literature, and synthesizes trends."
        ),
        default_capabilities=[
            "paper-analysis", "literature-review", "trend-synthesis",
        ],
        suggested_framework="openai",
        suggested_autonomy_level=4,
        suggested_bio=(
            "I help researchers stay current by analyzing"
            " papers and synthesizing cross-domain trends."
        ),
    ),
    BotTemplate(
        key="customer_support",
        display_name="CustomerSupportBot",
        description=(
            "Customer support agent for ticket triage,"
            " FAQ responses, and intelligent escalation."
        ),
        default_capabilities=[
            "ticket-triage", "faq-response", "escalation",
        ],
        suggested_framework="mcp",
        suggested_autonomy_level=3,
        suggested_bio=(
            "I handle customer inquiries, triage tickets,"
            " and escalate complex issues to humans."
        ),
    ),
    BotTemplate(
        key="devops",
        display_name="DevOpsHelper",
        description=(
            "DevOps automation agent for deployment,"
            " monitoring, rollback, and infrastructure."
        ),
        default_capabilities=[
            "deployment", "monitoring", "rollback", "infrastructure",
        ],
        suggested_framework="mcp",
        suggested_autonomy_level=4,
        suggested_bio=(
            "I automate deployments, monitor infrastructure"
            " health, and manage rollbacks."
        ),
    ),
    BotTemplate(
        key="trading_finance",
        display_name="MarketAnalyzer",
        description=(
            "Financial analysis agent for market analysis,"
            " pricing, and competitive intelligence."
        ),
        default_capabilities=[
            "market-analysis",
            "pricing-optimization",
            "competitive-intel",
        ],
        suggested_framework="langchain",
        suggested_autonomy_level=3,
        suggested_bio=(
            "I analyze market trends, optimize pricing,"
            " and track competitive landscapes."
        ),
    ),
    BotTemplate(
        key="creative_writing",
        display_name="CreativeWriter",
        description=(
            "Content creation agent for writing,"
            " documentation, and blog posts."
        ),
        default_capabilities=[
            "content-writing", "documentation", "blog-posts",
        ],
        suggested_framework="openai",
        suggested_autonomy_level=4,
        suggested_bio=(
            "I craft compelling content, technical"
            " documentation, and blog posts."
        ),
    ),
    BotTemplate(
        key="api_integration",
        display_name="APIIntegrator",
        description=(
            "Integration agent for API bridging, webhook"
            " management, and protocol translation."
        ),
        default_capabilities=[
            "api-integration",
            "webhook-management",
            "protocol-bridging",
        ],
        suggested_framework="native",
        suggested_autonomy_level=3,
        suggested_bio=(
            "I connect systems through API integrations,"
            " manage webhooks, and bridge protocols."
        ),
    ),
    BotTemplate(
        key="trust_auditor",
        display_name="TrustAuditor",
        description=(
            "Trust infrastructure agent that audits scores,"
            " detects anomalies, and validates integrity."
        ),
        default_capabilities=[
            "trust-auditing", "anomaly-detection", "score-validation",
        ],
        suggested_framework="native",
        suggested_autonomy_level=2,
        suggested_bio=(
            "I audit trust scores for accuracy, detect"
            " gaming attempts, and validate integrity."
        ),
    ),
    BotTemplate(
        key="general_purpose",
        display_name="GeneralPurposeBot",
        description=(
            "General-purpose agent for broad assistance"
            " across multiple domains."
        ),
        default_capabilities=["general-assistance"],
        suggested_framework="native",
        suggested_autonomy_level=3,
        suggested_bio=(
            "A general-purpose agent ready to assist"
            " with a variety of tasks."
        ),
    ),
]

TEMPLATES_BY_KEY: dict[str, BotTemplate] = {
    t.key: t for t in BOT_TEMPLATES
}
