#!/usr/bin/env bash
# Scheduled corpus scan — accumulates the Q3 security-scan corpus (#111).
#
# Runs a bounded batch each invocation, skipping repos already scanned (via the
# skip-file) so recurring runs cover NEW repos across the MCP + agent-framework
# ecosystems instead of repeating. Designed for hourly cron; naturally tapers
# once the discoverable set is exhausted. Respects the GitHub rate limit by
# capping each run.
#
# Cron (hourly, this week): see scripts/install_corpus_cron.sh / crontab -l
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root
mkdir -p data/corpus

# GITHUB_TOKEN only (do NOT `source .env` — it breaks pydantic cors_origins parse).
TOKEN="$(grep -E '^GITHUB_TOKEN=' .env.secrets 2>/dev/null | cut -d= -f2- | tr -d '"'\''' || true)"

STAMP="$(date +%Y%m%d_%H%M)"
GITHUB_TOKEN="$TOKEN" python3 -m src.scanner.batch_scan \
  --from-github \
  --limit 150 \
  --skip-file data/corpus/scanned_repos.txt \
  --output "data/corpus/scan_${STAMP}.json" \
  >> data/corpus/scan.log 2>&1

echo "$(date -u +%FT%TZ) run ${STAMP} complete; scanned-set size: $(wc -l < data/corpus/scanned_repos.txt 2>/dev/null || echo 0)" >> data/corpus/scan.log
