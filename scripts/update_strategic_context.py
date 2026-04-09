"""Push strategic context to Redis for marketing bot consumption.

Usage:
    python3 scripts/update_strategic_context.py
    python3 scripts/update_strategic_context.py path/to/context.md

Reads from data/marketing_strategic_context.md by default.
Writes to Redis key: marketing:strategic_context
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

DEFAULT_PATH = Path("data/marketing_strategic_context.md")


async def main() -> None:
    # Determine source file
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = DEFAULT_PATH

    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    content = path.read_text()

    # Load secrets for Redis connection
    secrets_path = Path(__file__).resolve().parent.parent / ".env.secrets"
    if secrets_path.exists():
        for line in secrets_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                import os
                os.environ.setdefault(key.strip(), val.strip().strip("'\""))

    # Push to Redis
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.redis_client import get_redis

    r = get_redis()
    await r.set("marketing:strategic_context", content)
    print(f"Pushed {len(content)} bytes to Redis key: marketing:strategic_context")
    print(f"Source: {path}")


if __name__ == "__main__":
    asyncio.run(main())
