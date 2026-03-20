#!/usr/bin/env bash
# ============================================================================
# AgentGraph Production Rollback
# ============================================================================
# Rolls back to a previous git commit on the EC2 instance.
# Does NOT roll back database migrations (manual step if needed).
#
# Usage:
#   ./scripts/rollback-prod.sh                  # Roll back 1 commit
#   ./scripts/rollback-prod.sh <commit-hash>    # Roll back to specific commit
#   ./scripts/rollback-prod.sh --list           # Show last 10 commits on prod
#   ./scripts/rollback-prod.sh --dry-run        # Show what would happen
#   ./scripts/rollback-prod.sh --dry-run abc123 # Show what rollback to abc123 would do
#
# Environment variables:
#   AG_EC2_HOST  — EC2 Elastic IP (required)
#   AG_SSH_KEY   — Path to SSH key (required)
# ============================================================================

set -euo pipefail

EC2_HOST="${AG_EC2_HOST:?Set AG_EC2_HOST env var}"
EC2_USER="ec2-user"
SSH_KEY="${AG_SSH_KEY:?Set AG_SSH_KEY env var}"
PROJECT_DIR="agentgraph"
COMPOSE_FILE="docker-compose.prod.yml"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

DRY_RUN=false
TARGET_COMMIT=""
LIST_MODE=false

for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=true ;;
    --list)     LIST_MODE=true ;;
    --help|-h)
      echo "Usage: $0 [--list] [--dry-run] [<commit-hash>]"
      echo ""
      echo "  (no args)       Roll back 1 commit (HEAD~1)"
      echo "  <commit-hash>   Roll back to a specific commit"
      echo "  --list          Show last 10 deployed commits"
      echo "  --dry-run       Show what would happen without executing"
      exit 0
      ;;
    -*)
      echo -e "${RED}Unknown flag: $arg${NC}"
      exit 1
      ;;
    *)
      TARGET_COMMIT="$arg"
      ;;
  esac
done

remote() {
  ssh $SSH_OPTS "${EC2_USER}@${EC2_HOST}" "$1"
}

step_num=0
step() {
  step_num=$((step_num + 1))
  echo ""
  echo -e "${CYAN}${BOLD}[$step_num] $1${NC}"
}

ok()   { echo -e "    ${GREEN}OK${NC} $1"; }
fail() { echo -e "    ${RED}FAIL${NC} $1"; exit 1; }
warn() { echo -e "    ${YELLOW}WARN${NC} $1"; }

# --- List mode ---
if $LIST_MODE; then
  echo -e "${BOLD}Last 10 commits on production:${NC}"
  echo ""
  remote "cd ~/${PROJECT_DIR} && git log --oneline -10" 2>&1 | while IFS= read -r line; do
    echo "  $line"
  done
  exit 0
fi

# --- Determine target ---
if [ -z "$TARGET_COMMIT" ]; then
  TARGET_COMMIT="HEAD~1"
fi

echo -e "${BOLD}=== AgentGraph Production Rollback ===${NC}"
echo ""
echo -e "  Host:   ${EC2_USER}@${EC2_HOST}"
echo -e "  Target: ${TARGET_COMMIT}"
echo -e "  Dry:    ${DRY_RUN}"

if $DRY_RUN; then
  echo ""
  echo -e "${YELLOW}${BOLD}--- DRY RUN MODE ---${NC}"
fi

# --- Step 1: Verify connectivity and get current state ---
step "Getting current deployment state"
if $DRY_RUN; then
  echo "    Would SSH to ${EC2_HOST} and check git log"
else
  CURRENT=$(remote "cd ~/${PROJECT_DIR} && git log --oneline -1" 2>&1)
  echo "    Current: $CURRENT"

  # Resolve target
  RESOLVED=$(remote "cd ~/${PROJECT_DIR} && git rev-parse --short ${TARGET_COMMIT}" 2>&1) || fail "Cannot resolve '${TARGET_COMMIT}'. Use --list to see available commits."
  TARGET_MSG=$(remote "cd ~/${PROJECT_DIR} && git log --oneline -1 ${RESOLVED}" 2>&1)
  echo "    Target:  $TARGET_MSG"

  # Check for uncommitted changes on prod
  DIRTY=$(remote "cd ~/${PROJECT_DIR} && git status --porcelain" 2>&1 | wc -l | tr -d ' ')
  if [ "$DIRTY" -gt "0" ]; then
    warn "Production has $DIRTY uncommitted changes — they will be preserved (rollback uses git checkout)"
  fi
