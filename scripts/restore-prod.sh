#!/usr/bin/env bash
# ============================================================================
# AgentGraph Production Database Restore
# ============================================================================
# Restores a production database from a backup file on the EC2 instance.
# Supports .sql.gz (pg_dump plain) and .dump (pg_restore custom format).
#
# Usage:
#   ./scripts/restore-prod.sh --list                          # List available backups
#   ./scripts/restore-prod.sh --dry-run <backup-file>         # Show what would happen
#   ./scripts/restore-prod.sh --confirm <backup-file>         # Restore a specific backup
#   ./scripts/restore-prod.sh --confirm --latest              # Restore the most recent backup
#
# The --confirm flag is REQUIRED for actual execution (safety guard).
#
# Environment variables:
#   AG_EC2_HOST  — EC2 Elastic IP (required)
#   AG_SSH_KEY   — Path to SSH key (required)
# ============================================================================

set -euo pipefail

EC2_HOST="${AG_EC2_HOST:?Set AG_EC2_HOST env var (e.g. your Elastic IP)}"
EC2_USER="ec2-user"
SSH_KEY="${AG_SSH_KEY:?Set AG_SSH_KEY env var (path to your SSH key)}"
PROJECT_DIR="agentgraph"
COMPOSE_FILE="docker-compose.prod.yml"
BACKUP_DIR="/home/ec2-user/backups"
CONTAINER_PG="agentgraph-postgres-1"
CONTAINER_BACKEND="agentgraph-backend-1"
PG_DB="agentgraph"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

DRY_RUN=false
LIST_MODE=false
CONFIRM=false
USE_LATEST=false
BACKUP_FILE=""

for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=true ;;
    --list)     LIST_MODE=true ;;
    --confirm)  CONFIRM=true ;;
    --latest)   USE_LATEST=true ;;
    --help|-h)
      echo "Usage: $0 [--list] [--dry-run] [--confirm] [--latest | <backup-file>]"
      echo ""
      echo "  --list              List available backups on EC2"
      echo "  --dry-run <file>    Show what would happen without executing"
      echo "  --confirm <file>    Actually restore (REQUIRED for execution)"
      echo "  --latest            Use the most recent backup file"
      echo "  <backup-file>       Backup filename (e.g. agentgraph-20260320-030000.sql.gz)"
      echo ""
      echo "Examples:"
      echo "  $0 --list"
      echo "  $0 --dry-run agentgraph-20260320-030000.sql.gz"
      echo "  $0 --confirm agentgraph-20260320-030000.sql.gz"
      echo "  $0 --confirm --latest"
      exit 0
      ;;
    -*)
      echo -e "${RED}Unknown flag: $arg${NC}"
      exit 1
      ;;
    *)
      BACKUP_FILE="$arg"
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
info() { echo -e "    $1"; }

# --- List mode ---
if $LIST_MODE; then
  echo -e "${BOLD}Available backups on production:${NC}"
  echo ""
  echo -e "  ${CYAN}Daily backups:${NC}"
  remote "ls -lh ${BACKUP_DIR}/daily/agentgraph-*.sql.gz ${BACKUP_DIR}/daily/agentgraph-*.dump 2>/dev/null | awk '{print \"    \" \$5 \"  \" \$6 \" \" \$7 \" \" \$8 \"  \" \$9}'" 2>&1 || echo "    (none)"
  echo ""
  echo -e "  ${CYAN}Weekly backups:${NC}"
  remote "ls -lh ${BACKUP_DIR}/weekly/agentgraph-*.sql.gz ${BACKUP_DIR}/weekly/agentgraph-*.dump 2>/dev/null | awk '{print \"    \" \$5 \"  \" \$6 \" \" \$7 \" \" \$8 \"  \" \$9}'" 2>&1 || echo "    (none)"
  echo ""
  echo -e "  ${CYAN}Root backup dir:${NC}"
  remote "ls -lh ${BACKUP_DIR}/agentgraph-*.sql.gz ${BACKUP_DIR}/agentgraph-*.dump 2>/dev/null | awk '{print \"    \" \$5 \"  \" \$6 \" \" \$7 \" \" \$8 \"  \" \$9}'" 2>&1 || echo "    (none)"
  exit 0
