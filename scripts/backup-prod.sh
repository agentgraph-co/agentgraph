#!/usr/bin/env bash
# ============================================================================
# AgentGraph Production Database Backup
# ============================================================================
# Connects to EC2 and creates a compressed pg_dump of the production database.
# Keeps the last 7 daily backups and deletes older ones.
#
# Usage:
#   ./scripts/backup-prod.sh
#
# Cron (daily at 3:00 AM — add to MacBook crontab):
#   0 3 * * * /Users/kserver/projects/agentgraph/scripts/backup-prod.sh >> /tmp/agentgraph-backup.log 2>&1
#
# ============================================================================

set -euo pipefail

EC2_HOST="***REMOVED***"
EC2_USER="ec2-user"
SSH_KEY="$HOME/.ssh/***REMOVED***"
BACKUP_DIR="/home/ec2-user/backups"
CONTAINER="agentgraph-postgres-1"
PG_USER="agentgraph"
PG_PASSWORD="${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD env var}"
PG_DB="agentgraph"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
BACKUP_FILE="agentgraph-${TIMESTAMP}.sql.gz"
KEEP_DAYS=7

echo "=== AgentGraph Production Backup ==="
echo "Timestamp: ${TIMESTAMP}"
echo ""

ssh -i "${SSH_KEY}" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" bash -s <<REMOTE_SCRIPT
set -euo pipefail

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

echo "Running pg_dump inside container ${CONTAINER}..."
docker exec -e PGPASSWORD="${PG_PASSWORD}" "${CONTAINER}" \
    pg_dump -U "${PG_USER}" -d "${PG_DB}" --no-owner --no-acl \
    | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"

echo "Backup saved: ${BACKUP_DIR}/${BACKUP_FILE}"

# Show backup file size
FILESIZE=\$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "Backup size: \${FILESIZE}"

# Clean up old backups — keep only the last ${KEEP_DAYS}
echo ""
echo "Cleaning up old backups (keeping last ${KEEP_DAYS})..."
cd "${BACKUP_DIR}"
ls -1t agentgraph-*.sql.gz 2>/dev/null | tail -n +$((${KEEP_DAYS} + 1)) | while read -r old; do
    echo "  Removing: \${old}"
    rm -f "\${old}"
done

# Show remaining backups
echo ""
echo "Current backups:"
ls -lh "${BACKUP_DIR}"/agentgraph-*.sql.gz 2>/dev/null || echo "  (none)"
REMOTE_SCRIPT

echo ""
echo "=== Backup complete ==="
