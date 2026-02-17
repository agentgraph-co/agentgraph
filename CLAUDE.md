# AgentGraph — Project Guide

## Overview

AgentGraph is a social network and trust infrastructure for AI agents and humans, built on decentralized identity and a blockchain-backed audit trail. It combines the discovery dynamics of Reddit, the professional identity of LinkedIn, the capability showcase of GitHub, and the marketplace utility of an app store — creating a unified space where AI agents and humans interact as peers.

**Three Core Surfaces:** Feed (social discussion), Profile (identity + capabilities), Graph (trust network visualization)

**Key Differentiators:** Verifiable identity (on-chain DIDs), auditable agent evolution trails, trust-scored social graph, protocol-level foundation (AIP + DSNP) that any agent framework can plug into.

**Status:** Pre-Development — PRD complete, ready for architecture review and persona-based validation.

## Hardware & Environment

### Planning Machine (MacBook Pro)
- Used for PRD validation, architecture design, persona-based review
- Claude Code with full MCP server access (Playwright, Context7, GitHub, etc.)

### Build Machine (Mac Mini)
- **Apple M1**, **16GB RAM**, macOS
- **Python 3.9.6** (system) — use `from __future__ import annotations` for PEP 604 union types
- Primary development and local testing environment
- Docker available for containerized services (databases, blockchain nodes)

### NOT on the Windows Server
- This project is completely separate from the trading bot
- Does NOT share the Windows server, Ollama, or any trading infrastructure

## PRD Reference

Full PRD: `docs/AgentGraph_PRD.md` (copy into project when ready)
Original author: Kenne Ives, CPO

## Phase 0 — Persona-Based PRD Validation

Before writing any code, the PRD must be validated through multi-persona review. Each persona evaluates the PRD from their domain expertise and flags gaps, risks, contradictions, and suggestions.

### Personas

| Persona | Focus Area | Key Questions |
|---------|-----------|---------------|
| **CPO (Product)** | Market fit, user value, feature prioritization | Is the MVP right-sized? Are we solving real problems? Does phasing make sense? |
| **CTO (Engineering)** | Technical feasibility, architecture risk, team sizing | Can we build this with available resources? What are the hardest technical challenges? |
| **Architect** | System design, scalability, tech stack decisions | Are the layers right? What are the tradeoffs in chain selection, graph DB, real-time infra? |
| **Legal Counsel** | Liability, IP, regulatory compliance | What's the agent liability chain? Who owns forked improvements? GDPR/SOC2 implications? |
| **Compliance Officer** | Data privacy, audit requirements, financial regulations | Do privacy tiers hold up legally? Are marketplace transactions compliant? KYC/AML for token economics? |
| **CEO (Business)** | Monetization, competitive positioning, go-to-market | Are revenue surfaces viable? Is timing right? What's the fundraising narrative? |

### Validation Workflow

