#!/usr/bin/env python3
"""Conformance verifier for the x402 endpoint-safety screen.

Reproduces every vector in safety_screen_v0.json from scratch: runs the reference
screen, canonicalizes the verdict with RFC 8785, and checks the bytes + SHA-256.
Any conforming implementation of the safety screen must reproduce these.

    python3 verify_fixture.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import rfc8785

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import safety_screen as ss  # noqa: E402


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    fixture = json.load(open(os.path.join(here, "safety_screen_v0.json")))
    errors = []

    for v in fixture["vectors"]:
        verdict = ss.screen(v["input"], v.get("ctx", {}))
        canon = rfc8785.dumps(verdict)
        sha = hashlib.sha256(canon).hexdigest()

        if verdict != v["expected_verdict"]:
            errors.append(f"{v['name']}: verdict {verdict} != {v['expected_verdict']}")
        if canon.decode("utf-8") != v["verdict_canonical_bytes_utf8"]:
            errors.append(f"{v['name']}: canonical bytes mismatch")
        if sha != v["verdict_sha256"]:
            errors.append(f"{v['name']}: sha256 {sha} != {v['verdict_sha256']}")

        failed_here = any(e.startswith(v["name"]) for e in errors)
        mark = "✗" if failed_here else "✓"
        print(f"  {mark} {v['name']:24} -> {verdict['verdict']:6} {sha[:16]}…")

    print("-" * 56)
    if errors:
        for e in errors:
            print("FAIL:", e)
        print(f"{len(errors)} failure(s)")
        return 1
    n = len(fixture["vectors"])
    print(f"OK — {n}/{n} vectors reproduce byte-for-byte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
