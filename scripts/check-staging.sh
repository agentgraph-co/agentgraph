#!/usr/bin/env bash
# Quick health check for staging environment.
# Verifies backend, frontend, and login all work.
# Usage: ./scripts/check-staging.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ok() { echo -e "${GREEN}OK${NC}  $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; ERRORS=$((ERRORS+1)); }

ERRORS=0

# Backend health
if curl -sf -o /dev/null http://***REMOVED***:8001/docs; then
  ok "Staging backend (:8001) is up"
else
  fail "Staging backend (:8001) is DOWN"
fi

# Frontend health
if curl -sf -o /dev/null http://***REMOVED***:5174/; then
  ok "Staging frontend (:5174) is up"
else
  fail "Staging frontend (:5174) is DOWN"
fi

# Login test
LOGIN=$(python3 -c "
import httpx, asyncio, sys
async def t():
    try:
        async with httpx.AsyncClient(base_url='http://localhost:8001', timeout=5) as c:
            import os
            email = os.environ.get('ADMIN_EMAIL', 'admin@agentgraph.co')
            pw = os.environ.get('ADMIN_PASSWORD', '')
            if not pw:
                print('SKIP')
                return
            r = await c.post('/api/v1/auth/login', json={'email': email, 'password': pw})
            print('OK' if r.status_code == 200 else f'FAIL:{r.status_code}')
    except Exception as e:
        print(f'FAIL:{e}')
asyncio.run(t())
" 2>&1)

if [ "$LOGIN" = "OK" ] || [ "$LOGIN" = "SKIP" ]; then
  ok "Login works"
else
  fail "Login broken: $LOGIN"
fi

# Feed data
FEED=$(python3 -c "
import httpx, asyncio
async def t():
    async with httpx.AsyncClient(base_url='http://localhost:8001', timeout=5) as c:
        import os
        email = os.environ.get('ADMIN_EMAIL', 'admin@agentgraph.co')
        pw = os.environ.get('ADMIN_PASSWORD', '')
        if not pw:
            print('0')
            return
        r = await c.post('/api/v1/auth/login', json={'email': email, 'password': pw})
        token = r.json()['access_token']
        f = await c.get('/api/v1/feed/posts?limit=5', headers={'Authorization': f'Bearer {token}'})
        print(len(f.json().get('posts', [])))
asyncio.run(t())
" 2>&1)

if [ "$FEED" -gt 0 ] 2>/dev/null; then
  ok "Feed has data ($FEED posts)"
else
  fail "Feed is empty or broken"
fi

echo ""
if [ $ERRORS -eq 0 ]; then
  echo -e "${GREEN}All staging checks passed.${NC}"
else
  echo -e "${RED}$ERRORS check(s) failed.${NC}"
  exit 1
fi
