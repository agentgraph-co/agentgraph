# Agent Tool Supply-Chain Security: Prevalence from 35,689 Scans

*A prevalence study of the tools, servers, and packages AI agents connect to.
Published by [AgentGraph](https://agentgraph.co). Last updated 2026-06.*

## Why this exists

Most agent-security discussion is qualitative ("MCP servers can be unsafe"). This is
**prevalence data**: what an automated static analysis of **35,689 real agent-ecosystem
endpoints** actually found. The tools an agent connects to — MCP servers, skills, packages —
are the surface that inherits *their* vulnerabilities into the agent, and that surface is
measurable.

It is offered as empirical input for practitioners and standards work (e.g. the OWASP Agentic
Security Initiative), not as a product claim.

## Corpus

| Surface | Scanned | Critical | High |
|---|---:|---:|---:|
| MCP servers | 7,029 | 69 | 567 |
| OpenClaw skills | 2,011 | 21 | 128 |
| npm agent packages | 324 | 7 | 36 |
| PyPI agent packages | 23 | 3 | 5 |
| x402 payment endpoints | 26,302 | 0 | 0 |
| **Total** | **35,689** | **100** | **736** |

9,387 of these are full source-repository scans; the remainder are endpoint/package-manifest
scans.

## Headline findings

- **MCP servers are the densest risk surface:** 7,029 scanned → **636 high-or-critical (9.0%)**.
  Nearly 1 in 11 ships a high/critical issue detectable by static analysis alone.
- **OpenClaw skills:** 2,011 scanned → **149 high-or-critical (7.4%)**.
- **npm agent packages:** 324 scanned → **43 high-or-critical (13.3%)** — small-n, but the
  highest rate in the corpus.
- **x402 payment endpoints (26,302):** 0 static critical/high — expected, because that risk is
  behavioral/authorization at pay-time, not in static code. That is itself a finding: the payment
  surface needs a *verify-then-pay* gate, not a code scan.

## Method (and its limits)

Static + dependency analysis: hardcoded secrets, unsafe `exec`/`eval` and command-injection
sinks, missing/absent authentication boundaries, and known-vulnerable dependencies (CVE
matching). Severity on a critical/high/medium scale.

**This is static analysis only. It does not cover runtime or behavioral risk** (prompt
injection, tool-poisoning at invocation, goal manipulation). The figures are a floor — the
statically-detectable subset — not a complete risk picture.

## Mapping to the OWASP Agentic taxonomy (Threats & Mitigations)

- **ASI04 — Agentic Supply Chain:** dependency CVEs, malicious-package patterns, unsafe code in
  MCP servers / skills. The bulk of the 736 highs.
- **ASI05 — Unexpected Code Execution (RCE):** the unsafe `exec`/`eval` findings.
- **ASI03 — Identity & Privilege Abuse:** missing-auth / over-broad-permission findings on MCP
  servers and skills (no auth boundary on the tool's own surface).
- **ASI02 — Tool Misuse:** insecure tool surfaces generally; secrets exposure supports this.

## From scan result to *verifiable* evidence

A scan result you have to trust the scanner for is a "trust-me" flag. AgentGraph emits each
verdict as a **signed, offline-verifiable attestation** (Ed25519/JWS, RFC 8785 canonicalization,
content-addressed) so a *relying party* — a downstream gate, another agent, an auditor — can
confirm "this tool was scanned, here's the verdict" **without trusting the scanner operator's
infrastructure**. This is the *provenance-verification* layer that supply-chain trust requires:
the verdict is independently reproducible against a published JWKS.

The attestation format and conformance vectors are cross-validated across independent
implementations; see the [conformance sets](../conformance/) and the public scan catalog at
[agentgraph.co/scans](https://agentgraph.co/scans).

## Reproduce / verify

- Public scan catalog: **agentgraph.co/scans**
- Scan any endpoint yourself: **agentgraph.co/check**
- Attestation verification + conformance vectors: this repository's `docs/conformance/`

*Questions, corrections, or data requests: open an issue on
[agentgraph-co/agentgraph](https://github.com/agentgraph-co/agentgraph) or contact the team via
[agentgraph.co](https://agentgraph.co).*
