#!/usr/bin/env bash
# AgentGraph Production Deployment Script
set -euo pipefail

echo "=== AgentGraph Production Deployment ==="
echo ""

# Check prerequisites
if [ ! -f .env.production ]; then
    echo "ERROR: .env.production not found. Copy from .env.production.template and fill in values."
    exit 1
fi

if [ ! -f nginx/htpasswd ]; then
    echo "ERROR: nginx/htpasswd not found."
    echo "Create with: htpasswd -Bc nginx/htpasswd agentgraph"
    exit 1
fi

echo "1. Pulling latest images..."
docker compose -f docker-compose.prod.yml pull 2>/dev/null || true

echo ""
echo "2. Building frontend..."
docker compose -f docker-compose.prod.yml --profile build run --rm frontend-builder

echo ""
echo "3. Starting services..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "4. Waiting for services to start..."
sleep 5

echo ""
echo "5. Health check..."
if curl -sf --max-time 5 http://localhost/health > /dev/null 2>&1; then
    echo "  [OK] Backend is healthy"
else
    echo "  [WARN] Backend health check failed — check logs with: docker compose -f docker-compose.prod.yml logs backend"
fi

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Next steps:"
echo "  - Set up SSL: certbot certonly --webroot -w /var/www/certbot -d agentgraph.io"
echo "  - View logs: docker compose -f docker-compose.prod.yml logs -f"
echo "  - Stop: docker compose -f docker-compose.prod.yml down"
