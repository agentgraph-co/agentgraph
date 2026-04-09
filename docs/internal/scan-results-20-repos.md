# Batch Scan Results — 20 Popular AI Agent Repos
## April 8, 2026

### Headline Stats
- **17 repos scanned** (3 not found/renamed)
- **Average trust score: 47/100**
- **47% scored 0 (blocked)** — scanner recommends zero automated trust
- **76.5% contain unsafe execution patterns** (eval, exec, subprocess)
- **41% have critical-severity findings**
- **Only 29% achieved "verified" tier** (score >= 90)

### Notable Findings
- **modelcontextprotocol/servers** (Anthropic's reference MCP servers): **0/100 blocked** — 131 findings (115 fs_access, 16 unsafe_exec)
- **openai/openai-python**: **0/100 blocked** — 78 findings
- **huggingface/transformers**: **0/100 blocked** — 115 findings, 1 critical
- **langchain-ai/langchain**: **0/100 blocked** — 138 findings (all medium, code_safety: 0)
- **crewAIInc/crewAI**: **100/100 verified** — only 4 findings
- **microsoft/autogen**: **97/100 verified** — clean, only 3 findings

### Full Results Table

| Repo | Score | Tier | Findings | Critical | Categories |
|------|-------|------|----------|----------|------------|
| modelcontextprotocol/servers | 0 | blocked | 131 | 0 | fs:115, exec:16 |
| mark3labs/mcp-go | 100 | verified | 9 | 1 | exec:6, fs:2, exfil:1 |
| punkpeye/awesome-mcp-servers | 79 | standard | 2 | 0 | fs:2 |
| wong2/awesome-mcp-servers | 90 | trusted | 0 | 0 | clean |
| appcypher/awesome-mcp-servers | 85 | trusted | 0 | 0 | clean |
| modelcontextprotocol/python-sdk | 100 | verified | 5 | 0 | exec:5 |
| modelcontextprotocol/typescript-sdk | 0 | blocked | 201 | 0 | exec:80, fs:121 |
| anthropics/claude-cookbooks | 0 | blocked | 57 | 1 | exec:30, fs:18, secret:2, exfil:7 |
| langchain-ai/langchain | 0 | blocked | 138 | 0 | exec:138 |
| crewAIInc/crewAI | 100 | verified | 4 | 0 | fs:3, exec:1 |
| microsoft/autogen | 97 | verified | 3 | 0 | fs:3 |
| run-llama/llama_index | 93 | trusted | 17 | 0 | exec:12, fs:5 |
| openai/openai-python | 0 | blocked | 78 | 0 | exec:75, fs:3 |
| huggingface/transformers | 0 | blocked | 115 | 1 | exec:87, fs:20, exfil:3, secret:2 |
| pydantic/pydantic-ai | 0 | blocked | 67 | 1 | exec:55, fs:10, exfil:1 |
| getzep/zep | 37 | minimal | 29 | 4 | exec:4, fs:21, exfil:4 |
| mem0ai/mem0 | 0 | blocked | 104 | 0 | exec:60, fs:40, secret:2 |
| agno-agi/agno | 100 | verified | 4 | 0 | exec:3, fs:1 |
| BerriAI/litellm | 23 | restricted | 25 | 2 | exec:12, fs:8, exfil:3, secret:2 |

### Tier Distribution
- Verified (90+): 5 repos (29%)
- Trusted (80-89): 3 repos (18%)
- Standard (60-79): 1 repo (6%)
- Minimal (30-59): 1 repo (6%)
- Restricted (1-29): 1 repo (6%)
- Blocked (0): 8 repos (47%)
