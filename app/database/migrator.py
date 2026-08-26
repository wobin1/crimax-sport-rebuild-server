"""Applies pending SQL migrations from backend/sql/ and records them.

`schema.sql` bootstraps an empty database as version 000. On a database that
already has tables it is recorded without running, because
`CREATE TABLE IF NOT EXISTS` skips existing tables and would miss any column
added by a later migration. The numbered files then run in order; they are
written idempotently, so a hand-migrated database converges on the same state.
"""
import hashlib
import logging
import os
import re

import asyncpg

logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def sql_dir() -> str:
    """Locate sql/ whether the app runs from source or an installed package."""
    env = os.environ.get("SQL_MIGRATIONS_DIR")
    if env:
        return env
    candidates = [
        os.path.join(os.getcwd(), "sql"),
        os.path.join(BACKEND_DIR, "sql"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "schema.sql")):
            return path
    raise RuntimeError(
        "SQL migrations directory not found. Looked in: " + ", ".join(candidates)
    )


BASELINE_VERSION = "000"
BASELINE_FILENAME = "schema.sql"
MIGRATION_FILENAME = re.compile(r"^(\d{3})_.+\.sql$")

# Serialises concurrent workers/instances booting at the same time.
ADVISORY_LOCK_KEY = 8_274_531

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT        PRIMARY KEY,
    filename   TEXT        NOT NULL,
    checksum   TEXT        NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def discover_migrations() -> list[tuple[str, str]]:
    """Return (version, filename) in apply order, baseline schema first."""
    numbered: dict[str, str] = {}
    for filename in os.listdir(sql_dir()):
        match = MIGRATION_FILENAME.match(filename)
        if not match:
            continue
        version = match.group(1)
        if version in numbered:
            raise RuntimeError(
                f"Duplicate migration version {version}: "
                f"{numbered[version]} and {filename}"
            )
        numbered[version] = filename

    return [
        (BASELINE_VERSION, BASELINE_FILENAME),
        *sorted(numbered.items()),
    ]


def _read(filename: str) -> tuple[str, str]:
    with open(os.path.join(sql_dir(), filename), "r") as f:
        sql = f.read()
    return sql, hashlib.sha256(sql.encode()).hexdigest()


async def _has_existing_tables(conn: asyncpg.Connection) -> bool:
    return await conn.fetchval("SELECT to_regclass('public.users')") is not None


async def run_migrations(pool: asyncpg.Pool) -> int:
    """Apply every migration not yet recorded. Returns how many ran."""
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_lock($1)", ADVISORY_LOCK_KEY)
        try:
            await conn.execute(_CREATE_TRACKING_TABLE)
            applied = {
                row["version"]: row["checksum"]
                for row in await conn.fetch(
                    "SELECT version, checksum FROM schema_migrations"
                )
            }

            baseline_only = await _has_existing_tables(conn)

            ran = 0
            for version, filename in discover_migrations():
                sql, checksum = _read(filename)

                if version in applied:
                    # schema.sql legitimately changes with every new migration.
                    if version != BASELINE_VERSION and applied[version] != checksum:
                        logger.warning(
                            "migration_changed_after_apply version=%s file=%s",
                            version,
                            filename,
                        )
                    continue

                skip = version == BASELINE_VERSION and baseline_only
                async with conn.transaction():
                    if not skip:
                        await conn.execute(sql)
                    await conn.execute(
                        """
                        INSERT INTO schema_migrations (version, filename, checksum)
                        VALUES ($1, $2, $3)
                        """,
                        version,
                        filename,
                        checksum,
                    )
                if skip:
                    logger.info("migration_baselined version=%s file=%s", version, filename)
                    continue
                ran += 1
                logger.info("migration_applied version=%s file=%s", version, filename)

            if ran == 0:
                logger.info("migrations_up_to_date count=%d", len(applied))
            return ran
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", ADVISORY_LOCK_KEY)
