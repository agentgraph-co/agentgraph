#!/usr/bin/env python3
"""EvidenceAnchor conformance verifier — AgentGraph static-analysis scan attestations.

Recomputes every action_ref in vectors.json from its preimage, offline, and checks the
invariants. A verifier confirms the scan record without access to AgentGraph's infra.

    python3 verify.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import rfc8785


def action_ref(preimage: dict) -> tuple[bytes, str]:
    canon = rfc8785.dumps(preimage)
    return canon, hashlib.sha256(canon).hexdigest()


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    fx = json.load(open(os.path.join(here, "vectors.json")))
    errors: list[str] = []
    by_name: dict[str, str] = {}

    for v in fx["vectors"]:
        canon, ref = action_ref(v["action_ref_preimage"])
        if canon.hex() != v["action_ref_canonical_hex"]:
            errors.append(f"{v['name']}: canonical bytes mismatch")
        if ref != v["action_ref"]:
            errors.append(f"{v['name']}: action_ref {ref} != {v['action_ref']}")
        # the verdict must NOT be part of the preimage (evidence independent of the key)
        if any(k in v["action_ref_preimage"] for k in ("verdict", "findings", "grade")):
            errors.append(f"{v['name']}: verdict leaked into action_ref preimage")
        by_name[v["name"]] = ref
        print(f"  {'✓' if not [e for e in errors if e.startswith(v['name'])] else '✗'} "
              f"{v['name']:32} {v['expectation']:4} {ref[:16]}…")

    # invariants
    if by_name.get("pass_clean_mcp") != by_name.get("rescan_same_target_stable_ref"):
        errors.append("invariant: same target/type/timestamp must give the same action_ref")
    if by_name.get("pass_clean_mcp") == by_name.get("rescan_later_distinct_ref"):
        errors.append("invariant: a later timestamp must give a different action_ref")

    print("-" * 60)
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print(f"OK — {len(fx['vectors'])}/{len(fx['vectors'])} action_refs reproduce + invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
