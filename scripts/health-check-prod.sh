#!/usr/bin/env bash
# Production health check script
set -euo pipefail

BASE_URL="${1:-https://localhost}"
EXIT_CODE=0

check() {
    local name="$1" url="$2"
    if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
        echo "  [OK] $name"
    else
        echo "  [FAIL] $name"
        EXIT_CODE=1
    fi
}

echo "=== AgentGraph Health Check ==="
echo ""

# Backend health
echo "Backend:"
check "Health endpoint" "$BASE_URL/health"
check "API ping" "$BASE_URL/api/v1/ping"

# SSL certificate (if HTTPS)
if [[ "$BASE_URL" == https://* ]]; then
    echo ""
    echo "SSL:"
    DOMAIN=$(echo "$BASE_URL" | sed 's|https://||' | cut -d/ -f1)
    EXPIRY=$(echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ -n "$EXPIRY" ]; then
        echo "  Certificate expires: $EXPIRY"
        # Warn if expiring within 14 days
        EXPIRY_EPOCH=$(date -j -f "%b %d %H:%M:%S %Y %Z" "$EXPIRY" +%s 2>/dev/null || date -d "$EXPIRY" +%s 2>/dev/null || echo 0)
        NOW_EPOCH=$(date +%s)
        DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
        if [ "$DAYS_LEFT" -lt 14 ]; then
            echo "  [WARN] Certificate expires in $DAYS_LEFT days!"
        else
            echo "  [OK] $DAYS_LEFT days until expiry"
        fi
    else
        echo "  [WARN] Could not check SSL certificate"
    fi
fi

echo ""
exit $EXIT_CODE
