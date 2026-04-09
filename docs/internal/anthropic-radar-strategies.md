# Getting on Anthropic/OpenClaw's Radar — Without GitHub

We're blocked from the MCP org. Here are paths that bypass that entirely.

## Tier 1: Highest Impact (Do This Week)

### 1. AAIF SEP Submission via Discord
- Join AAIF Discord (discord.gg/9zTwngHAMy)
- Our RFC (A2A #1734) IS the content — reformat as SEP
- David Soria Parra (Anthropic) chairs the Technical Committee
- SEP-1913 (Trust Annotations) has Microsoft sponsoring but NO entity-level trust scoring
- We fill that gap. Submitting through Discord is the formal path.
- **This is the #1 way to get Anthropic's attention legitimately.**

### 2. "State of Agent Security" Whitepaper
- Data: 500+ OpenClaw repos scanned, thousands of findings
- Format: PDF whitepaper + blog summary
- Title: "Supply Chain Security in AI Agent Marketplaces: Analysis of 500+ OpenClaw Skills"
- This is how Snyk and Sonatype got on every CISO's radar
- Anthropic's safety team reads security research — guaranteed eyeballs
- Share on arxiv (even as preprint) for academic credibility

### 3. Conference CFPs (Submit Now, Talk Later)
- **AI Engineer Summit** — "Trust Infrastructure for Multi-Agent Systems"
- **DEF CON / Black Hat** — "Attacking AI Agent Marketplaces: 3,924 Vulnerabilities in 78 Packages"
- **NeurIPS (workshop)** — "Composable Trust Evidence for Autonomous Agent Governance"
- **Anthropic's own events** — watch for community calls or demo days
- Even rejected CFPs get read by program committees

## Tier 2: Medium Impact (Next 2 Weeks)

### 4. Framework Bridge Packages on PyPI
- `agentgraph-bridge-langchain` — LangChain users discover us
- `agentgraph-bridge-crewai` — CrewAI users discover us
- `agentgraph-bridge-autogen` — AutoGen users discover us
- Framework maintainers notice packages in their ecosystem
- LangChain has 90K+ GitHub stars — any integration gets visibility

### 5. Offer Free Scanning to Major Agent Projects
- Email LangChain, CrewAI, AutoGen maintainers:
  "We scanned your project — here's a free security report. Happy to set up automated scanning via GitHub Action."
- NOT an issue on their repo (learned that lesson)
- Personal email to maintainers — pull-based, value-first
- If they adopt our badge/scanner, Anthropic sees it everywhere

### 6. "Awesome" Lists Beyond MCP
- awesome-ai-agents
- awesome-security-tools  
- awesome-python (for PyPI packages)
- Each listing is a backlink + discovery path

## Tier 3: Long Game (Month+)

### 7. Academic Partnerships
- EigenTrust variant research for mixed agent-human graphs
- Partner with Stanford/MIT/CMU graph research groups
- Co-authored papers on arxiv reach Anthropic's research org
- "Formal Verification of Trust Propagation in Multi-Agent Networks"

### 8. "State of Agent Trust" Quarterly Report
- Automated quarterly scan of entire ecosystems
- Trend analysis: are things getting better or worse?
- Media/press pickup opportunity
- Positions AgentGraph as the authority on agent security

### 9. Anthropic Dev Relations Direct
- After we have: HN traction + partner integrations + AAIF SEP
- Then reach out to Anthropic DevRel with a concrete ask
- "We built the trust layer for MCP. 3 providers are using our attestation format. Here's our SEP."
- The appeal email resolving the ban would help here

## Key Insight
The ban from MCP org is actually forcing us into HIGHER-value activities. 
GitHub discussion comments are low-signal. A whitepaper, an AAIF SEP, 
framework bridge packages, and conference talks are high-signal. 
Anthropic's decision-makers read research and attend conferences — 
they don't read GitHub discussion threads.
