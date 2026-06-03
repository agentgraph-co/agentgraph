# AgentGraph Trust Scan — GitHub Action

[![AgentGraph](https://img.shields.io/badge/AgentGraph-trust%20scan-7c3aed)](https://agentgraph.co)

Scan your MCP server or agent-tool repository for security and trust posture on
every pull request and push — for **free**, with **no secret to configure**.

This composite action calls AgentGraph's public scan API, derives a letter
grade (A+→F) from the trust score, posts a single sticky comment on the PR with
the grade and findings, sets step outputs you can branch on, and can optionally
fail the build when the score drops below a threshold you choose.

> Scanning uses the **unauthenticated public API** — you never need an AgentGraph
> API key or any repository secret. The only token used is the automatically
> provided `${{ github.token }}`, and only to post the PR comment.

## What it does

1. `GET https://agentgraph.co/api/v1/public/scan/{owner}/{repo}` (cached/fast).
2. Parses `trust_score`, `scan_result`, and `findings` (critical / high / medium / total).
3. Derives a letter grade: **A+** ≥96, **A** ≥81, **B** ≥61, **C** ≥41, **D** ≥21, else **F**.
4. Sets outputs (`trust-score`, `grade`, `scan-result`, `badge-url`, `report-url`).
5. On pull requests, posts/updates one sticky comment with the grade, findings,
   a link to the full report, and the README badge snippet.
6. If `fail-below` > 0 and the score is below it, fails the build.

## Usage

```yaml
name: AgentGraph Trust Scan
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write   # required to post the PR comment

jobs:
  trust-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: agentgraph-co/agentgraph/sdk/trust-scan-action@main
        with:
          fail-below: 41   # optional: fail if below a C grade
```

Copy `examples/trust-scan.yml` into `.github/workflows/` for a ready-to-run file.

## Inputs

| Input           | Required | Default                          | Description                                                                 |
|-----------------|----------|----------------------------------|-----------------------------------------------------------------------------|
| `repo`          | no       | `${{ github.repository }}`       | `owner/repo` to scan.                                                        |
| `api-url`       | no       | `https://agentgraph.co/api/v1`   | AgentGraph API base URL.                                                     |
| `fail-below`    | no       | `0`                              | Fail the build if the score is below this (0-100). `0` = never fail.        |
| `comment-on-pr` | no       | `true`                           | Post/update a sticky trust-grade comment on pull requests.                  |
| `github-token`  | no       | `${{ github.token }}`            | Token used only to post the PR comment (auto-provided; no AgentGraph key).  |

## Outputs

| Output        | Description                                                  |
|---------------|--------------------------------------------------------------|
| `trust-score` | Trust score 0-100 (security scan score).                     |
| `grade`       | Letter grade derived from the score (`A+`, `A`, `B`, `C`, `D`, `F`). |
| `scan-result` | Scan result string (e.g. `clean`, `warnings`, `flagged`).    |
| `badge-url`   | URL of the embeddable SVG trust badge.                       |
| `report-url`  | URL of the human-readable trust report (`/check` page).      |

### Using outputs

```yaml
      - id: scan
        uses: agentgraph-co/agentgraph/sdk/trust-scan-action@main
      - run: echo "Graded ${{ steps.scan.outputs.grade }} (${{ steps.scan.outputs.trust-score }}/100)"
```

## Badge

Add the live trust badge to your README (it links to the full report):

```markdown
[![AgentGraph Trust](https://agentgraph.co/api/v1/public/scan/OWNER/REPO/badge)](https://agentgraph.co/check/OWNER/REPO)
```

Replace `OWNER/REPO` with your repository. The action also prints this exact
snippet (pre-filled) in its PR comment and job summary.

## Permissions

The action needs `pull-requests: write` to post the sticky comment. If you set
`comment-on-pr: false`, only `contents: read` is required. No AgentGraph secret
is ever needed — scanning is free and uses the public API.

## Learn more

- Full report for any repo: `https://agentgraph.co/check/{owner}/{repo}`
- AgentGraph: trust infrastructure for AI agents — https://agentgraph.co
