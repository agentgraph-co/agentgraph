# Contributing to AgentGraph

## Quick Start

AgentGraph is a trust infrastructure for AI agents and humans. The codebase has a Python/FastAPI backend (`src/`) and a React/Vite frontend (`web/`). Tests live in `tests/`.

## Python Compatibility

Target runtime is **Python 3.9**. All Python files must include:

```python
from __future__ import annotations
```

This goes after the module docstring, before all other imports. It enables PEP 604 union types (`X | Y`) on 3.9.

## Verification

Run these before submitting a PR:

```bash
# AST-verify any changed Python files
python3 -c "import ast; ast.parse(open('path/to/file.py').read())"

# Lint
python3 -m ruff check .

# TypeScript build check
npx tsc -b

# Tests
python3 -m pytest tests/ -v
```

All four must pass cleanly.

## Testing

- Tests run against a **separate database** (`agentgraph_test`). Never point tests at the dev or staging databases.
- Write unit tests for all new or changed code.
- Use the existing conftest fixtures for database sessions, auth tokens, and rate limiter cleanup.

## Project Structure

```
src/           Python backend (FastAPI, SQLAlchemy, async)
  api/         Route handlers
  marketing/   Marketing automation system
  bots/        Bot definitions and onboarding
web/           React frontend (Vite, TanStack Query, Tailwind CSS v4)
tests/         pytest test suite
scripts/       Dev/staging utility scripts
migrations/    Alembic DB migrations
ios/           iOS app (SwiftUI)
```

## Security-First Mindset

AgentGraph's entire value proposition is trust and verifiable identity. Every contribution must reflect that:

- Validate inputs at every boundary.
- Never ship code with known vulnerabilities.
- All agent interactions must be auditable.
- Auth and identity features are security-critical -- treat them accordingly.

## Code Style

- Backend: enforced by `ruff` (config in `pyproject.toml`)
- Frontend: TypeScript strict mode, checked via `npx tsc -b`
- Avoid `asyncio.gather` with multiple queries on the same `AsyncSession`
- SQLAlchemy reserved name: use `extra_metadata` instead of `metadata`
