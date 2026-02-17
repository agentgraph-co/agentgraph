#!/usr/bin/env bash
set -euo pipefail

echo "=== AgentGraph Development Setup ==="
echo ""

# Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "ERROR: Homebrew not found. Install from https://brew.sh"
    exit 1
fi

# Install PostgreSQL and Redis
echo "Installing PostgreSQL 16 and Redis..."
brew install postgresql@16 redis 2>/dev/null || true

# Start services
echo "Starting database services..."
brew services start postgresql@16
brew services start redis

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
for i in {1..10}; do
    if pg_isready -q 2>/dev/null; then
        break
    fi
    sleep 1
done

# Create database
echo "Creating agentgraph database..."
createdb agentgraph 2>/dev/null || echo "Database already exists"

# Python venv
echo "Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run migrations (if any exist)
if [ -f "alembic.ini" ]; then
    echo "Running database migrations..."
    alembic upgrade head 2>/dev/null || echo "No migrations to run yet"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start developing:"
echo "  source .venv/bin/activate"
echo "  make dev"
echo ""
echo "Other commands:"
echo "  make test       — run tests"
echo "  make lint       — check code style"
echo "  make db-status  — check service status"
