#!/usr/bin/env bash
# Scheduled corpus scan — accumulates the Q3 security-scan corpus (#111).
#
# Runs a bounded batch each invocation, skipping repos already scanned (via the
# skip-file) so recurring runs cover NEW repos across the MCP + agent-framework
# ecosystems instead of repeating. Designed for hourly cron; naturally tapers
# once the discoverable set is exhausted.
#
# Hardening:
#  - lockdir prevents overlapping runs (an over-long run won't collide with the
#    next hourly fire on GitHub rate limits)
#  - watchdog kills a run that exceeds the budget (before the next hour)
#  - log rotation keeps scan.log bounded
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root
mkdir -p data/corpus
LOG=data/corpus/scan.log
LOCK=data/corpus/.scan.lock
BUDGET_SECS=3000   # 50 min — leaves headroom before the next hourly run

# --- overlap guard: mkdir is atomic; bail if a run is already in progress ---
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) skipped — a scan is already running ($LOCK)" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

# --- log rotation: keep scan.log under ~5MB ---
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 5000000 ]; then
  mv "$LOG" "$LOG.1"
fi

# GITHUB_TOKEN only (do NOT `source .env` — it breaks pydantic cors_origins parse).
TOKEN="$(grep -E '^GITHUB_TOKEN=' .env.secrets 2>/dev/null | cut -d= -f2- | tr -d '"'\''' || true)"
STAMP="$(date +%Y%m%d_%H%M)"

# --- run with a watchdog timeout (portable; macOS has no `timeout`) ---
GITHUB_TOKEN="$TOKEN" python3 -m src.scanner.batch_scan \
  --from-github --limit 150 \
  --skip-file data/corpus/scanned_repos.txt \
  --output "data/corpus/scan_${STAMP}.json" >> "$LOG" 2>&1 &
PID=$!
( sleep "$BUDGET_SECS"; kill -0 "$PID" 2>/dev/null && kill "$PID" 2>/dev/null \
  && echo "$(date -u +%FT%TZ) watchdog killed run ${STAMP} (exceeded ${BUDGET_SECS}s)" >> "$LOG" ) &
WATCHDOG=$!
wait "$PID" 2>/dev/null || true
kill "$WATCHDOG" 2>/dev/null || true

echo "$(date -u +%FT%TZ) run ${STAMP} complete; scanned-set: $(wc -l < data/corpus/scanned_repos.txt 2>/dev/null || echo 0)" >> "$LOG"
