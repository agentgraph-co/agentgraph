// Zero-dependency verifier for the AgentGraph pre-execution-verdict-v0 reference fixture.
// Node built-ins only. Verifies each compact EdDSA JWS against the embedded JWKS and
// recomputes every binding_digest from scratch (JCS + SHA-256). Run: node verify_fixture.mjs
import { readFileSync } from 'node:fs';
import { createPublicKey, verify, createHash } from 'node:crypto';

const fx = JSON.parse(readFileSync(new URL('./fixture.json', import.meta.url)));
let pass = 0, fail = 0;
const ok = (cond, msg) => { if (cond) { pass++; } else { fail++; console.log('  ✗ FAIL:', msg); } };

// Minimal RFC 8785 JCS for the flat digest object (sorted keys; strings + integer numbers).
function jcs(obj) {
  const keys = Object.keys(obj).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + JSON.stringify(obj[k])).join(',') + '}';
}
const sha256hex = s => createHash('sha256').update(s).digest('hex');

const jwk = fx.jwks.keys[0];
const pub = createPublicKey({ key: { kty: jwk.kty, crv: jwk.crv, x: jwk.x }, format: 'jwk' });

for (const v of fx.vectors) {
  const [h, p, s] = v.jws.split('.');
  // 1. signature verifies against the published JWKS
  const sigOk = verify(null, Buffer.from(`${h}.${p}`), pub, Buffer.from(s, 'base64url'));
  ok(sigOk, `${v.scenario}: JWS signature`);
  // 2. payload decodes to the displayed core
  const core = JSON.parse(Buffer.from(p, 'base64url').toString());
  ok(core.envelope === 'pre-execution-verdict-v0', `${v.scenario}: envelope tag`);
  // 3. binding_digest recomputed from scratch matches
  const b = core.binding;
  const recomputed = sha256hex(jcs({ amount_usd: b.amount_usd, charge_ref: b.charge_ref, nonce: b.nonce, subject_did: core.subject_did }));
  ok(recomputed === b.binding_digest, `${v.scenario}: binding_digest recompute (${recomputed.slice(0,12)} vs ${b.binding_digest.slice(0,12)})`);
  ok(recomputed === v.binding_digest, `${v.scenario}: binding_digest matches vector header`);
  // 4. admission invariants
  ok(core.admission.verdict === v.expect.verdict, `${v.scenario}: verdict=${v.expect.verdict}`);
  ok(core.admission.reason_code === v.expect.reason_code, `${v.scenario}: reason_code=${v.expect.reason_code}`);
  // 5. budget logic is self-consistent with the verdict
  const amt = b.amount_usd, lim = core.admission.dynamic_limit_usd;
  if (v.scenario === 'admit')      ok(core.admission.verdict === 'admit' && amt <= lim, `${v.scenario}: amount ${amt} within limit ${lim}`);
  if (v.scenario === 'limit-deny') ok(core.admission.verdict === 'deny'  && amt > lim,  `${v.scenario}: amount ${amt} exceeds limit ${lim}`);
  // 6. action_ref carries its derivation method + recomputes from the preimage
  ok(b.action_ref_method === 'argentum-core action-ref-v1', `${v.scenario}: action_ref_method present`);
  const pre = b.action_ref_preimage;
  const aref = sha256hex(jcs({ agent_id: pre.agent_id, action_type: pre.action_type, scope: pre.scope, timestamp: pre.timestamp }));
  ok(aref === b.action_ref, `${v.scenario}: action_ref recompute from preimage (draft-giskard-aeoess-action-ref §3)`);
}

const total = pass + fail;
console.log(fail === 0
  ? `\n✓ ${pass}/${total} assertions pass — agentgraph-pre-execution-verdict-v0`
  : `\n✗ ${fail} of ${total} assertions FAILED`);
console.log('Sample digests:');
for (const v of fx.vectors) console.log(`  ${v.scenario}: ${v.binding_digest}`);
process.exit(fail === 0 ? 0 : 1);
