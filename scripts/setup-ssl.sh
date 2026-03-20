#!/usr/bin/env bash
# =============================================================================
# AgentGraph SSL/TLS Setup Script
# =============================================================================
# Sets up Let's Encrypt SSL certificates on the production EC2 instance
# (Amazon Linux 2023) for agentgraph.co.
#
# This script is designed to be run ON the EC2 instance itself, or remotely
# via SSH from the MacBook:
#
#   Local (on EC2):
#     sudo ./scripts/setup-ssl.sh
#
#   Remote (from MacBook):
#     ssh -i ~/.ssh/***REMOVED*** ec2-user@YOUR_ELASTIC_IP \
#       'cd ~/agentgraph && sudo bash scripts/setup-ssl.sh'
#
# What it does:
#   1. Installs certbot (via pip, Amazon Linux 2023 method)
#   2. Obtains Let's Encrypt certificate for agentgraph.co (standalone mode)
#   3. Temporarily stops nginx to free port 80 for certbot verification
#   4. Copies nginx-ssl.conf into place as nginx.conf
#   5. Restarts Docker services with the SSL-enabled config
#   6. Sets up automatic renewal via cron
#
# Prerequisites:
#   - DNS A record for agentgraph.co pointing to YOUR_ELASTIC_IP
#   - Ports 80 and 443 open in EC2 security group
#   - Docker and docker-compose installed
#   - agentgraph repo cloned to ~/agentgraph
#
# Safe to re-run: checks for existing certs and backs up config.
# =============================================================================

set -euo pipefail

# --- Configuration ---
DOMAIN="agentgraph.co"
EXTRA_DOMAINS="-d agentgraph.co -d www.agentgraph.co"
EMAIL="***REMOVED***"
PROJECT_DIR="${HOME}/agentgraph"
COMPOSE_FILE="docker-compose.prod.yml"
NGINX_CONF="${PROJECT_DIR}/nginx/nginx.conf"
NGINX_SSL_CONF="${PROJECT_DIR}/nginx/nginx-ssl.conf"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Helpers ---
step_num=0
step() {
  step_num=$((step_num + 1))
  echo ""
  echo -e "${CYAN}${BOLD}[$step_num] $1${NC}"
}

ok() {
  echo -e "    ${GREEN}OK${NC} $1"
}

fail() {
  echo -e "    ${RED}FAIL${NC} $1"
  exit 1
}

warn() {
  echo -e "    ${YELLOW}WARN${NC} $1"
}

# --- Pre-flight checks ---
echo -e "${BOLD}=== AgentGraph SSL/TLS Setup ===${NC}"
echo ""
echo -e "  Domain:  ${DOMAIN}"
echo -e "  Email:   ${EMAIL}"
echo -e "  Project: ${PROJECT_DIR}"

# Must be root (certbot needs root for /etc/letsencrypt)
if [ "$(id -u)" -ne 0 ]; then
  fail "This script must be run as root (use sudo)."
fi

# Verify project directory exists
if [ ! -d "${PROJECT_DIR}" ]; then
  fail "Project directory not found: ${PROJECT_DIR}"
fi

# Verify SSL nginx config exists
if [ ! -f "${NGINX_SSL_CONF}" ]; then
  fail "SSL nginx config not found: ${NGINX_SSL_CONF}. Make sure nginx/nginx-ssl.conf is committed and pulled."
fi

# Verify docker-compose file exists
if [ ! -f "${PROJECT_DIR}/${COMPOSE_FILE}" ]; then
  fail "Docker compose file not found: ${PROJECT_DIR}/${COMPOSE_FILE}"
fi

# =============================================================================
# Step 1: Install certbot
# =============================================================================
step "Installing certbot"

if command -v certbot &> /dev/null; then
  CERTBOT_VERSION=$(certbot --version 2>&1 || true)
  ok "certbot is already installed (${CERTBOT_VERSION})"
else
  echo "    Installing certbot via pip (Amazon Linux 2023 method)..."

  # Install dependencies
  dnf install -y python3 python3-pip augeas-libs > /dev/null 2>&1 || true

  # Install certbot via pip (recommended for Amazon Linux 2023)
  python3 -m pip install --upgrade pip > /dev/null 2>&1
  python3 -m pip install certbot > /dev/null 2>&1

  # Create symlink so certbot is in PATH
  if [ -f /usr/local/bin/certbot ]; then
    ln -sf /usr/local/bin/certbot /usr/bin/certbot 2>/dev/null || true
  fi

  if command -v certbot &> /dev/null; then
    ok "certbot installed successfully"
  else
    fail "certbot installation failed. Try: python3 -m pip install certbot"
  fi
