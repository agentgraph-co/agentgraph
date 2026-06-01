// Client-side verification of AgentGraph Trust Score v2 envelopes.
//
// The point of the signed envelope: a consumer can verify a trust score WITHOUT
// trusting AgentGraph's server. This module reproduces the exact verification the
// Python SDK (agentgraph_sdk/verify.py) and the server do — JCS-canonical,
// proof-stripped, Ed25519 over a SHA-256 digest — standalone. It only needs
// `canonicalize` (RFC 8785 JCS, byte-matches Python's rfc8785) plus Node's
// built-in `node:crypto`.
//
// Spec: docs/standards/trust-score-envelope-v2.0.md (§6 verification).

import { createHash, createPublicKey, verify as cryptoVerify } from 'node:crypto';
import canonicalize from 'canonicalize';

export const PROOF_TYPE = 'Ed25519Signature2020';

/**
 * Outcome of verifying a signed trust-score envelope.
 *
 * `valid` is the bottom line (signature good AND within freshness window).
 * The component fields explain a failure.
 *
 * @typedef {Object} VerificationResult
 * @property {boolean} valid           signature valid AND fresh
 * @property {boolean} signatureValid  Ed25519 signature verified
 * @property {boolean} fresh           within freshness_ttl_seconds window
 * @property {string|null} kid         key id read from the JWS header
 * @property {string} reason           human-readable outcome
 */

/** base64url -> Buffer (handles missing padding). */
function b64urlDecode(s) {
  return Buffer.from(s, 'base64url');
}

/** Return a shallow copy of the envelope without the top-level `proof` key. */
function stripProof(envelope) {
  const out = {};
  for (const k of Object.keys(envelope)) {
    if (k !== 'proof') out[k] = envelope[k];
  }
  return out;
}

/**
 * SHA-256 of the JCS-canonical, proof-stripped envelope (what proof.jws signs).
 * Returns the raw 32-byte digest (mirrors Python's `.digest()`, not hexdigest).
 * @param {object} envelope
 * @returns {Buffer}
 */
export function envelopeDigest(envelope) {
  const canonical = canonicalize(stripProof(envelope));
  return createHash('sha256').update(Buffer.from(canonical, 'utf-8')).digest();
}

/** Read the `kid` from a compact JWS header (first dot-part). */
function kidFromJws(jws) {
  try {
    const header = jws.split('.', 1)[0];
    const decoded = JSON.parse(b64urlDecode(header).toString('utf-8'));
    return decoded.kid ?? null;
  } catch {
    return null;
  }
}

/**
 * Resolve an Ed25519 public key (Node KeyObject) from a JWKS (RFC 7517) by kid.
 *
 * `jwks` may be the full `{ keys: [...] }` doc or a bare array of JWKs.
 * If `kid` is null, the first OKP/Ed25519 key is used.
 * @returns {import('node:crypto').KeyObject|null}
 */
function publicKeyForKid(jwks, kid) {
  const keys = Array.isArray(jwks) ? jwks : (jwks?.keys ?? []);
  const candidates = keys.filter(
    (k) => k && k.kty === 'OKP' && k.crv === 'Ed25519' && 'x' in k,
  );
  const build = (jwk) =>
    createPublicKey({
      key: { kty: 'OKP', crv: 'Ed25519', x: jwk.x },
      format: 'jwk',
    });
  if (kid !== null && kid !== undefined) {
    for (const k of candidates) {
      if (k.kid === kid) return build(k);
    }
    return null;
  }
  if (candidates.length > 0) return build(candidates[0]);
  return null;
}

/**
 * True iff the envelope is within its `freshness_ttl_seconds` window.
 * @param {object} envelope
 * @param {{now?: Date}} [opts]
 * @returns {boolean}
 */
export function isFresh(envelope, { now } = {}) {
  const nowDate = now ?? new Date();
  try {
    const computedStr = String(envelope.computed_at).replace('Z', '+00:00');
    const computed = new Date(computedStr);
    if (Number.isNaN(computed.getTime())) return false;
    const ttl = parseInt(envelope.freshness_ttl_seconds ?? 0, 10);
    if (Number.isNaN(ttl)) return false;
    const deltaSeconds = (nowDate.getTime() - computed.getTime()) / 1000;
    return deltaSeconds <= ttl;
  } catch {
    return false;
  }
}

/**
 * Verify a signed v2 trust-score envelope against a JWKS.
 *
 * Fetch the JWKS once from `<issuer>/.well-known/jwks.json` (or use the client's
 * `verifyEnvelope()`/`verify()` which do it for you). Returns a
 * VerificationResult; `valid` is true iff signature valid AND fresh.
 *
 * @param {object} envelope
 * @param {object|Array} jwks
 * @param {{now?: Date}} [opts]
 * @returns {VerificationResult}
 */
export function verifyEnvelope(envelope, jwks, { now } = {}) {
  const proof = envelope?.proof;
  if (!proof || proof.type !== PROOF_TYPE) {
    return { valid: false, signatureValid: false, fresh: false, kid: null, reason: 'missing or unsupported proof' };
  }
  const jws = proof.jws ?? '';
  const parts = jws.split('.');
  if (parts.length !== 3) {
    return { valid: false, signatureValid: false, fresh: false, kid: null, reason: 'malformed jws' };
  }

  const kid = kidFromJws(jws);
  const pub = publicKeyForKid(jwks, kid);
  if (pub === null) {
    return { valid: false, signatureValid: false, fresh: false, kid, reason: 'no matching key in JWKS' };
  }

  let sigOk = false;
  try {
    const signature = b64urlDecode(parts[2]);
    // Ed25519: algorithm MUST be null in Node's crypto.verify.
    sigOk = cryptoVerify(null, envelopeDigest(envelope), pub, signature);
  } catch {
    sigOk = false;
  }

  const fresh = isFresh(envelope, { now });
  if (!sigOk) {
    return { valid: false, signatureValid: false, fresh, kid, reason: 'signature invalid' };
  }
  if (!fresh) {
    return { valid: false, signatureValid: true, fresh: false, kid, reason: 'envelope expired (stale)' };
  }
  return { valid: true, signatureValid: true, fresh: true, kid, reason: 'ok' };
}

export default verifyEnvelope;
