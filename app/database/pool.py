import logging
import ssl
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

_SQLALCHEMY_PREFIXES = (
    "postgresql+asyncpg://",
    "postgres+asyncpg://",
    "postgresql+psycopg://",
    "postgres+psycopg://",
    "postgresql+psycopg2://",
    "postgres+psycopg2://",
)

_DROP_QUERY_KEYS = {
    "ssl",
    "sslmode",
    "channel_binding",
    "sslrootcert",
    "sslcert",
    "sslkey",
}


def pool_connect_args(database_url: str) -> dict:
    """Turn a hosted Postgres URL into asyncpg create_pool kwargs.

    FastAPI Cloud / Neon / Render / Supabase URLs often include libpq-only
    params (`sslmode`, `channel_binding`) or a SQLAlchemy driver prefix.
    asyncpg rejects those, which crashes startup and fails verification.
    """
    dsn = database_url.strip()
    for prefix in _SQLALCHEMY_PREFIXES:
        if dsn.startswith(prefix):
            scheme = "postgresql://" if prefix.startswith("postgresql") else "postgres://"
            dsn = scheme + dsn[len(prefix) :]
            break

    parsed = urlparse(dsn)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = (query.get("sslmode") or query.get("ssl") or "").lower()
    for key in list(query):
        if key.lower() in _DROP_QUERY_KEYS:
            query.pop(key, None)

    clean_dsn = urlunparse(parsed._replace(query=urlencode(query)))
    host = (parsed.hostname or "").lower()
    local = host in {"localhost", "127.0.0.1", "::1", ""}

    if sslmode in {"disable", "allow"}:
        needs_ssl = False
    elif sslmode in {"require", "verify-ca", "verify-full", "true", "1"}:
        needs_ssl = True
    else:
        needs_ssl = not local

    kwargs: dict = {
        "dsn": clean_dsn,
        "min_size": 1,
        "max_size": 10,
        "timeout": 30,
        "command_timeout": 60,
    }
    if needs_ssl:
        ctx = ssl.create_default_context()
        # sslmode=require encrypts without custom CA verification (Neon/Render).
        if sslmode not in {"verify-ca", "verify-full"}:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl"] = ctx
    return kwargs


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    connect_args = pool_connect_args(settings.database_url)
    logger.info(
        "database_pool_connecting ssl=%s",
        bool(connect_args.get("ssl")),
    )
    _pool = await asyncpg.create_pool(**connect_args)


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised.")
    return _pool


async def get_conn():
    """FastAPI dependency — yields a single connection from the pool."""
    async with get_pool().acquire() as conn:
        yield conn