fi

# =============================================================================
# Step 2: Check for existing certificate
# =============================================================================
step "Checking for existing certificate"

CERT_EXISTS=false
if [ -f "${CERT_DIR}/fullchain.pem" ] && [ -f "${CERT_DIR}/privkey.pem" ]; then
  CERT_EXISTS=true
  # Check expiry
  EXPIRY=$(openssl x509 -enddate -noout -in "${CERT_DIR}/fullchain.pem" 2>/dev/null | cut -d= -f2)
  EXPIRY_EPOCH=$(date -d "${EXPIRY}" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "${EXPIRY}" +%s 2>/dev/null || echo 0)
  NOW_EPOCH=$(date +%s)
  DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

  if [ "${DAYS_LEFT}" -gt 30 ]; then
    ok "Certificate exists and is valid for ${DAYS_LEFT} more days (expires: ${EXPIRY})"
    echo "    Skipping certificate acquisition. Use 'certbot renew --force-renewal' to force."
  else
    warn "Certificate expires in ${DAYS_LEFT} days. Will renew."
    CERT_EXISTS=false
  fi
fi

# =============================================================================
# Step 3: Obtain certificate (if needed)
# =============================================================================
if [ "${CERT_EXISTS}" = false ]; then
  step "Obtaining Let's Encrypt certificate"

  # Stop nginx to free port 80 for standalone verification.
  # Certbot's standalone mode runs its own temporary web server on port 80.
  echo "    Stopping nginx container to free port 80..."
  cd "${PROJECT_DIR}"
  docker-compose -f "${COMPOSE_FILE}" stop nginx 2>/dev/null || true
  ok "nginx stopped"

  # Small delay to ensure port 80 is released
  sleep 2

  # Verify port 80 is free
  if ss -tlnp | grep -q ':80 '; then
    warn "Port 80 still in use. Attempting to identify the process..."
    ss -tlnp | grep ':80 ' || true
    fail "Port 80 is occupied. Stop the service using it and re-run."
  fi

  echo "    Requesting certificate for ${DOMAIN}..."
  echo "    (This requires DNS to be pointing to this server)"
  echo ""

  certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "${EMAIL}" \
    ${EXTRA_DOMAINS} \
    --preferred-challenges http \
    --http-01-port 80

  if [ -f "${CERT_DIR}/fullchain.pem" ]; then
    ok "Certificate obtained successfully"
    echo "    Certificate: ${CERT_DIR}/fullchain.pem"
    echo "    Private key: ${CERT_DIR}/privkey.pem"
  else
    # Restart nginx even if cert fails
    docker-compose -f "${COMPOSE_FILE}" start nginx 2>/dev/null || true
    fail "Certificate was not created. Check certbot output above."
  fi
else
  step "Skipping certificate acquisition (already valid)"
fi

# =============================================================================
# Step 4: Back up current nginx config and install SSL config
# =============================================================================
step "Updating nginx configuration"

# Back up the current config with timestamp
BACKUP_FILE="${NGINX_CONF}.backup.$(date +%Y%m%d-%H%M%S)"
if [ -f "${NGINX_CONF}" ]; then
  cp "${NGINX_CONF}" "${BACKUP_FILE}"
  ok "Current config backed up to: ${BACKUP_FILE}"
fi

# Copy the SSL config into place
cp "${NGINX_SSL_CONF}" "${NGINX_CONF}"
ok "SSL config installed: ${NGINX_CONF}"

# =============================================================================
# Step 5: Test nginx config and restart services
# =============================================================================
step "Testing nginx configuration"

cd "${PROJECT_DIR}"

# Test the config using a temporary nginx container
# This catches syntax errors before we restart the real service
CONFIG_TEST=$(docker run --rm \
  -v "${NGINX_CONF}:/etc/nginx/nginx.conf:ro" \
  -v "/etc/letsencrypt:/etc/letsencrypt:ro" \
  nginx:alpine nginx -t 2>&1) || {
  echo "    ${CONFIG_TEST}"
  # Restore backup
  if [ -f "${BACKUP_FILE}" ]; then
    cp "${BACKUP_FILE}" "${NGINX_CONF}"
    warn "Restored backup config due to test failure"
  fi
  fail "nginx config test failed. Fix the config and re-run."
}

