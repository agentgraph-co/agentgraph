// Reproducible cross-implementation byte-match check (Node built-ins; uses global fetch).
// Pulls the other published fixtures and recomputes their binding_digests with the SAME
// construction this reference uses — proving byte-identical agreement across independent impls.
//   binding_digest = sha256(JCS({amount_usd, charge_ref, nonce, subject_did}))
import { createHash } from 'node:crypto';
const jcs = o => '{' + Object.keys(o).sort().map(k => JSON.stringify(k)+':'+JSON.stringify(o[k])).join(',') + '}';
const bd = (a,c,n,s) => createHash('sha256').update(jcs({amount_usd:a,charge_ref:c,nonce:n,subject_did:s})).digest('hex');
const b64ud = s => Buffer.from(s, 'base64url').toString();
let pass=0, fail=0; const ok=(c,m)=>{c?pass++:(fail++,console.log('  ✗',m));};

const HAROLD='https://raw.githubusercontent.com/haroldmalikfrimpong-ops/agentid/main/tests/verifier_attestation_fixture.json';
const EVIDAI='https://raw.githubusercontent.com/evidai/agent-payment-mcp/main/docs/conformance/gated-preflight-v1.json';

const h = await (await fetch(HAROLD)).json();
console.log('haroldmalikfrimpong-ops/agentid (verifier-side):');
const hAtts = [h.live_production_example, ...(h.conformance_scenarios||[]).map(s=>s.verifier_attestation)].filter(Boolean);
for (const a of hAtts) { const b=a.binding, sd=a.subject?.did;
  ok(bd(b.amount_usd,b.charge_ref,b.nonce,sd)===b.binding_digest, `harold ${b.charge_ref}`); }

const e = await (await fetch(EVIDAI)).json();
console.log('evidai/agent-payment-mcp (gateway-side):');
for (const v of (e.vectors||[])) { const j=v.verifier_attestation; if(!j||!String(j).includes('.')) continue;
  const p=JSON.parse(b64ud(j.split('.')[1])); const b=p.binding, sd=p.subject_did||p.subject?.did;
  if(!b?.binding_digest||!sd) continue;
  ok(bd(b.amount_usd,b.charge_ref,b.nonce,sd)===b.binding_digest, `evidai ${v.name}`); }

console.log(fail===0 ? `\n✓ ${pass}/${pass+fail} cross-impl binding_digests byte-match this reference` : `\n✗ ${fail} mismatches`);
process.exit(fail===0?0:1);
