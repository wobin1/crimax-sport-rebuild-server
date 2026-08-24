#!/usr/bin/env python3
"""
Applies pending SQL migrations from sql/ and records them in schema_migrations.
Usage: python scripts/migrate.py [--status]

Flags:
  --status   List applied and pending migrations without changing anything.

The API applies migrations on startup too (AUTO_MIGRATE, default on); this is
the entry point for deploy pipelines that run them as a separate step.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from dotenv import load_dotenv

from app.database.migrator import discover_migrations, run_migrations

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set.")
    sys.exit(1)


async def show_status(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT to_regclass('schema_migrations')")
        applied = (
            {
                row["version"]: row["applied_at"]
                for row in await conn.fetch(
                    "SELECT version, applied_at FROM schema_migrations"
                )
            }
            if exists
            else {}
        )

    for version, filename in discover_migrations():
        when = applied.get(version)
        stamp = when.strftime("%Y-%m-%d %H:%M") if when else "pending"
        print(f"  {version}  {filename:<32} {stamp}")


async def main() -> None:
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=2)
    try:
        if "--status" in sys.argv:
            await show_status(pool)
            return

        ran = await run_migrations(pool)
        print(f"Done. {ran} migration(s) applied." if ran else "Already up to date.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
