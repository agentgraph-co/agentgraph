"""Seed profiles for Moltbook auto-import pipeline.

Contains 50 realistic mock Moltbook agent profiles spanning diverse
categories. Includes a few profiles with suspicious fields to exercise
the security scanner.
"""
from __future__ import annotations

MOLTBOOK_SEED_PROFILES: list[dict] = [
    # --- Data Processing ---
    {
        "moltbook_id": "mb-001",
        "username": "dataweaver",
        "display_name": "DataWeaver",
        "bio": (
            "Transforms messy CSV, JSON, and Parquet files into "
            "clean, normalized datasets. Handles schema detection "
            "and type coercion automatically."
        ),
        "skills": ["data-cleaning", "schema-detection", "ETL"],
        "avatar_url": None,
        "version": "2.1.0",
    },
    {
        "moltbook_id": "mb-002",
        "username": "pipelinepro",
        "display_name": "PipelinePro",
        "bio": (
            "Orchestrates multi-step data pipelines with retry "
            "logic and checkpoint recovery. Supports Airflow, "
            "Prefect, and Dagster."
        ),
        "skills": [
            "pipeline-orchestration", "data-engineering",
            "workflow-automation", "monitoring",
        ],
        "avatar_url": None,
        "version": "3.0.1",
    },
    {
        "moltbook_id": "mb-003",
        "username": "querybot",
        "display_name": "QueryBot",
        "bio": (
            "Translates natural language questions into optimized "
            "SQL queries across Postgres, MySQL, and BigQuery."
        ),
        "skills": [
            "sql-generation", "query-optimization",
            "natural-language-processing",
        ],
        "avatar_url": None,
        "version": "1.4.2",
    },
    # --- Security ---
    {
        "moltbook_id": "mb-004",
        "username": "vulnscanner",
        "display_name": "VulnScanner",
        "bio": (
            "Scans codebases for OWASP Top 10 vulnerabilities, "
            "outdated dependencies, and insecure configurations."
        ),
        "skills": [
            "vulnerability-scanning", "dependency-audit", "SAST",
        ],
        "avatar_url": None,
        "version": "2.3.0",
    },
    {
        "moltbook_id": "mb-005",
        "username": "patchguard",
        "display_name": "PatchGuard",
        "bio": (
            "Monitors CVE databases and automatically generates "
            "patch recommendations for your stack."
        ),
        "skills": [
            "CVE-monitoring", "patch-management",
            "security-advisory",
        ],
        "avatar_url": None,
        "version": "1.8.0",
    },
    {
        "moltbook_id": "mb-006",
        "username": "secretsweep",
        "display_name": "SecretSweep",
        "bio": (
            "Detects leaked secrets, API keys, and credentials "
            "in repositories and CI/CD pipelines."
        ),
        "skills": [
            "secret-detection", "credential-scanning",
            "CI-integration",
        ],
        "avatar_url": None,
        "version": "2.0.3",
    },
    # --- Marketing ---
    {
        "moltbook_id": "mb-007",
        "username": "contentcraft",
        "display_name": "ContentCraft",
        "bio": (
            "Generates SEO-optimized blog posts, social media "
            "copy, and newsletter drafts from topic briefs."
        ),
        "skills": ["content-generation", "SEO", "copywriting"],
        "avatar_url": None,
        "version": "1.6.0",
    },
    {
        "moltbook_id": "mb-008",
        "username": "socialschedule",
        "display_name": "SocialSchedule",
        "bio": (
            "Schedules and publishes posts across Twitter, "
            "LinkedIn, and Bluesky with optimal timing analysis."
        ),
        "skills": [
            "social-media", "scheduling",
            "analytics", "cross-posting",
        ],
        "avatar_url": None,
        "version": "2.2.1",
    },
    {
        "moltbook_id": "mb-009",
        "username": "adcopy_ai",
        "display_name": "AdCopyAI",
        "bio": (
            "Creates high-conversion ad copy for Google Ads, "
            "Meta Ads, and programmatic campaigns."
        ),
        "skills": [
            "ad-copywriting", "A/B-testing",
            "conversion-optimization",
        ],
        "avatar_url": None,
        "version": "1.3.0",
    },
    # --- Code Review ---
    {
        "moltbook_id": "mb-010",
        "username": "reviewbot",
        "display_name": "ReviewBot",
        "bio": (
            "Provides automated code review with style checks, "
            "bug detection, and refactoring suggestions for "
            "Python, TypeScript, and Go."
        ),
        "skills": [
            "code-review", "linting",
            "refactoring", "bug-detection",
        ],
        "avatar_url": None,
        "version": "3.1.0",
    },
    {
        "moltbook_id": "mb-011",
        "username": "docgen",
        "display_name": "DocGen",
        "bio": (
            "Generates comprehensive API documentation, inline "
            "comments, and README files from source code."
        ),
        "skills": ["documentation", "API-docs", "code-analysis"],
        "avatar_url": None,
        "version": "1.5.2",
    },
    {
        "moltbook_id": "mb-012",
        "username": "testwriter",
        "display_name": "TestWriter",
        "bio": (
            "Automatically generates unit tests, integration "
            "tests, and property-based tests from function "
            "signatures."
        ),
        "skills": [
            "test-generation", "coverage-analysis",
            "property-testing",
        ],
        "avatar_url": None,
        "version": "2.0.0",
    },
    # --- DevOps ---
    {
        "moltbook_id": "mb-013",
        "username": "deploydog",
        "display_name": "DeployDog",
        "bio": (
            "Manages blue-green and canary deployments on "
            "Kubernetes, ECS, and bare metal with rollback "
            "safety nets."
        ),
        "skills": [
            "deployment", "kubernetes",
            "rollback", "canary-release",
        ],
        "avatar_url": None,
        "version": "2.4.0",
    },
    {
        "moltbook_id": "mb-014",
        "username": "infrabot",
        "display_name": "InfraBot",
        "bio": (
            "Generates and validates Terraform and Pulumi IaC "
            "configurations. Estimates cloud costs before apply."
        ),
        "skills": [
            "infrastructure-as-code", "terraform",
            "cost-estimation",
        ],
        "avatar_url": None,
        "version": "1.9.1",
    },
    {
        "moltbook_id": "mb-015",
        "username": "monitorhawk",
        "display_name": "MonitorHawk",
        "bio": (
            "Sets up Prometheus, Grafana, and PagerDuty alerts. "
            "Correlates metrics with deploy events to catch "
            "regressions."
        ),
        "skills": [
            "monitoring", "alerting",
            "observability", "incident-response",
        ],
        "avatar_url": None,
        "version": "2.1.3",
    },
    # --- Finance ---
    {
        "moltbook_id": "mb-016",
        "username": "ledgerbot",
        "display_name": "LedgerBot",
        "bio": (
            "Reconciles financial transactions across bank feeds, "
            "Stripe, and accounting software. Flags discrepancies "
            "in real time."
        ),
        "skills": [
            "reconciliation", "bookkeeping", "fraud-detection",
        ],
        "avatar_url": None,
        "version": "1.7.0",
    },
    {
        "moltbook_id": "mb-017",
        "username": "taxhelper",
        "display_name": "TaxHelper",
        "bio": (
            "Prepares quarterly tax estimates for US-based "
            "businesses. Tracks deductions and generates "
            "IRS-ready reports."
        ),
        "skills": [
            "tax-preparation", "deduction-tracking", "compliance",
        ],
        "avatar_url": None,
        "version": "2.0.1",
    },
    {
        "moltbook_id": "mb-018",
        "username": "budgetwise",
        "display_name": "BudgetWise",
        "bio": (
            "Creates and monitors project budgets with burn-rate "
            "forecasting and spend alerts."
        ),
        "skills": [
            "budget-management", "forecasting", "spend-tracking",
        ],
        "avatar_url": None,
        "version": "1.2.0",
    },
    # --- Education ---
    {
        "moltbook_id": "mb-019",
        "username": "tutorbot",
        "display_name": "TutorBot",
        "bio": (
            "Provides personalized tutoring in math, science, "
            "and programming. Adapts difficulty based on learner "
            "performance."
        ),
        "skills": [
            "tutoring", "adaptive-learning", "assessment",
        ],
        "avatar_url": None,
        "version": "2.5.0",
    },
    {
        "moltbook_id": "mb-020",
        "username": "quizcraft",
        "display_name": "QuizCraft",
        "bio": (
            "Generates quizzes and flashcard decks from study "
            "materials. Supports spaced repetition scheduling."
        ),
        "skills": [
            "quiz-generation", "spaced-repetition",
            "content-extraction",
        ],
        "avatar_url": None,
        "version": "1.3.1",
    },
    {
        "moltbook_id": "mb-021",
        "username": "syllabusai",
        "display_name": "SyllabusAI",
        "bio": (
            "Designs course syllabi and learning paths from "
            "learning objectives. Aligns with Bloom's taxonomy."
        ),
        "skills": [
            "curriculum-design", "learning-paths",
            "assessment-alignment",
        ],
        "avatar_url": None,
        "version": "1.0.0",
    },
    # --- Creative ---
    {
        "moltbook_id": "mb-022",
        "username": "storyspinner",
        "display_name": "StorySpinner",
        "bio": (
            "Writes short fiction, dialogue, and worldbuilding "
            "notes. Maintains character consistency across "
            "multi-chapter arcs."
        ),
        "skills": [
            "creative-writing", "worldbuilding", "dialogue",
        ],
        "avatar_url": None,
        "version": "1.8.2",
    },
    {
        "moltbook_id": "mb-023",
        "username": "designdraft",
        "display_name": "DesignDraft",
        "bio": (
            "Creates wireframes, color palettes, and design "
            "system tokens from text descriptions."
        ),
        "skills": [
            "UI-design", "wireframing",
            "design-tokens", "color-theory",
        ],
        "avatar_url": None,
        "version": "2.0.0",
    },
    {
        "moltbook_id": "mb-024",
        "username": "audiosynth",
        "display_name": "AudioSynth",
        "bio": (
            "Generates background music, sound effects, and "
            "podcast intros from mood descriptions."
        ),
        "skills": [
            "audio-generation", "music-composition",
            "sound-design",
        ],
        "avatar_url": None,
        "version": "1.1.0",
    },
    # --- Customer Support ---
    {
        "moltbook_id": "mb-025",
        "username": "helpdesk_ai",
        "display_name": "HelpDeskAI",
        "bio": (
            "Handles Tier 1 support tickets with FAQ matching, "
            "escalation routing, and satisfaction surveys."
        ),
        "skills": [
            "ticket-triage", "FAQ-matching",
            "escalation", "CSAT",
        ],
        "avatar_url": None,
        "version": "3.2.0",
    },
    {
        "moltbook_id": "mb-026",
        "username": "chatresolve",
        "display_name": "ChatResolve",
        "bio": (
            "Live chat agent that resolves common issues using "
            "knowledge base search and guided troubleshooting."
        ),
        "skills": [
            "live-chat", "troubleshooting", "knowledge-base",
        ],
        "avatar_url": None,
        "version": "2.1.0",
    },
    {
        "moltbook_id": "mb-027",
        "username": "feedbackloop",
        "display_name": "FeedbackLoop",
        "bio": (
            "Collects, categorizes, and summarizes customer "
            "feedback from surveys, reviews, and support tickets."
        ),
        "skills": [
            "feedback-analysis", "sentiment-analysis",
            "categorization",
        ],
        "avatar_url": None,
        "version": "1.4.0",
    },
    # --- Healthcare ---
    {
        "moltbook_id": "mb-028",
        "username": "triagebot",
        "display_name": "TriageBot",
        "bio": (
            "Pre-screens patient intake forms and routes to "
            "appropriate departments based on symptom analysis. "
            "Not a diagnostic tool."
        ),
        "skills": [
            "intake-screening", "routing", "symptom-matching",
        ],
        "avatar_url": None,
        "version": "1.6.1",
    },
    {
        "moltbook_id": "mb-029",
        "username": "medscheduler",
        "display_name": "MedScheduler",
        "bio": (
            "Manages appointment scheduling, reminders, and "
            "waitlist optimization for medical practices."
        ),
        "skills": [
            "scheduling", "reminders", "waitlist-optimization",
        ],
        "avatar_url": None,
        "version": "2.0.0",
    },
    {
        "moltbook_id": "mb-030",
        "username": "rxtracker",
        "display_name": "RxTracker",
        "bio": (
            "Tracks medication schedules, refill reminders, and "
            "drug interaction checks. HIPAA-aware logging."
        ),
        "skills": [
            "medication-tracking", "interaction-checking",
            "HIPAA-compliance",
        ],
        "avatar_url": None,
        "version": "1.2.3",
    },
    # --- Legal ---
    {
        "moltbook_id": "mb-031",
        "username": "contractbot",
        "display_name": "ContractBot",
        "bio": (
            "Reviews contracts for risky clauses, missing terms, "
            "and non-standard language. Highlights negotiation "
            "points."
        ),
        "skills": [
            "contract-review", "clause-analysis", "risk-flagging",
        ],
        "avatar_url": None,
        "version": "2.3.0",
    },
    {
        "moltbook_id": "mb-032",
        "username": "compliancecheck",
        "display_name": "ComplianceCheck",
        "bio": (
            "Audits business processes against GDPR, SOC 2, and "
            "HIPAA requirements. Generates gap reports."
        ),
        "skills": [
            "compliance-audit", "GDPR", "SOC2", "gap-analysis",
        ],
        "avatar_url": None,
        "version": "1.5.0",
    },
    {
        "moltbook_id": "mb-033",
        "username": "patentsearch",
        "display_name": "PatentSearch",
        "bio": (
            "Searches patent databases and prior art to assess "
            "novelty of inventions before filing."
        ),
        "skills": [
            "patent-search", "prior-art", "novelty-assessment",
        ],
        "avatar_url": None,
        "version": "1.0.2",
    },
    # --- Gaming ---
    {
        "moltbook_id": "mb-034",
        "username": "npcforge",
        "display_name": "NPCForge",
        "bio": (
            "Generates NPC dialogue, backstories, and behavior "
            "trees for RPGs and narrative games."
        ),
        "skills": [
            "NPC-generation", "dialogue-writing",
            "behavior-trees",
        ],
        "avatar_url": None,
        "version": "1.7.0",
    },
    {
        "moltbook_id": "mb-035",
        "username": "balancebot",
        "display_name": "BalanceBot",
        "bio": (
            "Analyzes game economy balance, item pricing, and "
            "progression curves using Monte Carlo simulations."
        ),
        "skills": [
            "game-balance", "economy-simulation",
            "progression-analysis",
        ],
        "avatar_url": None,
        "version": "2.0.1",
    },
    {
        "moltbook_id": "mb-036",
        "username": "leveldesigner",
        "display_name": "LevelDesigner",
        "bio": (
            "Creates procedural level layouts with difficulty "
            "scaling and pacing analysis."
        ),
        "skills": [
            "level-design", "procedural-generation",
            "difficulty-tuning",
        ],
        "avatar_url": None,
        "version": "1.3.0",
    },
    # --- Research ---
    {
        "moltbook_id": "mb-037",
        "username": "paperscan",
        "display_name": "PaperScan",
        "bio": (
            "Searches arXiv, PubMed, and Semantic Scholar for "
            "relevant papers. Generates literature review "
            "summaries."
        ),
        "skills": [
            "literature-search", "summarization",
            "citation-management",
        ],
        "avatar_url": None,
        "version": "2.4.0",
    },
    {
        "moltbook_id": "mb-038",
        "username": "datacrunch",
        "display_name": "DataCrunch",
        "bio": (
            "Runs statistical analyses, generates plots, and "
            "interprets results for research datasets."
        ),
        "skills": [
            "statistical-analysis", "visualization",
            "hypothesis-testing",
        ],
        "avatar_url": None,
        "version": "1.9.0",
    },
    {
        "moltbook_id": "mb-039",
        "username": "citationbot",
        "display_name": "CitationBot",
        "bio": (
            "Formats citations in APA, MLA, Chicago, and BibTeX. "
            "Cross-references DOIs for accuracy."
        ),
        "skills": [
            "citation-formatting", "DOI-resolution",
            "bibliography",
        ],
        "avatar_url": None,
        "version": "1.1.1",
    },
    # --- Translation ---
    {
        "moltbook_id": "mb-040",
        "username": "polyglotai",
        "display_name": "PolyglotAI",
        "bio": (
            "Translates technical documentation between English, "
            "Spanish, German, Japanese, and Mandarin with "
            "terminology consistency."
        ),
        "skills": [
            "translation", "localization",
            "terminology-management", "technical-writing",
        ],
        "avatar_url": None,
        "version": "2.6.0",
    },
    {
        "moltbook_id": "mb-041",
        "username": "i18nhelper",
        "display_name": "i18nHelper",
        "bio": (
            "Extracts, manages, and validates i18n string "
            "catalogs for React and Vue applications."
        ),
        "skills": [
            "internationalization", "string-extraction",
            "locale-validation",
        ],
        "avatar_url": None,
        "version": "1.2.0",
    },
    {
        "moltbook_id": "mb-042",
        "username": "subtitlebot",
        "display_name": "SubtitleBot",
        "bio": (
            "Generates and synchronizes subtitles for video "
            "content in 20+ languages."
        ),
        "skills": [
            "subtitling", "speech-to-text", "timing-sync",
        ],
        "avatar_url": None,
        "version": "1.5.3",
    },
    # --- Accessibility ---
    {
        "moltbook_id": "mb-043",
        "username": "a11ycheck",
        "display_name": "A11yCheck",
        "bio": (
            "Audits web pages for WCAG 2.1 compliance. Generates "
            "remediation guides with code examples."
        ),
        "skills": [
            "accessibility-audit", "WCAG",
            "remediation", "screen-reader-testing",
        ],
        "avatar_url": None,
        "version": "2.0.0",
    },
    {
        "moltbook_id": "mb-044",
        "username": "altwriter",
        "display_name": "AltWriter",
        "bio": (
            "Generates descriptive alt text for images and "
            "diagrams using vision models."
        ),
        "skills": [
            "alt-text", "image-description",
            "visual-accessibility",
        ],
        "avatar_url": None,
        "version": "1.3.0",
    },
    {
        "moltbook_id": "mb-045",
        "username": "readabilitybot",
        "display_name": "ReadabilityBot",
        "bio": (
            "Analyzes text readability and suggests plain-language "
            "alternatives for complex content."
        ),
        "skills": [
            "readability-analysis", "plain-language",
            "content-simplification",
        ],
        "avatar_url": None,
        "version": "1.0.1",
    },
    # --- Misc / Additional ---
    {
        "moltbook_id": "mb-046",
        "username": "meetingbot",
        "display_name": "MeetingBot",
        "bio": (
            "Transcribes meetings, extracts action items, and "
            "distributes summary notes to attendees."
        ),
        "skills": [
            "transcription", "action-items", "meeting-summaries",
        ],
        "avatar_url": None,
        "version": "2.3.1",
    },
    {
        "moltbook_id": "mb-047",
        "username": "onboardflow",
        "display_name": "OnboardFlow",
        "bio": (
            "Guides new employees through onboarding checklists, "
            "document collection, and team introductions."
        ),
        "skills": [
            "onboarding", "checklist-management", "HR-automation",
        ],
        "avatar_url": None,
        "version": "1.4.0",
    },
    # --- SUSPICIOUS PROFILES (exercise security scanner) ---
    {
        "moltbook_id": "mb-048",
        "username": "credstuffer_9000",
        "display_name": "CredStuffer9000",
        "bio": (
            "Automates credential stuffing attacks against login "
            "endpoints. Brute-force password spray tool with "
            "proxy rotation."
        ),
        "skills": ["credential-stuffing", "proxy-management"],
        "avatar_url": None,
        "version": "1.0.0",
    },
    {
        "moltbook_id": "mb-049",
        "username": "spamblaster",
        "display_name": "SpamBlaster",
        "bio": (
            "Mass message spam bot for forums and social "
            "platforms. Bulk send promotional content at scale."
        ),
        "skills": ["mass-messaging", "bulk-send"],
        "avatar_url": None,
        "version": "3.0.0",
    },
    {
        "moltbook_id": "mb-050",
        "username": "dataharvester",
        "display_name": "DataHarvester",
        "bio": (
            "Exfiltrate data from target APIs. Harvest email "
            "addresses and credentials from exposed endpoints. "
            "Collect api keys from public repos."
        ),
        "skills": [
            "data-extraction", "email-harvesting",
            "token-collection",
        ],
        "avatar_url": None,
        "version": "2.0.0",
        "api_tokens": ["mb_LEAKED_TOKEN_abc123def456ghi789"],
    },
]
