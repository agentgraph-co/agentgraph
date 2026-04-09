# MCP Registry Submissions — Step by Step

There are 4 separate registries. Each is independent. Do them in this order because awesome-mcp-servers requires Glama first.

---

## 1. Glama.ai (REQUIRED for awesome-mcp-servers PR)

**Time:** ~5 min | **URL:** https://glama.ai/mcp/servers

1. Go to https://glama.ai/mcp/servers
2. Click **"Submit Server"** (top right)
3. Enter GitHub URL: `https://github.com/agentgraph-co/agentgraph`
   - If it asks for subdirectory: `sdk/mcp-server`
4. It will run automated checks (starts server, sends introspection requests)
5. **If it asks for a Dockerfile:** Add one to `sdk/mcp-server/Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim
   RUN pip install agentgraph-trust
   ENTRYPOINT ["agentgraph-trust"]
   ```
6. Wait for checks to pass
7. Once listed, your Glama path will be: `agentgraph-co/agentgraph` (or similar)
8. Copy the badge URL — you need it for the next step

**Your Glama badge format:**
```
[![agentgraph-co/agentgraph MCP server](https://glama.ai/mcp/servers/agentgraph-co/agentgraph/badges/score.svg)](https://glama.ai/mcp/servers/agentgraph-co/agentgraph)
```

---

## 2. awesome-mcp-servers PR Update (PR #4326)

**Time:** ~2 min | **URL:** https://github.com/punkpeye/awesome-mcp-servers/pull/4326

The bot requires a Glama badge. After completing step 1:

1. Go to: https://github.com/kenneives/awesome-mcp-servers/blob/add-agentgraph-trust/README.md
2. Click the pencil icon to edit
3. Find the agentgraph-trust line and update it to include the badge:

**Current line:**
```
- [agentgraph-co/agentgraph-trust](https://github.com/agentgraph-co/agentgraph) 🐍 ☁️ 🍎 🪟 🐧 - Trust verification and security scanning for AI agents. Checks security posture of third-party MCP servers and tools with signed attestations (Ed25519/JWS) before interaction.
```

**Updated line (add badge after the link):**
```
- [agentgraph-co/agentgraph-trust](https://github.com/agentgraph-co/agentgraph) [![agentgraph-co/agentgraph MCP server](https://glama.ai/mcp/servers/agentgraph-co/agentgraph/badges/score.svg)](https://glama.ai/mcp/servers/agentgraph-co/agentgraph) 🐍 ☁️ 🍎 🪟 🐧 - Trust verification and security scanning for AI agents. Checks security posture of third-party MCP servers and tools with signed attestations (Ed25519/JWS) before interaction.
```

4. Commit directly to the `add-agentgraph-trust` branch
5. The PR will auto-update. Reply to the bot: "Updated with Glama badge — server passes all checks."

---

## 3. Official MCP Registry (modelcontextprotocol.io)

**Time:** ~5 min | **Requires:** npm/npx

This is the registry that Claude Code and Claude Desktop use to discover MCP servers.

1. Open terminal in the `sdk/mcp-server/` directory:
   ```bash
   cd sdk/mcp-server
   ```

2. Run the publisher:
   ```bash
   npx @anthropic-ai/mcp-publisher@latest publish
   ```

3. It will:
   - Read `server.json` (already created)
   - Verify the PyPI package `agentgraph-trust` exists (it does, v0.2.1)
   - Check for the `<!-- mcp-name: io.github.agentgraph-co/agentgraph-trust -->` tag in README.md (already added)
   - Ask you to authenticate with GitHub (proves ownership of agentgraph-co org)

4. After approval, the server appears at:
   `https://modelcontextprotocol.io/servers/io.github.agentgraph-co/agentgraph-trust`

**If mcp-publisher fails or doesn't exist yet:** The official registry may still be accepting manual submissions. Check https://github.com/modelcontextprotocol/registry for alternative instructions.

---

## 4. mcp.so (Community Directory)

**Time:** 30 seconds | **URL:** https://mcp.so

1. Go to https://mcp.so
2. Click **"Submit"** or **"Add Server"**
3. Fill in:
   - **Name:** `agentgraph-trust`
   - **Description:** Trust verification and security scanning for AI agents. Check security posture, verify trust scores, and get signed attestations (Ed25519/JWS) before interacting with third-party tools.
   - **GitHub URL:** `https://github.com/agentgraph-co/agentgraph/tree/main/sdk/mcp-server`
   - **PyPI:** `agentgraph-trust`
   - **Install command:** `pip install agentgraph-trust`
   - **Category:** Security
4. Submit — they review and list within 24-48 hours

---

## 5. Smithery.ai (Optional)

**URL:** https://smithery.ai

1. Go to https://smithery.ai
2. Click "Add Server"
3. Connect GitHub account
4. Select the agentgraph repo, point to `sdk/mcp-server/`
5. It auto-detects the MCP server configuration

---

## Verification Checklist

After all submissions:

- [ ] Glama.ai — server listed, badge working
- [ ] awesome-mcp-servers — PR updated with badge, waiting for merge
- [ ] Official MCP registry — published via mcp-publisher
- [ ] mcp.so — submitted, waiting for review
- [ ] Smithery — submitted (optional)

---

## HN Post (Tuesday April 7, 9-10am ET)

**Title:** `Show HN: We scanned 25 OpenClaw skills – 1,195 security findings, avg trust score 51/100`

**URL:** Link to the Dev.to article (currently: https://dev.to/agentgraph/methodology-18ki — update if title/slug changes)

**If doing a text post instead, use this intro (keep it short for HN):**

> We built an open-source security scanner for AI agent tools and ran it against 25 popular OpenClaw skills. Results: 1,195 findings across the board. OpenClaw's own skill registry and their security plugin both scored 0/100. The scanner is available as an MCP tool (pip install agentgraph-trust) and as a free public API with trust-tiered rate limiting. All results are cryptographically signed (Ed25519/JWS).

**Timing:** Post Tuesday April 7 between 9-10am ET (6-7am PST). Power outage on Mon night through 4pm PST Tue — post after power is back. Tuesday morning is still excellent for HN.

**Tips:**
- Don't editorialize the title — let the data speak
- Be ready to answer questions in comments within the first hour (critical for ranking)
- If asked about methodology, link to the scanner source code
- Don't be defensive about OpenClaw — present data neutrally
- Mention the free public API and trust gateway — that's the hook for framework authors
