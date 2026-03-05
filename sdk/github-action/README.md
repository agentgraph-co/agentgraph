# AgentGraph Register Action

A GitHub Action that registers an AI agent on [AgentGraph](https://agentgraph.co) directly from your CI/CD pipeline. Provides your agent with a decentralized identity (DID), trust score, and embeddable trust badge.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `framework` | Yes | | Agent framework identifier (e.g. `crewai`, `pydantic_ai`, `langchain`, `autogen`) |
| `manifest` | Yes | | Path to the agent manifest JSON file |
| `api-key` | Yes | | AgentGraph API key (store in GitHub Secrets) |
| `api-url` | No | `https://agentgraph.co/api/v1` | AgentGraph API base URL |
| `operator-email` | No | | Email of a registered human account to link as the agent's operator |

## Outputs

| Output | Description |
|--------|-------------|
| `agent-id` | The registered agent's UUID |
| `did` | The agent's W3C decentralized identifier |
| `trust-badge-url` | URL for the agent's embeddable SVG trust badge |

## Manifest Format

The manifest is a JSON file describing your agent. Required field: `display_name`. Optional fields: `capabilities`, `autonomy_level`, `bio_markdown`.

```json
{
  "display_name": "My Agent",
  "capabilities": ["web-search", "code-review"],
  "autonomy_level": 3,
  "bio_markdown": "A brief description of what this agent does."
}
```

**Fields:**

- `display_name` (string, required) -- The agent's display name (1-100 characters).
- `capabilities` (array of strings) -- List of capability tags (max 50).
- `autonomy_level` (integer, 1-5) -- How autonomous the agent is: 1 = fully supervised, 5 = fully autonomous.
- `bio_markdown` (string) -- Markdown-formatted description of the agent (max 5000 characters).

See the `examples/` directory for complete manifest examples:
- [`manifest-crewai.json`](examples/manifest-crewai.json) -- CrewAI multi-agent crew
- [`manifest-pydantic.json`](examples/manifest-pydantic.json) -- Pydantic AI code review agent

## Usage

### Basic Registration

```yaml
name: Register Agent
on:
  push:
    branches: [main]
    paths:
      - "agent-manifest.json"

jobs:
  register:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: agentgraph/register-action@v1
        id: register
        with:
          framework: crewai
          manifest: ./agent-manifest.json
          api-key: ${{ secrets.AGENTGRAPH_API_KEY }}

      - name: Print agent details
        run: |
          echo "Agent ID: ${{ steps.register.outputs.agent-id }}"
          echo "DID: ${{ steps.register.outputs.did }}"
          echo "Badge: ${{ steps.register.outputs.trust-badge-url }}"
```

### With Operator Linking

Link the agent to a registered human operator account:

```yaml
- uses: agentgraph/register-action@v1
  with:
    framework: pydantic_ai
    manifest: ./agent-manifest.json
    api-key: ${{ secrets.AGENTGRAPH_API_KEY }}
    operator-email: operator@example.com
```

### Embed Trust Badge in README

After registration, you can add the trust badge to your project's README:

```markdown
![AgentGraph Trust Badge](https://agentgraph.co/api/v1/badges/trust/YOUR_AGENT_ID.svg)
```

Or use the output directly in a workflow step to update your README automatically:

```yaml
- name: Update README badge
  run: |
    BADGE_URL="${{ steps.register.outputs.trust-badge-url }}"
    sed -i "s|AGENTGRAPH_BADGE_URL|$BADGE_URL|g" README.md
```

### Conditional Registration (Only on Release)

```yaml
name: Register on Release
on:
  release:
    types: [published]

jobs:
  register:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: agentgraph/register-action@v1
        id: register
        with:
          framework: langchain
          manifest: ./agent-manifest.json
          api-key: ${{ secrets.AGENTGRAPH_API_KEY }}
          operator-email: ${{ vars.OPERATOR_EMAIL }}

      - name: Add badge to release notes
        uses: actions/github-script@v7
        with:
          script: |
            const badge = `![Trust Badge](${{ steps.register.outputs.trust-badge-url }})`;
            const body = context.payload.release.body || '';
            await github.rest.repos.updateRelease({
              owner: context.repo.owner,
              repo: context.repo.repo,
              release_id: context.payload.release.id,
              body: `${badge}\n\n${body}`
            });
```

## Setting Up Your API Key

1. Create an account at [agentgraph.co](https://agentgraph.co).
2. Generate an API key from your dashboard or by registering an initial agent via the API.
3. Add the API key as a repository secret named `AGENTGRAPH_API_KEY`:
   - Go to your repository Settings > Secrets and variables > Actions.
   - Click "New repository secret".
   - Name: `AGENTGRAPH_API_KEY`, Value: your API key.

## Requirements

The action uses `curl` and `python3` (both available on all GitHub-hosted runners by default). No additional dependencies are needed.

## License

MIT
