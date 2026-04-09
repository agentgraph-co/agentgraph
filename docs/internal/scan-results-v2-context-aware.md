# Batch Scan Results v2 — Context-Aware MCP Scanner
## April 8, 2026

### Before/After Comparison (key repos)
| Repo | Before (v1) | After (v2) | MCP? | Change |
|------|-------------|------------|------|--------|
| modelcontextprotocol/servers | 0 blocked | 72 standard | YES | +72 |
| langchain-ai/langchain | 0 blocked | 79 standard | YES | +79 |
| huggingface/transformers | 0 blocked | 70 standard | NO | +70 |
| modelcontextprotocol/typescript-sdk | 0 blocked | 28 restricted | YES | +28 |
| openai/openai-python | 0 blocked | 0 blocked | NO | 0 |
| crewAI | 100 verified | 100 verified | YES | 0 |
| microsoft/autogen | 100 verified | 100 verified | YES | 0 |

### Aggregate Stats (12 valid scans)
- Average score: 75.2 (was 47.3)
- MCP detected: 7/12 (58%)
- Verified: 4 (33%) — crewAI, autogen, python-sdk, mcp-go
- Standard: 4 (33%) — servers, langchain, transformers, awesome-mcp
- Trusted: 2 (16%) — wong2/awesome, appcypher/awesome
- Restricted: 1 (8%) — typescript-sdk
- Blocked: 1 (8%) — openai-python
- Critical findings: 2/12 (16%)

### HN Framing
"We built a context-aware security scanner for AI agent tools. MCP servers 
get scored differently than regular libraries — filesystem access is expected 
in a tool server but concerning in a library. Average score: 75/100 across 
12 popular repos. Try it: curl agentgraph.co/api/v1/public/scan/owner/repo"