fi

# --- Resolve backup file ---
if $USE_LATEST; then
  # Will resolve on remote in step 1
  BACKUP_FILE="__latest__"
elif [ -z "$BACKUP_FILE" ]; then
  echo -e "${RED}Error: Specify a backup file or --latest. Use --list to see available backups.${NC}"
  echo "Usage: $0 [--confirm] [--dry-run] [--latest | <backup-file>]"
  exit 1
fi

# --- Safety check ---
if ! $DRY_RUN && ! $CONFIRM; then
  echo -e "${RED}${BOLD}Error: --confirm flag is required for actual restore.${NC}"
  echo ""
  echo "This is a destructive operation that will REPLACE the production database."
  echo "Add --confirm to proceed, or use --dry-run to preview."
  echo ""
  echo "  $0 --confirm ${BACKUP_FILE}"
  echo "  $0 --dry-run ${BACKUP_FILE}"
  exit 1
fi

echo -e "${BOLD}=== AgentGraph Production Database Restore ===${NC}"
echo ""
echo -e "  Host:    ${EC2_USER}@${EC2_HOST}"
echo -e "  Backup:  ${BACKUP_FILE}"
echo -e "  Dry run: ${DRY_RUN}"
echo -e "  Confirm: ${CONFIRM}"

if $DRY_RUN; then
  echo ""
  echo -e "${YELLOW}${BOLD}--- DRY RUN MODE ---${NC}"
fi

if ! $DRY_RUN; then
  echo ""
  echo -e "${RED}${BOLD}WARNING: This will DROP and REPLACE the production database.${NC}"
  echo -e "${RED}Make sure you have a recent backup before proceeding.${NC}"
  echo ""
  read -r -p "Type 'RESTORE' to proceed: " ANSWER
  if [ "$ANSWER" != "RESTORE" ]; then
    echo "Aborted."
    exit 1
  fi
fi

# --- Step 1: Verify connectivity and resolve backup file ---
step "Verifying connectivity and locating backup"
if $DRY_RUN; then
  info "Would SSH to ${EC2_HOST} and verify backup file exists"
  if [ "$BACKUP_FILE" = "__latest__" ]; then
    info "Would find the most recent backup in ${BACKUP_DIR}/"
  fi
