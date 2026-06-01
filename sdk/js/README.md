# @agentgraph/trust

JavaScript/TypeScript SDK for **AgentGraph Trust Score v2** — signed,
self-verifiable trust-score envelopes. This is the JS peer of the Python
`agentgraph-sdk` verify module; both reproduce the server's
JCS-canonical, Ed25519-over-SHA-256 verification **byte-for-byte**.

- Zero crypto deps: uses Node's built-in `node:crypto` for Ed25519.
- One runtime dep: [`canonicalize`](https://www.npmjs.com/package/canonicalize)
  (RFC 8785 JCS — byte-matches Python's `rfc8785`).
- Node >= 18 (uses the global `fetch`).

## Install

```bash
npm install @agentgraph/trust
```

## Trust Score v2 — signed, self-verifiable envelopes

Every v2 trust score is a signed envelope you can verify **without trusting our
server** — fetch it, then check the Ed25519 signature against our published JWKS
yourself.

```js
import { TrustClient } from '@agentgraph/trust';

const client = new TrustClient('https://agentgraph.co');
const did = 'did:web:agentgraph.co:agents:<id>';

// Signed envelope: score + per-source methodology breakdown + proof
const env = await client.getAggregate(did);
console.log(env.trust_score, env.contributions.map((c) => c.source));

// Verify it client-side (fetches JWKS, checks signature + freshness)
const result = await client.verify(did);
if (result.valid) {            // true iff signature valid AND fresh
  console.log('verified:', result.kid);
} else {
  console.log('NOT verified:', result.reason);
}

// Scan any GitHub repo -> grade + findings + a verifiable envelope
const scan = await client.checkRepo('owner', 'repo');
if (scan.trust_envelope) {
  console.log(await client.verifyEnvelope(scan.trust_envelope));
}
```

### Standalone verification (no client)

`verifyEnvelope(envelope, jwks, { now })` only needs `canonicalize` plus
`node:crypto`, reproducing the server's JCS-canonical, Ed25519-over-SHA-256
check byte-for-byte.

```js
import { verifyEnvelope } from '@agentgraph/trust';

const result = verifyEnvelope(envelope, jwks);
// => { valid, signatureValid, fresh, kid, reason }
```

It (1) strips the top-level `proof` key, (2) JCS-canonicalizes the rest,
(3) SHA-256s it, (4) reads `kid` from the detached JWS header, (5) finds the
matching `{ kty: 'OKP', crv: 'Ed25519', x }` key in the JWKS, (6) verifies the
Ed25519 signature over the digest, then (7) checks
`computed_at + freshness_ttl_seconds >= now`. `valid` is
`signatureValid && fresh`.

## API

### `new TrustClient(baseUrl, { apiKey?, token?, timeout? })`

| Method | Description |
|--------|-------------|
| `getAggregate(did)` | Signed v2 envelope for a subject DID |
| `getContributions(did)` | Just the methodology breakdown |
| `checkRepo(owner, repo)` | Scan a GitHub repo -> grade + findings + envelope |
| `getJwks()` | Issuer JWKS from `<baseUrl>/.well-known/jwks.json` |
| `verifyEnvelope(env, { now? })` | Fetch JWKS + verify an envelope client-side |
| `verify(did, { now? })` | `getAggregate` + `verifyEnvelope` in one call |

API base is `<baseUrl>/api/v1`; the JWKS is served outside that prefix.

### `verifyEnvelope(envelope, jwks, { now? })`

Returns `{ valid, signatureValid, fresh, kid, reason }`. `reason` is one of:
`ok`, `missing or unsupported proof`, `malformed jws`,
`no matching key in JWKS`, `signature invalid`, `envelope expired (stale)`.

Also exported: `envelopeDigest(envelope)` (raw 32-byte SHA-256 of the
JCS-canonical, proof-stripped envelope), `isFresh(envelope, { now? })`,
`PROOF_TYPE`.

## Verification / tests

```bash
npm install
npm test          # node --test
```

The test suite validates against **production**: it fetches the real JWKS and a
real signed aggregate from `agentgraph.co` and asserts the JS verifier accepts
it (`valid === true`, `kid === 'trust-v2-2026'`). A passing live check proves
byte-compatible JCS canonicalization + Ed25519 with the Python/server side. If
prod is unreachable it falls back to a pinned fixture captured from prod.

## Spec

[`docs/standards/trust-score-envelope-v2.0.md`](../../docs/standards/trust-score-envelope-v2.0.md)
(§6 verification). MIT licensed.
