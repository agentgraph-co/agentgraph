#!/usr/bin/env python3
"""AgentGraph <-> AlgoVoi JCS conformance runner (v2 — full coverage).

Handles all vector encodings in the corpus:
  - input under: input_object | preimage | receipt | input | object | canonical_input
  - expected bytes under: *jcs_bytes_b64 (base64) | canonical_bytes_utf8 (utf8 str)
  - expected hash  under: *content_sha256 | *receipt_hash | canonical_sha256 | expected_sha256
Pairs expected-keys to the input by name affinity (so a dict carrying BOTH a
'receipt' and a 'preimage' input matches each to its own expected_* fields).
"""
import base64, glob, hashlib, json, os, sys
import rfc8785

INPUT_KEYS = ("input_object", "preimage", "receipt", "input", "object", "canonical_input",
              "mandate_body", "attestation_body", "response", "payload")

def is_hex64(s):
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s.lower())

def expected_for(node, ikey):
    """Find (bytes, hash) expected values whose key name best matches input key ikey."""
    bkeys = [k for k, v in node.items() if isinstance(v, str) and ("jcs_bytes_b64" in k or "canonical_bytes_utf8" == k or k.endswith("_bytes_b64") or k.endswith("canonical_json"))]
    # content_hash / prev_hash are audit-chain linkage metadata (deliberately stale in
    # tamper rows), NOT JCS reproduction targets — exclude them from conformance scoring.
    LINKAGE = ("content_hash", "prev_hash")
    hkeys = [k for k, v in node.items() if is_hex64(v) and k not in LINKAGE
             and ("content_sha256" in k or "receipt_hash" in k or "canonical_sha256" == k
                  or "expected_sha256" == k or k.endswith("_hash") or k.endswith("_sha256"))]
    def pick(keys):
        if not keys: return None
        aff = [k for k in keys if ikey in k]
        return (aff or keys)[0]
    return pick(bkeys), pick(hkeys)

results = []

def decode_bytes(node, bkey):
    v = node[bkey]
    if bkey.endswith("_b64") or "b64" in bkey:
        return base64.b64decode(v)
    return v.encode("utf-8")

def check(fname, label, node, expect):
    # reject/negative-path vectors deliberately tamper a field so the stored hash
    # NO LONGER equals sha256(jcs(payload)); for those, a mismatch is the PASS.
    reject = (expect or "").lower() in ("reject", "fail", "deny", "invalid")
    for ikey in INPUT_KEYS:
        if ikey in node and isinstance(node[ikey], (dict, list)):
            bkey, hkey = expected_for(node, ikey)
            if not bkey and not hkey:
                continue
            try:
                ours = rfc8785.dumps(node[ikey])
            except Exception as e:
                results.append((fname, f"{label}.{ikey}", "ERROR", False, str(e)))
                continue
            if bkey:
                exp = decode_bytes(node, bkey)
                ok = ours == exp
                results.append((fname, f"{label}.{ikey}", "bytes", ok,
                                "" if ok else f"ours={ours[:80]!r} theirs={exp[:80]!r}"))
            if hkey:
                ok = hashlib.sha256(ours).hexdigest() == node[hkey].lower()
                results.append((fname, f"{label}.{ikey}", "sha256", ok,
                                "" if ok else f"ours={hashlib.sha256(ours).hexdigest()} theirs={node[hkey].lower()} (expect={expect})"))

def walk(fname, node, path="$", expect=None):
    if isinstance(node, dict):
        expect = node.get("expectation", node.get("expected_result", expect))
        check(fname, path, node, expect)
        for k, v in node.items():
            walk(fname, v, f"{path}.{k}", expect)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(fname, v, f"{path}[{i}]", expect)

VECTORS = os.environ.get("VECTORS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors")
for f in sorted(glob.glob(os.path.join(VECTORS, "*.json"))):
    b = os.path.basename(f)
    if "package" in b:
        continue
    try:
        data = json.load(open(f))
    except Exception as e:
        print(f"!! parse {b}: {e}"); continue
    walk(b, data)

failed = [r for r in results if not r[3]]
by_file = {}
for r in results:
    by_file.setdefault(r[0], []).append(r)
print("=" * 74)
print("AgentGraph rfc8785@0.1.4  vs  AlgoVoi JCS conformance vectors  (full sweep)")
print("=" * 74)
for f in sorted(by_file):
    rs = by_file[f]; p = sum(1 for x in rs if x[3])
    print(f"  {'OK ' if p==len(rs) else 'XX '} {f:<54} {p}/{len(rs)}")
    for r in rs:
        if not r[3]:
            print(f"        FAIL [{r[2]}] {r[1]}: {r[4]}")
print("-" * 74)
print(f"TOTAL: {len(results)-len(failed)}/{len(results)} checks pass across "
      f"{len(by_file)} files  ({len(failed)} failures)")
sys.exit(1 if failed else 0)