fi

# --- Step 2: Create backup tag ---
step "Tagging current state for recovery"
if $DRY_RUN; then
  echo "    Would create tag: pre-rollback-$(date +%Y%m%d-%H%M%S)"
else
  TAG="pre-rollback-$(date +%Y%m%d-%H%M%S)"
  remote "cd ~/${PROJECT_DIR} && git tag ${TAG}" 2>&1 || warn "Tag creation failed (non-fatal)"
  ok "Tagged as ${TAG} (use 'git checkout ${TAG}' to undo rollback)"
fi

# --- Step 3: Checkout target commit ---
step "Checking out target commit"
if $DRY_RUN; then
  echo "    Would run: git checkout ${TARGET_COMMIT}"
else
  remote "cd ~/${PROJECT_DIR} && git checkout ${TARGET_COMMIT}" 2>&1 | while IFS= read -r line; do
    echo "    $line"
  done
  ok "Checked out ${TARGET_COMMIT}"
fi

# --- Step 4: Rebuild backend ---
step "Rebuilding backend"
if $DRY_RUN; then
  echo "    Would rebuild and restart Docker containers"
else
  remote "cd ~/${PROJECT_DIR} && sudo docker-compose -f ${COMPOSE_FILE} up -d --build" 2>&1 | while IFS= read -r line; do
    echo "    $line"
  done
  ok "Backend rebuilt and restarted"
fi

# --- Step 5: Rebuild frontend ---
step "Rebuilding frontend"
if $DRY_RUN; then
  echo "    Would run: npm run build in web/"
else
  remote "cd ~/${PROJECT_DIR}/web && npm run build" 2>&1 | while IFS= read -r line; do
    echo "    $line"
  done
  ok "Frontend rebuilt"
fi

# --- Step 6: Restart nginx ---
step "Restarting nginx"
if $DRY_RUN; then
  echo "    Would restart nginx container"
else
  remote "cd ~/${PROJECT_DIR} && sudo docker exec agentgraph-nginx-1 nginx -s reload" 2>&1 || true
  ok "Nginx reloaded"
fi

# --- Step 7: Health check ---
step "Waiting for backend health"
if $DRY_RUN; then
  echo "    Would poll /health for up to 30s"
else
  HEALTHY=false
  for i in $(seq 1 15); do
    if remote "curl -sf --max-time 3 http://localhost/health" > /dev/null 2>&1; then
      HEALTHY=true
      break
    fi
    echo "    Attempt $i/15 — waiting 2s..."
    sleep 2
  done
  if $HEALTHY; then
    ok "Backend is healthy"
  else
    fail "Backend not healthy after rollback. Check logs."
  fi
fi

# --- Done ---
echo ""
if $DRY_RUN; then
  echo -e "${YELLOW}${BOLD}=== Dry run complete ===${NC}"
else
  FINAL=$(remote "cd ~/${PROJECT_DIR} && git log --oneline -1" 2>&1)
  echo -e "${GREEN}${BOLD}=== Rollback successful ===${NC}"
  echo ""
  echo -e "  Now at: $FINAL"
  echo -e "  Undo:   $0 ${TAG}"
  echo ""
  echo -e "${YELLOW}NOTE: Database migrations are NOT rolled back.${NC}"
  echo -e "If the rolled-back code requires older schema, manually run:"
  echo -e "  ssh $SSH_OPTS ${EC2_USER}@${EC2_HOST} 'cd ~/${PROJECT_DIR} && docker-compose -f ${COMPOSE_FILE} exec backend python -m alembic downgrade -1'"
fi
