# Draft Comment for SEP-1913 (Trust and Sensitivity Annotations)

PR: modelcontextprotocol/modelcontextprotocol#1913

---

This proposal addresses an important gap — MCP needs a way to express trust and sensitivity properties at the protocol level, not just in application code.

One dimension I think is worth considering alongside data-level annotations: **entity-level trust**. The current proposal lets a server annotate its responses with `sensitiveHint` and `maliciousActivityHint`, but these are self-declared. A malicious server would obviously not set `maliciousActivityHint: true` on itself.

The missing layer is independent verification — cryptographically signed attestations from external trust providers that verify the server's identity, code security, and behavioral history. This would complement the annotations in SEP-1913 by answering "who verified this?" alongside "what is this?"

Concrete example: a server declares `sensitiveHint: true` on a response containing PII. An entity-level trust layer would additionally provide:
- A security scan attestation (signed JWS) showing the server's code has been audited
- An identity attestation linking the server to a verified operator
- A behavioral attestation from an interaction history provider

The `attribution` field in this proposal is a good starting point for provenance, but it could be extended to reference signed attestations rather than just string identifiers.

We've built this at AgentGraph — a public scan API that produces EdDSA-signed attestations for any GitHub repo, verifiable against our JWKS. Happy to contribute a reference implementation showing how entity-level trust could integrate with the annotations proposed here.

Would this be better as an extension to this SEP or a separate complementary SEP?
