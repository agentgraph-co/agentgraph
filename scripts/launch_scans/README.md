# Launch Scans — May 12 "State of Agent Security Q2 2026"

Four scan scripts that feed the launch litepaper. All are **dry-run by default** —
they discover targets and write a target list to `data/launch-scans/<name>-targets.json`
without hitting any scanning endpoint.

**Run mode must be explicit.** Pass `--run` to actually execute scans. This is
deliberate: we want to review the target list before burning rate-limit budget.

## Scripts

| Script | Ecosystem | Rate-limit surface | Discover endpoint |
|--------|-----------|---------------------|-------------------|
| `scan_x402.py` | x402 Bazaar | bazaar.x402.org + per-endpoint | `GET /bazaar/listings` |
| `scan_mcp_registry.py` | MCP Registry | registry.modelcontextprotocol.io | `GET /servers` |
| `scan_npm_agents.py` | npm | registry.npmjs.org (5000/hr) | `GET /-/v1/search?text=agent+framework` |
| `scan_pypi_agents.py` | PyPI | pypi.org (no hard limit, be polite) | `GET /search?q=agent` |

## Output Structure

Every script writes:

- `data/launch-scans/<name>-targets.json` — discovered target list (dry-run or run)
- `data/launch-scans/<name>-progress.json` — incremental scan state (resumable)
- `data/launch-scans/<name>-results.json` — full scan output (only in `--run` mode)

## Review Checklist (Tomorrow AM)

Before passing `--run` to any script, confirm:

1. `targets.json` count is reasonable (not 50,000 packages)
2. Rate-limit pacing in each script matches the ecosystem's posted limits
3. Discovery filters out obvious non-agent-framework noise
4. Auth envs (`GITHUB_TOKEN`, etc.) are loaded from `.env.secrets`, not hardcoded

## Timing

- **Mon 04-21 late:** Discovery (`python3 scripts/launch-scans/scan_*.py`)
- **Tue 04-22 AM:** Review each targets.json
- **Tue 04-22 day/night:** Actual scans (`--run`), nohup'd to survive disconnect
- **Wed 04-23 AM:** Data ready for litepaper tables + /state-of-agent-security-2026 page

## Why Not in scripts/scan_openclaw_batch.py style?

Those scripts were launch-day emergency tooling. These are four parallel, independently
pausable workstreams. Splitting them means we can kill one ecosystem without losing progress
on the others.
