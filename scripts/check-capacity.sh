#!/usr/bin/env bash
# =============================================================================
# AgentGraph — Production Capacity Check
# =============================================================================
# Reports memory, CPU, disk, swap, and Docker container stats from EC2.
# Run from your local machine (Mac Mini or MacBook).
#
# Usage:
#   ./scripts/check-capacity.sh              # Full report via SSH
#   ./scripts/check-capacity.sh --local      # Run directly on EC2 (no SSH)
# =============================================================================

set -euo pipefail

EC2_HOST="${AG_EC2_HOST:?Set AG_EC2_HOST env var (e.g. your Elastic IP)}"
EC2_USER="ec2-user"
SSH_KEY="${AG_SSH_KEY:?Set AG_SSH_KEY env var (path to your SSH key)}"
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"
PROJECT_DIR="agentgraph"
COMPOSE_FILE="docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

LOCAL_MODE=false
if [[ "${1:-}" == "--local" ]]; then
    LOCAL_MODE=true
fi

# Run command either locally or via SSH
run() {
    if $LOCAL_MODE; then
        eval "$1"
    else
        ssh $SSH_OPTS "${EC2_USER}@${EC2_HOST}" "$1"
    fi
}

echo -e "${BOLD}=== AgentGraph Production Capacity Report ===${NC}"
echo -e "  Instance: t3.small (2 vCPU, 2GB RAM)"
echo -e "  Host:     ${EC2_HOST}"
echo -e "  Time:     $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

# --- System Memory ---
echo -e "${CYAN}${BOLD}[1] System Memory${NC}"
run "free -h" 2>/dev/null | while IFS= read -r line; do
    echo "    $line"
done
echo ""

# --- Swap ---
echo -e "${CYAN}${BOLD}[2] Swap Status${NC}"
SWAP_TOTAL=$(run "free -m | awk '/^Swap:/ {print \$2}'" 2>/dev/null || echo "0")
if [[ "$SWAP_TOTAL" == "0" ]]; then
    echo -e "    ${YELLOW}[WARN] No swap configured!${NC}"
    echo "    Run these commands on EC2 to add 2GB swap:"
    echo "      sudo fallocate -l 2G /swapfile"
    echo "      sudo chmod 600 /swapfile"
    echo "      sudo mkswap /swapfile"
    echo "      sudo swapon /swapfile"
    echo "      echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab"
    echo "      sudo sysctl vm.swappiness=10"
else
    echo -e "    ${GREEN}[OK]${NC} Swap: ${SWAP_TOTAL}MB configured"
fi
echo ""

# --- CPU Load ---
echo -e "${CYAN}${BOLD}[3] CPU Load${NC}"
LOAD=$(run "cat /proc/loadavg" 2>/dev/null || echo "N/A")
echo "    Load avg: $LOAD"
UPTIME=$(run "uptime -p" 2>/dev/null || echo "N/A")
echo "    Uptime:   $UPTIME"
echo ""

# --- Disk Usage ---
echo -e "${CYAN}${BOLD}[4] Disk Usage${NC}"
run "df -h / /var/lib/docker 2>/dev/null || df -h /" 2>/dev/null | while IFS= read -r line; do
    echo "    $line"
done
echo ""

# --- Docker Container Stats (snapshot) ---
echo -e "${CYAN}${BOLD}[5] Docker Container Stats${NC}"
run "docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.PIDs}}'" 2>/dev/null | while IFS= read -r line; do
    echo "    $line"
done
echo ""

# --- Container Health Status ---
echo -e "${CYAN}${BOLD}[6] Container Health${NC}"
run "cd ~/${PROJECT_DIR} && docker-compose -f ${COMPOSE_FILE} ps" 2>/dev/null | while IFS= read -r line; do
    echo "    $line"
done
echo ""

# --- Docker Volumes (disk usage) ---
echo -e "${CYAN}${BOLD}[7] Docker Volume Sizes${NC}"
run "docker system df -v 2>/dev/null | sed -n '/VOLUME/,/^$/p' | head -10" 2>/dev/null | while IFS= read -r line; do
    echo "    $line"
done
echo ""

# --- Health Endpoint ---
echo -e "${CYAN}${BOLD}[8] Health Endpoint${NC}"
HEALTH=$(run "curl -sf --max-time 5 http://localhost/health" 2>/dev/null || echo "UNREACHABLE")
if [[ "$HEALTH" == "UNREACHABLE" ]]; then
    echo -e "    ${RED}[FAIL]${NC} Health endpoint unreachable"
else
    echo -e "    ${GREEN}[OK]${NC} $HEALTH"
fi
echo ""

# --- OOM Kill Check ---
echo -e "${CYAN}${BOLD}[9] Recent OOM Kills${NC}"
OOM_COUNT=$(run "dmesg 2>/dev/null | grep -ci 'oom\|out of memory' || echo 0" 2>/dev/null || echo "N/A")
if [[ "$OOM_COUNT" == "0" || "$OOM_COUNT" == "N/A" ]]; then
    echo -e "    ${GREEN}[OK]${NC} No OOM kills detected"
else
    echo -e "    ${RED}[WARN]${NC} $OOM_COUNT OOM-related messages in dmesg"
    echo "    Consider upgrading to t3.medium or adding swap."
fi
echo ""

# --- Capacity Assessment ---
echo -e "${CYAN}${BOLD}[10] Capacity Assessment${NC}"
MEM_AVAIL=$(run "awk '/MemAvailable/ {print \$2}' /proc/meminfo" 2>/dev/null || echo "0")
MEM_AVAIL_MB=$((MEM_AVAIL / 1024))
echo "    Available memory: ${MEM_AVAIL_MB}MB"

if [[ $MEM_AVAIL_MB -lt 200 ]]; then
    echo -e "    ${RED}[CRITICAL]${NC} Less than 200MB free. Upgrade to t3.medium NOW."
    echo ""
    echo "    Upgrade command (2 min downtime):"
    echo "      aws ec2 stop-instances --instance-ids YOUR_INSTANCE_ID"
    echo "      aws ec2 modify-instance-attribute --instance-id YOUR_INSTANCE_ID --instance-type '{\"Value\":\"t3.medium\"}'"
    echo "      aws ec2 start-instances --instance-ids YOUR_INSTANCE_ID"
elif [[ $MEM_AVAIL_MB -lt 400 ]]; then
    echo -e "    ${YELLOW}[WARN]${NC} Under 400MB free. Watch closely during traffic surge."
    echo "    If memory drops below 200MB, upgrade to t3.medium."
else
    echo -e "    ${GREEN}[OK]${NC} Sufficient headroom for 50-200 concurrent users."
fi

echo ""
echo -e "${BOLD}=== Report Complete ===${NC}"
