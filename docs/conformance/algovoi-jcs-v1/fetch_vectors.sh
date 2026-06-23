#!/usr/bin/env bash
# Fetch AlgoVoi's JCS RFC 8785 conformance vector corpus, pinned to the exact
# commit AgentGraph validated against. Apache-2.0 (AlgoVoi / chopmob-cloud).
#
# Usage:  ./fetch_vectors.sh [dest_dir]   (default: ./vectors)
set -euo pipefail

REPO="https://github.com/chopmob-cloud/algovoi-jcs-conformance-vectors"
PIN="f31f4af55bb6f2b8d5f75722e674687391c52a6f"   # manifest 0.16.0 / 31 sets / 256 vectors (2026-06-22)
DEST="${1:-./vectors}"

tmp="$(mktemp -d)"
git clone --quiet "$REPO" "$tmp/corpus"
git -C "$tmp/corpus" checkout --quiet "$PIN"
mkdir -p "$DEST"
# flatten vectors/<set>/<file>.json -> <set>__<file>.json (matches run_conformance.py)
find "$tmp/corpus/vectors" -name '*.json' ! -name 'package*.json' | while read -r f; do
  rel="${f#"$tmp/corpus/vectors/"}"
  cp "$f" "$DEST/${rel//\//__}"
done
rm -rf "$tmp"
echo "Fetched $(ls -1 "$DEST"/*.json | wc -l | tr -d ' ') vector files into $DEST (pinned $PIN)"
