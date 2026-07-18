#!/usr/bin/env python3
"""
Applies the database schema (sql/schema.sql) to the target database.
Usage: python scripts/apply_schema.py [--seed]

Flags:
  --seed   Also run 002_seed.sql to insert the default admin user.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "sql", "schema.sql")
SEED_PATH = os.path.join(BASE_DIR, "app", "database", "migrations", "002_seed.sql")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set.")
    sys.exit(1)


async def run_sql_file(conn: asyncpg.Connection, path: str) -> None:
    with open(path, "r") as f:
        sql = f.read()
    await conn.execute(sql)
    print(f"Applied: {os.path.basename(path)}")


async def main() -> None:
    seed = "--seed" in sys.argv

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        print("Applying schema…")
        await run_sql_file(conn, SCHEMA_PATH)

        if seed:
            print("Seeding default admin…")
            await run_sql_file(conn, SEED_PATH)

        print("\nDone.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
