# GitHub Action Design — INTERNAL

## What It Does
MCP server authors add a `.github/workflows/trust-scan.yml` to their repo.
On every push/PR, it:
1. Calls our public scan API
2. Posts the result as a PR comment (score, grade, category breakdown)
3. Updates a README badge
4. Fails the CI check if score is below a threshold

## Why This Matters
- Every repo that adds the action gets a trust badge in their README
- Every badge links back to AgentGraph
- Organic adoption — they come to us, we don't push
- CI integration means ongoing engagement (every PR gets scanned)

## Implementation
- Simple: just a composite action that calls curl + formats output
- No Docker needed (runs in any GitHub runner)
- No AgentGraph account needed (public scan API, no auth)

## Files to Create
- A new public repo: agentgraph-co/trust-scan-action
- action.yml
- scan.sh (the actual script)
- README.md with setup instructions
