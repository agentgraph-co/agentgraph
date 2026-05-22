#!/usr/bin/env python3
"""
JCS RFC 8785 cross-implementation runner -- Python (rfc8785@0.1.4)
Verifies 53 substrate vectors across 5 fixture files byte-for-byte.
Usage: pip install rfc8785 && python runner_python.py
"""
import json, hashlib, base64
from pathlib import Path
import rfc8785

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def jcs_hash(obj):
    canon = rfc8785.dumps(obj)
    return hashlib.sha256(canon).hexdigest()

def jcs_bytes_b64(obj):
    return base64.b64encode(rfc8785.dumps(obj)).decode()

passed = failed = 0

# Files with mandate_body / attestation_body -> expected_jcs_bytes_b64
for fname in ["ap2-omh-v0.json", "per_chain_envelope_v0.json", "privacy_class_v0.1.json"]:
    body_key = "attestation_body" if "privacy" in fname else "mandate_body"
    data = json.loads((FIXTURES_DIR / fname).read_bytes())
    vectors = data["vectors"]
    for v in vectors:
        vid = v.get("vector_id", v.get("id", "?"))
        got = jcs_bytes_b64(v[body_key])
        exp = v["expected_jcs_bytes_b64"]
        ok = got == exp
        passed += ok; failed += (not ok)
        status = "PASS" if ok else "FAIL\n  got={}\n  exp={}".format(got[:40], exp[:40])
        print(f"{fname} {vid}: {status}")

# Files with input -> canonical_sha256
for fname in ["aps_vectors.json"]:
    data = json.loads((FIXTURES_DIR / fname).read_bytes())
    vectors = data["vectors"]
    for v in vectors:
        vid = v.get("name", v.get("vector_id", v.get("id", "?")))
        got = jcs_hash(v["input"])
        exp = v["canonical_sha256"]
        ok = got == exp
        passed += ok; failed += (not ok)
        print(f"{fname} {vid}: {'PASS' if ok else 'FAIL'}")

# ctef: flat dict at top level, named keys -> input_object + canonical_sha256
for fname in ["ctef_vectors.json"]:
    data = json.loads((FIXTURES_DIR / fname).read_bytes())
    for vid, v in data.items():
        if not isinstance(v, dict) or "input_object" not in v:
            continue
        got = jcs_hash(v["input_object"])
        exp = v["canonical_sha256"]
        ok = got == exp
        passed += ok; failed += (not ok)
        print(f"{fname} {vid}: {'PASS' if ok else 'FAIL'}")

print(f"\nPython rfc8785@0.1.4: {passed}/{passed+failed} PASS")
