// Live-prod verification test for @agentgraph/trust.
//
// We cannot sign envelopes in JS (no private key), so instead we validate
// AGAINST PRODUCTION: fetch the real JWKS and a real signed aggregate envelope
// from agentgraph.co, and assert the JS verifier accepts it (valid=true,
// kid='trust-v2-2026'). A passing live check PROVES byte-compatible JCS
// canonicalization + Ed25519-over-SHA-256 with the Python/server side.
//
// If prod is unreachable in the sandbox, we fall back to a hardcoded fixture
// captured from prod (which exercises the same JCS+Ed25519 path).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { verifyEnvelope, envelopeDigest, isFresh } from '../index.js';
import { TrustClient } from '../src/client.js';

const BASE = 'https://agentgraph.co';
const SUBJECT = 'did:web:agentgraph.co:agents:8d34e889-3d07-4cfe-96aa-cb43ce662688';

// --- Fallback fixture (captured from prod 2026-06-01) ---------------------
// A real signed envelope + the matching JWKS. The signature is over the live
// preimage, so it only verifies if JCS canonicalization byte-matches the server.
// Freshness is checked with a pinned `now` so the fixture never goes stale.
const FIXTURE_JWKS = {
  keys: [
    { kty: 'OKP', crv: 'Ed25519', x: 'JwovTLVbpgk85zlMNruTiLzp85dAucsZWngs8NisBFg', kid: 'agentgraph-security-v1', use: 'sig', alg: 'EdDSA' },
    { kty: 'OKP', crv: 'Ed25519', x: 'vPk-HNu9TKjPUuEfguB5qc8CW0f5irYpiGwoEWi6W_k', kid: 'trust-v2-2026', use: 'sig', alg: 'EdDSA' },
  ],
};
const FIXTURE_ENV = {
  subject_did: 'did:web:agentgraph.co:agents:8d34e889-3d07-4cfe-96aa-cb43ce662688',
  subject_kind: 'agent',
  trust_score: 0.6317999999999999,
  score_version: 'v2.0',
  computed_at: '2026-06-01T18:04:00.207Z',
  freshness_ttl_seconds: 3600,
  contributions: [
    { source: 'self_attested', raw_signal: 0.6, weighted_contribution: 0.21, freshness_ttl_seconds: 3600, _metadata: { v1_component: 'verification', v1_weight: 0.35 } },
    { source: 'community_signal', raw_signal: 0.1781, weighted_contribution: 0.0178, freshness_ttl_seconds: 3600, _metadata: { v1_component: 'age', v1_weight: 0.1 } },
    { source: 'erc8004_reputation', raw_signal: 0.6, weighted_contribution: 0.21, freshness_ttl_seconds: 3600, _metadata: { v1_component: 'external_reputation', v1_weight: 0.35 } },
    { source: 'scan_corpus', raw_signal: 0.97, weighted_contribution: 0.194, freshness_ttl_seconds: 3600, _metadata: { v1_component: 'scan_score', v1_weight: 0.2 } },
  ],
  shape_version: 'trust-score-envelope-v2.0',
  canonicalization: 'jcs-rfc8785-v1',
  hash_algo: 'sha256',
  issuer: 'did:web:agentgraph.co',
  issued_at: '2026-06-01T18:04:00.207Z',
  proof: {
    type: 'Ed25519Signature2020',
    verificationMethod: 'did:web:agentgraph.co#trust-v2-2026',
    jws: 'eyJhbGciOiJFZERTQSIsImtpZCI6InRydXN0LXYyLTIwMjYiLCJ0eXAiOiJKV1QifQ..dJp7fQ_C_GTYT_nheIDj1lYZiwn9FRdQkJxL7hyFvbYmo6Z7bqnGXJ4upuUNIDyl0dQ_vO40_hiJpJymdRiqBA',
  },
};
const FIXTURE_NOW = new Date('2026-06-01T18:04:30.000Z'); // within 3600s TTL

