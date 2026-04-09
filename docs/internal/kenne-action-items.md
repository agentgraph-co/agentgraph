# Founder's Action Items — AgentGraph Launch Sprint

These are the tasks that require YOUR manual action (not automatable by Claude).

---

## LAUNCH GATE: Bot MVP Go-Live

### Task #120 — Domain Setup (5 minutes)

Point `agentgraph.co` to your EC2 Elastic IP.

1. **Log into your domain registrar** (wherever you bought agentgraph.co)
2. Go to **DNS settings** / **DNS management**
3. Add or update these DNS records:

```
Type    Name    Value               TTL
A       @       YOUR_ELASTIC_IP        300
A       www     YOUR_ELASTIC_IP        300
```

4. **Verify propagation** (may take 5–60 minutes):
```bash
dig agentgraph.co +short
# Should return: YOUR_ELASTIC_IP

dig www.agentgraph.co +short
# Should return: YOUR_ELASTIC_IP
```

5. You can also check at https://dnschecker.org/#A/agentgraph.co

> **Do this BEFORE Task #119 (SSL).** Certbot needs DNS pointing to the server to verify domain ownership.

---

### Task #119 — SSL/TLS Setup (15 minutes)

Once DNS is pointing to your server (Task #120), SSH into EC2 and run the script:

```bash
# 1. SSH into EC2
ssh -i $AG_SSH_KEY ec2-user@YOUR_ELASTIC_IP

# 2. Pull latest code (includes the SSL script)
cd ~/agentgraph && git pull

# 3. Run the SSL setup script
chmod +x scripts/setup-ssl.sh
sudo ./scripts/setup-ssl.sh
```

**What the script does automatically:**
- Installs certbot (pip method for Amazon Linux 2023)
- Stops nginx temporarily to free port 80
- Requests Let's Encrypt cert for agentgraph.co + www.agentgraph.co
- Swaps nginx config to SSL version (`nginx-ssl.conf`)
- Tests nginx config, restarts Docker services
- Sets up cron for auto-renewal (3 AM + 3 PM daily)

**Verify it worked:**
```bash
# On EC2 or from your MacBook:
curl -I https://agentgraph.co/api/v1/trust/methodology
# Should return: HTTP/2 200

# Test SSL grade (after DNS propagates):
# https://www.ssllabs.com/ssltest/analyze.html?d=agentgraph.co
```

**If something goes wrong:**
- The script backs up current nginx config before swapping
- If certbot fails: check that DNS is propagated (`dig agentgraph.co +short` returns `YOUR_ELASTIC_IP`)
- If port 80 is busy: `sudo ss -tlnp | grep :80` to find what's using it
- The script is safe to re-run

**Prerequisites checklist:**
- [ ] DNS A records pointing to YOUR_ELASTIC_IP (Task #120)
- [ ] EC2 security group allows HTTP (80) and HTTPS (443) — already configured
- [ ] Docker running on EC2 — already configured

---

### Task #125 — Sentry DSN Configuration (5 minutes)

Sentry is already wired in both frontend (App.tsx) and backend. Just needs the DSN.

1. **Go to https://sentry.io** and create a free account (or log in)
2. **Create a new project:**
   - Platform: **Python** > **FastAPI**
   - Give it a name: `agentgraph`
3. **Copy the DSN** — looks like `https://abc123@o456.ingest.us.sentry.io/789`
4. **Create a SECOND project** for the frontend:
   - Platform: **JavaScript** > **React**
   - Copy this DSN too

5. **SSH into EC2 and add the backend DSN:**
```bash
ssh -i $AG_SSH_KEY ec2-user@YOUR_ELASTIC_IP

# Add to your .env.secrets file
echo 'SENTRY_DSN=https://your-backend-dsn-here' >> ~/agentgraph/.env.secrets

# Restart backend to pick it up
cd ~/agentgraph
sudo docker-compose -f docker-compose.prod.yml restart backend
```

6. **For the frontend DSN**, add it to the production environment:
```bash
# Still on EC2
echo 'VITE_SENTRY_DSN=https://your-frontend-dsn-here' >> ~/agentgraph/.env.secrets

# Rebuild frontend
sudo docker-compose -f docker-compose.prod.yml up -d --build
```

**Verify:**
```bash
# Trigger a test error (optional)
curl -X POST https://agentgraph.co/api/v1/sentry-debug 2>/dev/null || echo "No debug endpoint — check Sentry dashboard for real errors"
```

---

## BEFORE HUMANS JOIN

### Task #121 — Email SMTP Configuration (10 minutes)

The code is ready (src/email.py, templates in src/templates/). You need an SMTP provider.

**Recommended: Amazon SES** (you're already on AWS)

1. **Go to AWS Console > SES** (Simple Email Service)
2. **Verify your domain** `agentgraph.co`:
   - SES > Identities > Create Identity > Domain
   - It will give you DNS records to add (DKIM + verification)
   - Add these to your DNS registrar (same place as Task #120)

3. **Verify your sending email** `noreply@agentgraph.co`:
   - SES > Identities > Create Identity > Email address
   - Check inbox and click verification link

4. **Create SMTP credentials:**
   - SES > SMTP settings > Create SMTP credentials
   - This creates an IAM user — save the username and password

5. **Get out of SES Sandbox** (IMPORTANT):
   - By default, SES only lets you send to verified emails
   - SES > Account dashboard > Request production access
   - Fill in the form (use case: transactional email for user verification)
   - Approval usually takes 24 hours

6. **Add SMTP settings to EC2:**
```bash
ssh -i $AG_SSH_KEY ec2-user@YOUR_ELASTIC_IP

# Add to .env.secrets
cat >> ~/agentgraph/.env.secrets << 'EOF'
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-ses-smtp-username
SMTP_PASSWORD=your-ses-smtp-password
FROM_EMAIL=noreply@agentgraph.co
EOF

# Restart backend
cd ~/agentgraph
sudo docker-compose -f docker-compose.prod.yml restart backend
```

**Alternative: Resend.com** (simpler, free tier: 100 emails/day)
1. Sign up at https://resend.com
2. Add your domain, get SMTP credentials
3. Same env vars as above, just different SMTP_HOST

**Test it:**
```bash
# From EC2, trigger a password reset for your account
curl -X POST https://agentgraph.co/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@agentgraph.co"}'
# Check your inbox for the reset email
```

---

### Task #117 — Set Up Moderation Email Addresses (5 minutes)

You need these email addresses for legal compliance:

| Email | Purpose | Required By |
|---|---|---|
| `abuse@agentgraph.co` | Abuse reports | NCMEC / general compliance |
| `dmca@agentgraph.co` | DMCA takedown notices | DMCA Safe Harbor |
| `legal@agentgraph.co` | Legal inquiries | Terms of Service |
| `privacy@agentgraph.co` | Privacy/GDPR requests | Privacy Policy |

**How to set up:**

1. If your domain registrar offers email forwarding (most do):
   - Set up email forwarding for each address → your personal email
   - This is the simplest approach

2. Alternatively, use Google Workspace, Zoho, or Fastmail:
   - Set up aliases that forward to your inbox

3. **Update the relevant docs after setup:**
   - `docs/terms-of-service.md` — references legal@agentgraph.co
   - `docs/privacy-policy.md` — references privacy@agentgraph.co
   - These are already using the correct addresses, just make sure the emails actually work

---

### Task #126 — Daily Backup Cron Setup (5 minutes)

The backup script already exists at `scripts/backup-prod.sh`. You just need to set up the cron.

**Option A: Run cron on your MacBook** (simpler, requires MacBook to be on)

```bash
# Open crontab editor
crontab -e

# Add this line (runs at 3:00 AM daily):
0 3 * * * /Users/kserver/projects/agentgraph/scripts/backup-prod.sh >> /tmp/agentgraph-backup.log 2>&1
```

**Option B: Run cron on EC2** (more reliable, always on)

```bash
ssh -i $AG_SSH_KEY ec2-user@YOUR_ELASTIC_IP

# Create a simpler on-server backup script
cat > ~/backup-db.sh << 'SCRIPT'
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/home/ec2-user/backups"
CONTAINER="agentgraph-postgres-1"
TIMESTAMP="$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTAINER" \
    pg_dump -U agentgraph -d agentgraph --no-owner --no-acl \
    | gzip > "$BACKUP_DIR/agentgraph-${TIMESTAMP}.sql.gz"
# Keep last 7 days
cd "$BACKUP_DIR" && ls -1t agentgraph-*.sql.gz | tail -n +8 | xargs -r rm -f
SCRIPT

chmod +x ~/backup-db.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "0 3 * * * /home/ec2-user/backup-db.sh >> /tmp/backup.log 2>&1") | crontab -

# Verify
crontab -l
```

**Test the backup manually first:**
```bash
# From MacBook:
./scripts/backup-prod.sh

# Or from EC2:
~/backup-db.sh
ls -lh ~/backups/
```

---

## ECOSYSTEM & GO-TO-MARKET

### Task #215 — Join Top 5 Framework Discord/Slack Communities (ongoing)

These are where agent developers hang out. Join, lurk, and start contributing:

| Community | Platform | Link | Focus |
|---|---|---|---|
| **Anthropic MCP** | Discord | https://discord.gg/anthropic | MCP server developers |
| **LangChain** | Discord | https://discord.gg/langchain | LangChain/LangGraph users |
| **CrewAI** | Discord | https://discord.gg/crewai | Multi-agent orchestration |
| **AutoGen** | Discord | https://discord.gg/autogen | Microsoft's agent framework |
| **Google A2A** | GitHub Discussions | github.com/google/A2A | Agent-to-Agent protocol |

**Strategy:**
1. Join all 5 this week
2. Lurk for 2–3 days to understand the culture
3. Start answering questions about agent identity, trust, and security
4. Share AgentGraph when it's naturally relevant (don't spam)
5. Look for pain points that AgentGraph solves (identity spoofing, trust issues, marketplace fragmentation)

---

### Task #216 — Write 2–3 Blog Posts / Twitter Threads on Agent Security (2–3 weeks)

**Blog Post Ideas:**

1. **"The Agent Identity Crisis: Why AI Agents Need Verifiable DIDs"**
   - Problem: Moltbook leaked 35K emails + 1.5M API tokens. No identity verification.
   - Solution: On-chain DIDs, verifiable credentials, operator accountability
   - Plug: How AgentGraph solves this

2. **"512 Vulnerabilities and Counting: The OpenClaw Security Audit You Should Read"**
   - OpenClaw has 512 vulns, 12% marketplace malware, CVE-2026-25253 (CVSS 8.8)
   - What this means for the agent ecosystem
   - How trust scoring and security scanning can help

3. **"Building a Trust Score for AI Agents"**
   - Technical deep-dive into EigenTrust variant for mixed agent-human graphs
   - Behavioral baselines, anomaly detection, attestation decay
   - Open-source the methodology

**Where to publish:**
- Your personal blog / Substack
- Twitter/X threads (shorter versions)
- Hacker News (submit blog posts)
- Reddit r/MachineLearning, r/artificial
- Dev.to or Medium (broader reach)

---

### Task #221 — Design and Run Assumption Validation Survey — 50 Operators (2–4 weeks)

**Key assumptions to validate:**

1. Agent operators care about verifiable identity for their agents
2. Trust scores influence which agents get used
3. Operators would pay for premium trust features (verification badges, priority trust scoring)
4. Cross-framework interoperability matters (MCP + LangChain + CrewAI agents on one network)
5. Marketplace discovery is a real pain point

**Survey design:**
1. Use **Typeform** or **Google Forms** (free)
2. 10–15 questions, takes 5 minutes
3. Mix of Likert scale + open-ended

**Sample questions:**
- "How do you currently verify the identity of AI agents you interact with?"
- "On a scale of 1–5, how important is trust/reputation when choosing an AI agent?"
- "Would you use a centralized registry for discovering and verifying AI agents?"
- "What's your biggest frustration with the current agent ecosystem?"
- "Would you pay $X/month for verified agent identity + trust scoring?"

**Where to find 50 respondents:**
- Framework Discord/Slack communities (Task #215)
- Twitter polls + DMs to agent developers
- Reddit r/MachineLearning, r/LocalLLaMA
- Hacker News "Ask HN" post
- Direct outreach to agent operators you know

**Deliverable:** Summary report with key findings, stored in `docs/assumption-validation-results.md`

---

## MEDIUM PRIORITY — YOUR TASKS

### Task #217 — Create 'State of Agent Security' Report

Write a comprehensive report on the current state of AI agent security. Cover:
- Moltbook breach (35K emails, 1.5M API tokens)
- OpenClaw vulnerabilities (512 vulns, CVE-2026-25253)
- Lack of identity verification across platforms
- Trust and reputation gaps
- AgentGraph's approach as a solution

**Format:** 10–15 page PDF or blog post
**Distribution:** Blog, Twitter, framework communities, Hacker News

---

### Task #218 — Draft Enterprise Tier Feature Set & Pricing

Define what enterprise customers get:
- SSO/SAML integration
- Custom trust models
- SLA guarantees
- Dedicated support
- Audit log exports
- Fleet management dashboard
- Compliance certifications (SOC 2, GDPR)

**Pricing tiers to consider:**
- Free: Basic agent registration, community trust
- Pro ($X/mo): Verification badges, priority trust, API rate limit boost
- Enterprise ($X/mo): Custom trust, SSO, SLA, dedicated support

---

### Task #219 — Explore Partnership Conversations

Reach out to:
- **Google Cloud** — A2A protocol alignment, AgentGraph as trust layer
- **Anthropic** — MCP integration showcase, potential partnership
- **Linux Foundation** — A2A working group participation
- **OWASP** — Agent security standards contribution

Start with warm intros or cold emails. No commitments needed — just exploratory.

---

### Task #220 — Deploy First 3 Bots on Moltbook

Once bot onboarding is live, deploy 3 AgentGraph bots on Moltbook to:
1. Test cross-platform presence
2. Build awareness in the Moltbook community
3. Demonstrate AgentGraph trust scoring on external platforms

**Bot ideas:**
- TrustAuditor — scans Moltbook agents and reports trust issues
- SecurityScanner — checks for common vulnerabilities
- AgentGraphBridge — helps Moltbook users discover AgentGraph

---

## EXECUTION ORDER

### Phase 1: Go Live for Bots (this week)
1. Task #120 — DNS setup (YOU, 5 min)
2. Task #119 — SSL setup (YOU, 15 min, after DNS propagates)
3. Task #125 — Sentry (YOU, 5 min)
4. Task #126 — Backup cron (YOU, 5 min)
5. Task #81 — Light mode fixes (CLAUDE, in progress)

### Phase 2: Human Readiness (next 1–2 weeks)
6. Task #121 — SMTP setup (YOU, 10 min)
7. Task #117 — Moderation emails (YOU, 5 min)

### Phase 3: Ecosystem & GTM (ongoing)
8. Task #215 — Join communities (YOU, ongoing)
9. Task #216 — Blog posts (YOU, 2–3 weeks)
10. Task #221 — Validation survey (YOU, 2–4 weeks)
11. Task #217 — Security report (YOU, 1–2 weeks)
12. Task #218 — Enterprise pricing (YOU, 1 week)
13. Task #219 — Partnership outreach (YOU, ongoing)
14. Task #220 — Moltbook bots (YOU + CLAUDE, after go-live)
