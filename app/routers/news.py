from fastapi import APIRouter, Depends
import asyncpg

from app.core.dependencies import require_super_admin
from app.core.exceptions import NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.database.pool import get_conn
from app.queries import news as q
from app.schemas.news import NewsCreate, NewsOut, NewsUpdate
from app.schemas.pagination import Paginated, paginated

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=Paginated[NewsOut])
async def list_news(
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_all_news(
        conn,
        published_only=True,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/admin/all", response_model=Paginated[NewsOut])
async def list_all_news_admin(
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    items, total = await q.get_all_news(
        conn,
        published_only=False,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/admin/{news_id}", response_model=NewsOut)
async def get_article_admin(
    news_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    article = await q.get_news_by_id(conn, news_id)
    if not article:
        raise NotFoundError("Article")
    return article


@router.get("/{slug}", response_model=NewsOut)
async def get_article(slug: str, conn: asyncpg.Connection = Depends(get_conn)):
    article = await q.get_news_by_slug(conn, slug)
    if not article or not article["is_published"]:
        raise NotFoundError("Article")
    return article


@router.post("", response_model=NewsOut, status_code=201)
async def create_article(
    payload: NewsCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_super_admin),
):
    return await q.create_news(conn, payload.model_dump(), author_id=current_user["id"])


@router.patch("/{news_id}", response_model=NewsOut)
async def update_article(
    news_id: str,
    payload: NewsUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    article = await q.update_news(conn, news_id, payload.model_dump(exclude_none=True))
    if not article:
        raise NotFoundError("Article")
    return article


@router.delete("/{news_id}", status_code=204)
async def delete_article(
    news_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    deleted = await q.delete_news(conn, news_id)
    if not deleted:
        raise NotFoundError("Article")