async function fetchLive() {
  try {
    const client = new TrustClient(BASE, { timeout: 12000 });
    const [jwks, env] = await Promise.all([client.getJwks(), client.getAggregate(SUBJECT)]);
    return { jwks, env, live: true, now: undefined };
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[verify.test] live prod unreachable (${err.message}); using fixture`);
    return { jwks: FIXTURE_JWKS, env: FIXTURE_ENV, live: false, now: FIXTURE_NOW };
  }
}

test('verifies a real signed envelope against prod JWKS (valid + correct kid)', async () => {
  const { jwks, env, live, now } = await fetchLive();
  const result = verifyEnvelope(env, jwks, { now });

  assert.equal(result.signatureValid, true,
    `signature should verify — JCS digest must byte-match server. reason=${result.reason}`);
  assert.equal(result.kid, 'trust-v2-2026', 'kid should be the trust-v2 signing key');
  if (live) {
    // Live envelopes are freshly computed, so they should be fresh and fully valid.
    assert.equal(result.fresh, true, 'live envelope should be within its TTL');
    assert.equal(result.valid, true, `live envelope should be fully valid. reason=${result.reason}`);
  } else {
    // Fixture: signature is what proves byte-compatibility; freshness pinned via `now`.
    assert.equal(result.valid, true, `fixture should verify with pinned now. reason=${result.reason}`);
  }
  assert.equal(result.reason, 'ok');
});

test('tamper detection: mutating trust_score breaks the signature', async () => {
  const { jwks, env, now } = await fetchLive();
  const tampered = structuredClone(env);
  tampered.trust_score = (Number(env.trust_score) || 0) + 0.1;

  const result = verifyEnvelope(tampered, jwks, { now });
  assert.equal(result.valid, false, 'tampered envelope must not verify');
  assert.equal(result.signatureValid, false, 'signature must fail after mutation');
  assert.equal(result.reason, 'signature invalid');
});

test('tamper detection: mutating a contribution breaks the signature', async () => {
  const { jwks, env, now } = await fetchLive();
  const tampered = structuredClone(env);
  tampered.contributions[0].weighted_contribution = 0.99;

  const result = verifyEnvelope(tampered, jwks, { now });
  assert.equal(result.valid, false);
  assert.equal(result.signatureValid, false);
});

test('digest is stable and proof-independent', async () => {
  const { env } = await fetchLive();
  const d1 = envelopeDigest(env);
  const withoutProof = { ...env };
  delete withoutProof.proof;
  const d2 = envelopeDigest(withoutProof);
  assert.equal(d1.length, 32, 'SHA-256 digest is 32 raw bytes');
  assert.equal(Buffer.compare(d1, d2), 0, 'proof block must not affect the digest');
});

test('missing/unsupported proof is rejected', () => {
  const r1 = verifyEnvelope({ trust_score: 0.5 }, FIXTURE_JWKS);
  assert.equal(r1.valid, false);
  assert.equal(r1.reason, 'missing or unsupported proof');

  const r2 = verifyEnvelope({ proof: { type: 'BogusSignature', jws: 'a.b.c' } }, FIXTURE_JWKS);
  assert.equal(r2.reason, 'missing or unsupported proof');
});

test('malformed jws (wrong number of parts) is rejected', () => {
  const env = { proof: { type: 'Ed25519Signature2020', jws: 'only.two' } };
  const result = verifyEnvelope(env, FIXTURE_JWKS);
  assert.equal(result.valid, false);
  assert.equal(result.reason, 'malformed jws');
});

test('unknown kid yields no matching key', () => {
  const env = structuredClone(FIXTURE_ENV);
  // header with kid that is not in the JWKS
  const hdr = Buffer.from(JSON.stringify({ alg: 'EdDSA', kid: 'nope-9999', typ: 'JWT' })).toString('base64url');
  env.proof = { ...env.proof, jws: `${hdr}..${FIXTURE_ENV.proof.jws.split('.')[2]}` };
  const result = verifyEnvelope(env, FIXTURE_JWKS);
  assert.equal(result.valid, false);
  assert.equal(result.kid, 'nope-9999');
  assert.equal(result.reason, 'no matching key in JWKS');
});

test('isFresh respects the TTL window', () => {
  assert.equal(isFresh(FIXTURE_ENV, { now: FIXTURE_NOW }), true);
  const wayLater = new Date('2026-06-01T20:04:30.000Z'); // > 3600s after computed_at
  assert.equal(isFresh(FIXTURE_ENV, { now: wayLater }), false);
});

test('stale-but-authentic envelope reports expired, not invalid signature', async () => {
  const { jwks, env } = await fetchLive();
  const wayLater = new Date(new Date(env.computed_at).getTime() + (env.freshness_ttl_seconds + 60) * 1000);
  const result = verifyEnvelope(env, jwks, { now: wayLater });
  assert.equal(result.signatureValid, true, 'signature is still good on a stale envelope');
  assert.equal(result.fresh, false);
  assert.equal(result.valid, false);
  assert.equal(result.reason, 'envelope expired (stale)');
});