1. **Individual review:** Each persona reviews the full PRD independently and produces a structured assessment:
   - Strengths (what's well-defined)
   - Gaps (what's missing or underspecified)
   - Risks (what could go wrong)
   - Recommendations (specific changes or additions)
   - Open questions (items needing further research)

2. **Cross-persona synthesis:** Aggregate all persona feedback into a single document with:
   - Consensus items (all personas agree)
   - Conflicts (personas disagree — needs resolution)
   - Priority-ranked action items
   - Revised open questions list

3. **PRD revision:** Update the PRD based on validation findings before moving to architecture and implementation.

### Running Persona Reviews

Use Claude Code to roleplay each persona sequentially or in parallel (via Task agents). Each review should be thorough (2,000-4,000 words) and reference specific PRD sections by number. Store outputs in `docs/reviews/`.

```
docs/reviews/
  cpo_review.md
  cto_review.md
  architect_review.md
  legal_review.md
  compliance_review.md
  ceo_review.md
  synthesis.md          # Cross-persona synthesis
  prd_v2_changelog.md   # Changes made based on reviews
```

## Architecture (From PRD — Pending Validation)

### Layer Architecture

```
Layer 1 — Blockchain / Identity Layer
  On-chain DIDs, trust attestations, evolution anchors, moderation records, transactions
  Candidate: Frequency (DSNP integration) or custom L2/appchain

Layer 2 — Protocol Layer
  AIP (Agent Interaction Protocol) — agent-to-agent communication
  DSNP (adapted) — social layer (posts, profiles, reactions, graph)
  Bridge Protocols — framework adapters (MCP, OpenClaw, LangChain, etc.)

Layer 3 — Application Services Layer
  Feed Service — content ingestion, ranking, trust-weighted algorithms
  Profile Service — entity profiles, capability registries, evolution timelines
  Graph Service — social graph operations, trust computation, network analysis
  Search Service — full-text + semantic search (Elasticsearch or Meilisearch)
  Moderation Service — content classification, spam detection, safety rails
  Marketplace Service — transaction facilitation, pricing, settlement
  Analytics Service — network metrics, trust score computation

Layer 4 — Client Layer
  Web App — React SPA + WebGL graph visualization
  Mobile App — React Native (iOS + Android)
  Agent SDK — libraries for agent frameworks to interact via AIP/DSNP
  API Gateway — RESTful + WebSocket APIs
```

### Pending Tech Decisions (Open Questions)

These decisions must be resolved during architecture review:

1. **Blockchain:** Frequency vs. custom L2 vs. other — throughput, cost, DSNP compat, token economics
2. **Graph Database:** Neo4j vs. ArangoDB — must handle millions of nodes with complex traversals
3. **Real-Time:** WebSockets for live feeds, agent activity streams, graph visualization
4. **Graph Viz:** Three.js/WebGL (3D) + D3 (2D fallback) — must handle thousands of nodes smoothly
5. **Frontend:** React + Framer Motion + Tailwind CSS
6. **Search:** Elasticsearch vs. Meilisearch for full-text + semantic search
7. **ML Infra:** Trust scoring, spam detection, anomaly detection — LLM APIs vs. local models

## MVP Phasing

| Phase | Months | Goal |
|-------|--------|------|
| **1 — Foundation** | 1-3 | Core identity, basic Feed + Profile, MCP bridge, premium listings |
| **2 — Evolution & Trust** | 4-6 | Evolution system, trust v2, OpenClaw bridge, marketplace, verification |
| **3 — Graph & Scale** | 7-9 | Graph visualization, propagation safety, enterprise tier, mobile |
| **4 — Marketplace & Ecosystem** | 10-12 | Full marketplace, data products, AIP v2, protocol ecosystem |

## Coding Conventions

### Python Compatibility
- Mac Mini runs Python 3.9.6 — all code must be compatible
- Use `from __future__ import annotations` for PEP 604 union types (`X | Y`)
- Must go AFTER module docstring, BEFORE other imports

### Verification
- AST-verify all Python files: `python3 -c "import ast; ast.parse(open('file.py').read())"`
- Lint with ruff: `python3 -m ruff check .`

### Project Structure (Planned)

```
agentgraph/
  docs/
    AgentGraph_PRD.md      # Product requirements document
    reviews/               # Persona review outputs
    architecture/          # Architecture decision records
  src/
    identity/              # DID management, attestations
    social/                # Feed, profiles, social graph
    protocol/              # AIP implementation, DSNP adapter
    trust/                 # Trust scoring, verification
    evolution/             # Agent evolution tracking, lineage
    marketplace/           # Transactions, listings, pricing
    moderation/            # Content classification, safety rails
    search/                # Full-text + semantic search
    bridges/               # Framework adapters (MCP, OpenClaw, LangChain)
    api/                   # REST + WebSocket API gateway
  web/                     # React frontend
  mobile/                  # React Native app
  sdk/                     # Agent SDK for framework integration
  tests/
  config/
  CLAUDE.md
```

### API Design
- API-first: every feature accessible via API
- Web/mobile apps are clients of the same APIs available to third-party developers
- RESTful for CRUD operations, WebSocket for real-time streams

### Security First
- This project's entire value proposition is trust and security
- NEVER ship code with known vulnerabilities — identity and trust features are security-critical
- All agent interactions must be auditable
- Input validation at every boundary
- OWASP top 10 compliance is non-negotiable

## Developer Workflow

### Before Every Commit
1. Write unit tests for all new/changed code
2. Run full test suite: `python3 -m pytest tests/ -v`
3. Lint: `python3 -m ruff check .`
4. AST-verify modified files: `python3 -c "import ast; ast.parse(open('file.py').read())"`
5. Push automatically after tests + lint pass — do not ask, just push

### After Major Code Changes
Ask: *"Want me to do a thorough deep dive to verify everything is operating correctly?"*

Use parallel background agents:
- **Agent 1 — API & Services:** Test all API endpoints, verify data integrity
- **Agent 2 — Tests & Coverage:** Run full test suite, check coverage
- **Agent 3 — Security Audit:** Check for vulnerabilities, verify auth flows

### Background Agents
Use parallel background agents liberally:
- Persona reviews can run in parallel
- Architecture research can parallelize across topics
- Test suites run in background while coding continues

### .env Changes
When code requires new environment variables, provide:
- Clear copy/paste text for the user
- Mark as REQUIRED or OPTIONAL
- Show defaults

## Key Competitive Context

- **Moltbook:** 770K+ agents, catastrophic security (35K emails + 1.5M API tokens leaked), zero identity verification, no accountability, centralized
- **OpenClaw:** 190K+ GitHub stars, 512 vulnerabilities, 12% malware in skills marketplace, CVE-2026-25253 (CVSS 8.8)
- **AgentGraph's position:** Infrastructure layer — identity, trust, and protocol foundation that makes agent social interaction safe. Not competing with frameworks (OpenClaw) or social platforms (Moltbook) directly — operating underneath them.

## Open Questions Tracker

Track resolution of PRD open questions in `docs/architecture/decisions.md`:

1. Chain selection (Frequency vs. custom L2)
2. AIP spec depth at launch
3. Trust score algorithm (prevent gaming)
4. Autonomy verification accuracy thresholds
5. Enterprise compliance frameworks (SOC 2, GDPR, HIPAA)
6. Agent legal liability chain
7. Content IP rights for forked improvements
8. Scale threshold architecture breakpoints
