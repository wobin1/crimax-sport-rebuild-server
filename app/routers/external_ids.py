from fastapi import APIRouter, Depends, Query
import asyncpg

from app.core.dependencies import require_super_admin
from app.core.exceptions import NotFoundError
from app.database.pool import get_conn
from app.queries import audit as aq
from app.queries import external_ids as q
from app.schemas.external_ids import ExternalIdCreate, ExternalIdOut

router = APIRouter(prefix="/external-ids", tags=["external-ids"])


@router.get("", response_model=list[ExternalIdOut])
async def list_external_ids(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    return await q.list_for_entity(conn, entity_type, entity_id)


@router.put("", response_model=ExternalIdOut)
async def upsert_external_id(
    payload: ExternalIdCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_super_admin),
):
    async with conn.transaction():
        mapping = await q.upsert(
            conn,
            entity_type=payload.entity_type.value,
            entity_id=payload.entity_id,
            provider=payload.provider,
            external_id=payload.external_id,
        )
        await aq.record(
            conn,
            actor=current_user,
            action="external_id.upsert",
            entity_type=payload.entity_type.value,
            entity_id=payload.entity_id,
            after_data=mapping,
        )
    return mapping


@router.delete("", status_code=204)
async def delete_external_id(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
    provider: str = Query(...),
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_super_admin),
):
    async with conn.transaction():
        deleted = await q.delete(
            conn,
            entity_type=entity_type,
            entity_id=entity_id,
            provider=provider,
        )
        if not deleted:
            raise NotFoundError("External ID")
        await aq.record(
            conn,
            actor=current_user,
            action="external_id.delete",
            entity_type=entity_type,
            entity_id=entity_id,
            after_data={"provider": provider},
        )