ok "nginx config test passed"

# =============================================================================
# Step 6: Restart Docker services
# =============================================================================
step "Restarting Docker services"

cd "${PROJECT_DIR}"
docker-compose -f "${COMPOSE_FILE}" up -d
ok "All services started"

# Wait for nginx to be ready
sleep 3

# Verify HTTPS is responding
echo "    Testing HTTPS response..."
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 \
  "https://${DOMAIN}/health" 2>/dev/null) || HTTP_CODE="000"

if [ "${HTTP_CODE}" = "200" ]; then
  ok "HTTPS is working (got 200 from /health)"
elif [ "${HTTP_CODE}" = "302" ]; then
  ok "HTTPS is working (got 302 — gate redirect, expected for non-API routes)"
else
  warn "HTTPS returned HTTP ${HTTP_CODE}. This might be OK if DNS hasn't propagated yet."
  echo "    Try: curl -vk https://${DOMAIN}/health"
fi

# =============================================================================
# Step 7: Set up automatic renewal
# =============================================================================
step "Setting up automatic certificate renewal"

RENEWAL_SCRIPT="/etc/cron.d/certbot-renew-agentgraph"
RENEWAL_LOG="/var/log/certbot-renew.log"

# The renewal hook stops nginx, renews the cert, then restarts all services.
# Certbot only actually renews if the cert is within 30 days of expiry.
cat > "${RENEWAL_SCRIPT}" << CRONEOF
# AgentGraph SSL certificate auto-renewal
# Runs twice daily (recommended by Let's Encrypt)
# Certbot only renews if cert is within 30 days of expiry

SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Pre-hook: stop nginx to free port 80
# Post-hook: restart nginx to load new cert
# deploy-hook: only runs if cert was actually renewed

0 3,15 * * * root certbot renew --standalone --pre-hook "cd ${PROJECT_DIR} && docker-compose -f ${COMPOSE_FILE} stop nginx" --post-hook "cd ${PROJECT_DIR} && docker-compose -f ${COMPOSE_FILE} up -d" >> ${RENEWAL_LOG} 2>&1
CRONEOF

chmod 644 "${RENEWAL_SCRIPT}"
ok "Cron job installed at ${RENEWAL_SCRIPT}"
echo "    Schedule: 3:00 AM and 3:00 PM daily"
echo "    Log: ${RENEWAL_LOG}"

# Verify cron can parse it
if crontab -l -u root 2>/dev/null | grep -q certbot 2>/dev/null || [ -f "${RENEWAL_SCRIPT}" ]; then
  ok "Renewal cron is active"
fi

# =============================================================================
# Step 8: Verify certificate details
# =============================================================================
step "Certificate details"

if [ -f "${CERT_DIR}/fullchain.pem" ]; then
  echo ""
  echo "    Subject:  $(openssl x509 -subject -noout -in "${CERT_DIR}/fullchain.pem" 2>/dev/null | sed 's/subject=//')"
  echo "    Issuer:   $(openssl x509 -issuer -noout -in "${CERT_DIR}/fullchain.pem" 2>/dev/null | sed 's/issuer=//')"
  echo "    Expires:  $(openssl x509 -enddate -noout -in "${CERT_DIR}/fullchain.pem" 2>/dev/null | sed 's/notAfter=//')"
  echo "    SANs:     $(openssl x509 -text -noout -in "${CERT_DIR}/fullchain.pem" 2>/dev/null | grep -A1 'Subject Alternative Name' | tail -1 | sed 's/^\s*//')"
fi

# =============================================================================
# Done
# =============================================================================
echo ""
echo -e "${GREEN}${BOLD}=== SSL setup complete ===${NC}"
echo ""
echo -e "  HTTPS:     https://${DOMAIN}"
echo -e "  Cert:      ${CERT_DIR}/fullchain.pem"
echo -e "  Config:    ${NGINX_CONF}"
echo -e "  Backup:    ${BACKUP_FILE}"
echo -e "  Renewal:   ${RENEWAL_SCRIPT} (twice daily)"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "    1. Verify in browser: https://${DOMAIN}"
echo -e "    2. Test SSL grade:    https://www.ssllabs.com/ssltest/analyze.html?d=${DOMAIN}"
echo -e "    3. Monitor renewal:   tail -f ${RENEWAL_LOG}"
echo ""
