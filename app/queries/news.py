import asyncpg
import re
from typing import Optional


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


_NEWS_SELECT = """
    SELECT
        n.id::text,
        n.title,
        n.slug,
        n.content,
        n.excerpt,
        n.image_url,
        n.author_id::text,
        u.full_name   AS author_name,
        n.is_published,
        n.published_at::text,
        n.created_at::text,
        n.updated_at::text
    FROM news n
    LEFT JOIN users u ON u.id = n.author_id
"""


async def get_all_news(
    conn: asyncpg.Connection,
    published_only: bool = True,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    where = "WHERE n.is_published = TRUE" if published_only else ""
    total = await conn.fetchval(f"SELECT COUNT(*) FROM news n {where}")
    rows = await conn.fetch(
        f"{_NEWS_SELECT} {where} ORDER BY n.published_at DESC NULLS LAST LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [dict(r) for r in rows], int(total or 0)


async def get_news_by_slug(conn: asyncpg.Connection, slug: str) -> Optional[dict]:
    row = await conn.fetchrow(f"{_NEWS_SELECT} WHERE n.slug = $1", slug)
    return dict(row) if row else None


async def get_news_by_id(conn: asyncpg.Connection, news_id: str) -> Optional[dict]:
    row = await conn.fetchrow(f"{_NEWS_SELECT} WHERE n.id = $1", news_id)
    return dict(row) if row else None


async def create_news(conn: asyncpg.Connection, data: dict, author_id: str) -> dict:
    base_slug = _slugify(data["title"])
    slug = base_slug
    counter = 1
    while await conn.fetchval("SELECT 1 FROM news WHERE slug = $1", slug):
        slug = f"{base_slug}-{counter}"
        counter += 1

    from datetime import datetime, timezone
    published_at = datetime.now(timezone.utc) if data.get("is_published") else None

    row = await conn.fetchrow(
        """
        INSERT INTO news (title, slug, content, excerpt, image_url, author_id, is_published, published_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id::text
        """,
        data["title"],
        slug,
        data["content"],
        data.get("excerpt"),
        data.get("image_url"),
        author_id,
        data.get("is_published", False),
        published_at,
    )
    return await get_news_by_id(conn, row["id"])


async def update_news(conn: asyncpg.Connection, news_id: str, data: dict) -> Optional[dict]:
    current = await get_news_by_id(conn, news_id)
    if not current:
        return None

    fields = {k: v for k, v in data.items() if v is not None}

    if fields.get("is_published") is True and not current["is_published"]:
        from datetime import datetime, timezone
        fields["published_at"] = datetime.now(timezone.utc)

    if not fields:
        return current

    set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())

    await conn.execute(
        f"UPDATE news SET {set_clauses} WHERE id = $1",
        news_id,
        *values,
    )
    return await get_news_by_id(conn, news_id)


async def delete_news(conn: asyncpg.Connection, news_id: str) -> bool:
    result = await conn.execute("DELETE FROM news WHERE id = $1", news_id)
    return result == "DELETE 1"