else
  remote "echo ok" > /dev/null 2>&1 || fail "Cannot SSH to ${EC2_HOST}"
  ok "SSH connection verified"

  if [ "$BACKUP_FILE" = "__latest__" ]; then
    BACKUP_FILE=$(remote "ls -1t ${BACKUP_DIR}/daily/agentgraph-*.sql.gz ${BACKUP_DIR}/daily/agentgraph-*.dump ${BACKUP_DIR}/agentgraph-*.sql.gz ${BACKUP_DIR}/agentgraph-*.dump 2>/dev/null | head -1" 2>&1)
    if [ -z "$BACKUP_FILE" ]; then
      fail "No backup files found in ${BACKUP_DIR}"
    fi
    ok "Latest backup: ${BACKUP_FILE}"
  else
    # Search for the file in known locations
    RESOLVED=$(remote "
      for dir in '${BACKUP_DIR}/daily' '${BACKUP_DIR}/weekly' '${BACKUP_DIR}'; do
        if [ -f \"\${dir}/${BACKUP_FILE}\" ]; then
          echo \"\${dir}/${BACKUP_FILE}\"
          exit 0
        fi
      done
      # Try as absolute path
      if [ -f '${BACKUP_FILE}' ]; then
        echo '${BACKUP_FILE}'
        exit 0
      fi
    " 2>&1)
    if [ -z "$RESOLVED" ]; then
      fail "Backup file '${BACKUP_FILE}' not found. Use --list to see available backups."
    fi
    BACKUP_FILE="$RESOLVED"
    ok "Found: ${BACKUP_FILE}"
  fi

  # Show file details
  FILE_INFO=$(remote "ls -lh '${BACKUP_FILE}'" 2>&1)
  info "File: ${FILE_INFO}"
fi

# Determine restore method based on file extension
if [[ "$BACKUP_FILE" == *.sql.gz ]]; then
  RESTORE_METHOD="psql"
elif [[ "$BACKUP_FILE" == *.dump ]]; then
  RESTORE_METHOD="pg_restore"
else
  RESTORE_METHOD="psql"
  warn "Unknown extension — defaulting to psql (plain SQL)"
fi

# --- Step 2: Get PG_USER from environment ---
step "Reading PostgreSQL credentials"
if $DRY_RUN; then
  info "Would read POSTGRES_USER from docker container environment"
  PG_USER="(from POSTGRES_USER env var)"
else
  PG_USER=$(remote "cd ~/${PROJECT_DIR} && sudo docker exec ${CONTAINER_PG} bash -c 'echo \$POSTGRES_USER'" 2>&1)
  if [ -z "$PG_USER" ]; then
    PG_USER="agentgraph"
    warn "Could not read POSTGRES_USER, defaulting to '${PG_USER}'"
  else
    ok "PostgreSQL user: ${PG_USER}"
  fi
fi

# --- Step 3: Create pre-restore backup ---
step "Creating pre-restore safety backup"
if $DRY_RUN; then
  info "Would dump current database to ${BACKUP_DIR}/pre-restore-*.sql.gz"
else
  PRE_RESTORE="pre-restore-$(date +%Y%m%d-%H%M%S).sql.gz"
  remote "mkdir -p ${BACKUP_DIR} && sudo docker exec ${CONTAINER_PG} pg_dump -U '${PG_USER}' -d '${PG_DB}' --no-owner --no-acl | gzip > '${BACKUP_DIR}/${PRE_RESTORE}'" 2>&1 || fail "Could not create pre-restore backup"
  PRE_SIZE=$(remote "du -h '${BACKUP_DIR}/${PRE_RESTORE}' | cut -f1" 2>&1)
  ok "Pre-restore backup saved: ${BACKUP_DIR}/${PRE_RESTORE} (${PRE_SIZE})"
fi

# --- Step 4: Stop backend container ---
step "Stopping backend container"
if $DRY_RUN; then
  info "Would run: docker-compose -f ${COMPOSE_FILE} stop backend"
else
  remote "cd ~/${PROJECT_DIR} && sudo docker-compose -f ${COMPOSE_FILE} stop backend" 2>&1 | while IFS= read -r line; do
    info "$line"
  done
  ok "Backend stopped (postgres still running)"
fi

# --- Step 5: Restore database ---
step "Restoring database from backup (method: ${RESTORE_METHOD})"
if $DRY_RUN; then
  if [ "$RESTORE_METHOD" = "psql" ]; then
    info "Would run: gunzip < backup | docker exec -i postgres psql -U user -d agentgraph"
  else
    info "Would run: docker exec pg_restore -U user -d agentgraph --clean --if-exists < backup"
  fi
else
  # Drop and recreate database to ensure clean restore
  info "Dropping and recreating database..."
  remote "sudo docker exec ${CONTAINER_PG} psql -U '${PG_USER}' -d postgres -c \"
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${PG_DB}' AND pid <> pg_backend_pid();
  \" 2>/dev/null || true" > /dev/null 2>&1

  remote "sudo docker exec ${CONTAINER_PG} psql -U '${PG_USER}' -d postgres -c 'DROP DATABASE IF EXISTS ${PG_DB};'" 2>&1 || fail "Could not drop database"
  remote "sudo docker exec ${CONTAINER_PG} psql -U '${PG_USER}' -d postgres -c 'CREATE DATABASE ${PG_DB} OWNER ${PG_USER};'" 2>&1 || fail "Could not create database"
  ok "Database dropped and recreated"

  info "Loading backup data..."
  if [ "$RESTORE_METHOD" = "psql" ]; then
    remote "gunzip -c '${BACKUP_FILE}' | sudo docker exec -i ${CONTAINER_PG} psql -U '${PG_USER}' -d '${PG_DB}' --quiet" 2>&1 | tail -5 || fail "psql restore failed"
  else
    # For custom format dumps, copy into container then pg_restore
    remote "sudo docker cp '${BACKUP_FILE}' ${CONTAINER_PG}:/tmp/restore.dump && sudo docker exec ${CONTAINER_PG} pg_restore -U '${PG_USER}' -d '${PG_DB}' --no-owner --no-acl --clean --if-exists /tmp/restore.dump && sudo docker exec ${CONTAINER_PG} rm -f /tmp/restore.dump" 2>&1 | tail -5 || fail "pg_restore failed"
  fi
  ok "Database restored from backup"
fi

# --- Step 6: Run Alembic migrations ---
step "Running Alembic migrations (upgrade head)"
if $DRY_RUN; then
  info "Would run: docker-compose exec backend python -m alembic upgrade head"
else
  # Start backend briefly to run migrations
  remote "cd ~/${PROJECT_DIR} && sudo docker-compose -f ${COMPOSE_FILE} start backend" 2>&1 | while IFS= read -r line; do
    info "$line"
  done
  sleep 3

  MIGRATION_OUT=$(remote "cd ~/${PROJECT_DIR} && sudo docker-compose -f ${COMPOSE_FILE} exec -T backend python -m alembic upgrade head" 2>&1)
  echo "$MIGRATION_OUT" | while IFS= read -r line; do
    info "$line"
  done
  ok "Alembic migrations applied"
fi

# --- Step 7: Restart backend ---
step "Restarting backend"
if $DRY_RUN; then
  info "Would restart backend container"
else
  remote "cd ~/${PROJECT_DIR} && sudo docker-compose -f ${COMPOSE_FILE} restart backend" 2>&1 | while IFS= read -r line; do
    info "$line"
  done
  ok "Backend restarted"
fi

# --- Step 8: Health check ---
step "Waiting for backend health"
if $DRY_RUN; then
  info "Would poll /health for up to 30s"
else
  HEALTHY=false
  for i in $(seq 1 15); do
    if remote "curl -sf --max-time 3 http://localhost/health" > /dev/null 2>&1; then
      HEALTHY=true
      break
    fi
    info "Attempt $i/15 — waiting 2s..."
    sleep 2
  done
  if $HEALTHY; then
    ok "Backend is healthy"
  else
    fail "Backend not healthy after restore. Check logs: ssh ${EC2_HOST} 'cd ~/${PROJECT_DIR} && docker-compose -f ${COMPOSE_FILE} logs backend --tail 50'"
  fi
fi

# --- Step 9: Verify login ---
step "Verifying login works"
if $DRY_RUN; then
  info "Would test login with admin credentials"
else
  ADMIN_EMAIL="${ADMIN_EMAIL:?Set ADMIN_EMAIL env var}"
  ADMIN_PASSWORD="${ADMIN_PASSWORD:?Set ADMIN_PASSWORD env var}"
  LOGIN_STATUS=$(remote "curl -sf -o /dev/null -w '%{http_code}' --max-time 10 http://localhost/api/v1/auth/login -H 'Content-Type: application/json' -d '{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}'" 2>&1)
  if [ "$LOGIN_STATUS" = "200" ]; then
    ok "Admin login successful"
  else
    warn "Login returned HTTP ${LOGIN_STATUS} — verify manually"
  fi
fi

# --- Done ---
echo ""
if $DRY_RUN; then
  echo -e "${YELLOW}${BOLD}=== Dry run complete ===${NC}"
  echo ""
  echo "To actually restore, run:"
  echo "  $0 --confirm ${BACKUP_FILE}"
else
  echo -e "${GREEN}${BOLD}=== Restore successful ===${NC}"
  echo ""
  echo -e "  Restored from: ${BACKUP_FILE}"
  echo -e "  Pre-restore backup: ${BACKUP_DIR}/${PRE_RESTORE}"
  echo ""
  echo -e "${YELLOW}To undo this restore, run:${NC}"
  echo -e "  $0 --confirm ${BACKUP_DIR}/${PRE_RESTORE}"
fi
