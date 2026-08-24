from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
import asyncpg

from app.core.dependencies import get_managed_club_ids, require_admin, require_super_admin
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.match_rules import evaluate_clock
from app.core.pagination import PaginationParams, get_pagination
from app.core.policy import enforce_policy
from app.core.rate_limit import client_key, limiter
from app.core.rulesets import resolve_ruleset
from app.core.websocket import manager
from app.database.pool import get_conn
from app.queries import audit as aq
from app.queries import events as eq
from app.queries import external_ids as xid
from app.queries import fixtures as q
from app.queries import tournaments as tq
from app.schemas.audit import AuditEntryOut
from app.schemas.fixtures import ClockUpdate, FixtureCreate, FixtureOut, FixtureUpdate
from app.schemas.pagination import Paginated, paginated

router = APIRouter(prefix="/fixtures", tags=["fixtures"])

MATCH_DATA_SCHEMA_VERSION = "1.0.0"


@router.get("", response_model=Paginated[FixtureOut])
async def list_fixtures(
    tournament_id: str | None = Query(None),
    status: str | None = Query(None),
    round: str | None = Query(None),
    date: str | None = Query(None),
    club_id: str | None = Query(None),
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_fixtures(
        conn,
        tournament_id=tournament_id,
        status=status,
        round=round,
        date=date,
        club_id=club_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/live", response_model=Paginated[FixtureOut])
async def list_live_fixtures(
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_live_fixtures(
        conn, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/{fixture_id}", response_model=FixtureOut)
async def get_fixture(fixture_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    fixture = await q.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    return fixture


@router.get("/{fixture_id}/export")
async def export_fixture(
    fixture_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_admin),
):
    """Canonical match timeline for interchange / dispute review."""
    fixture = await q.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")

    managed = await get_managed_club_ids(current_user, conn)
    clubs = {fixture["home_club"]["id"], fixture["away_club"]["id"]}
    if current_user["role"] == "club_manager" and not clubs.intersection(managed):
        raise ForbiddenError("You do not manage a club in this fixture.")

    events, _ = await eq.get_fixture_events(conn, fixture_id, limit=2000, offset=0)
    audit_items, _ = await aq.get_for_fixture(conn, fixture_id, limit=200, offset=0)
    external = await xid.list_for_entity(conn, "fixture", fixture_id)
    ruleset = resolve_ruleset(
        fixture.get("ruleset_snapshot")
        or await q.get_effective_ruleset(conn, fixture_id)
    )

    return {
        "schema_version": MATCH_DATA_SCHEMA_VERSION,
        "fixture": fixture,
        "ruleset": ruleset.model_dump(mode="json"),
        "events": events,
        "audit_summary": [
            {
                "id": item["id"],
                "action": item["action"],
                "actor_role": item["actor_role"],
                "actor_name": item["actor_name"],
                "reason": item["reason"],
                "created_at": item["created_at"],
            }
            for item in audit_items
        ],
        "external_ids": external,
    }


@router.get("/{fixture_id}/audit", response_model=Paginated[AuditEntryOut])
async def get_fixture_audit(
    fixture_id: str,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_admin),
):
    fixture = await q.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    managed_clubs = await get_managed_club_ids(current_user, conn)
    fixture_clubs = {fixture["home_club"]["id"], fixture["away_club"]["id"]}
    if current_user["role"] == "club_manager" and not fixture_clubs.intersection(
        managed_clubs
    ):
        raise ForbiddenError("You do not manage a club in this fixture.")
    items, total = await aq.get_for_fixture(
        conn,
        fixture_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.post("", response_model=FixtureOut, status_code=201)
async def create_fixture(
    payload: FixtureCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    data = payload.model_dump()
    if not data.get("tournament_id"):
        current = await tq.get_current_tournament(conn)
        if not current:
            raise HTTPException(status_code=400, detail="No active tournament found. Create or mark a tournament as current first.")
        data["tournament_id"] = current["id"]
    return await q.create_fixture(conn, data)


@router.patch("/{fixture_id}", response_model=FixtureOut)
async def update_fixture(
    fixture_id: str,
    payload: FixtureUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_super_admin),
    request_id: str | None = Header(None, alias="X-Request-ID"),
):
    async with conn.transaction():
        if not await q.lock_fixture(conn, fixture_id):
            raise NotFoundError("Fixture")
        before = await q.get_fixture_by_id(conn, fixture_id)
        update_data = payload.model_dump(exclude_none=True)
        if update_data.get("status") in ("live", "completed"):
            raise BadRequestError(
                "Use the match clock controls to start or complete a fixture."
            )
        fixture = await q.update_fixture(
            conn, fixture_id, update_data
        )
        if not fixture:
            raise NotFoundError("Fixture")
        await aq.record(
            conn,
            actor=current_user,
            action="fixture.update",
            entity_type="fixture",
            entity_id=fixture_id,
            fixture_id=fixture_id,
            before_data=before,
            after_data=fixture,
            request_id=request_id,
        )

    # Sync live viewers when status/period change via fixtures admin.
    await manager.broadcast(
        fixture_id,
        {"type": "clock_update", "fixture": fixture},
    )
    return fixture


@router.post("/{fixture_id}/clock", response_model=FixtureOut)
async def update_clock(
    fixture_id: str,
    payload: ClockUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_admin),
    request_id: str | None = Header(None, alias="X-Request-ID"),
):
    """Admin match-clock controls: Start 1H / HT / Start 2H / FT / nudge / stoppage."""
    limiter.hit(client_key(request, "clock"), limit=60, window_seconds=60)
    try:
        async with conn.transaction():
            if not await q.lock_fixture(conn, fixture_id):
                raise NotFoundError("Fixture")
            before = await q.get_fixture_by_id(conn, fixture_id)
            ruleset = resolve_ruleset(
                await q.get_effective_ruleset(conn, fixture_id)
            )
            evaluation = evaluate_clock(payload.action.value, before, ruleset)
            overridden = enforce_policy(
                evaluation,
                actor=current_user,
                acknowledged_warnings=payload.acknowledged_warnings,
                override=payload.override,
                override_reason=payload.override_reason,
            )
            if before.get("ruleset_snapshot") is None:
                await q.snapshot_ruleset(
                    conn, fixture_id, ruleset.model_dump(mode="json")
                )
            fixture = await q.apply_clock_action(
                conn,
                fixture_id,
                action=payload.action.value,
                minute=payload.minute,
                stoppage_minutes=payload.stoppage_minutes,
            )
            if not fixture:
                raise NotFoundError("Fixture")
            await aq.record(
                conn,
                actor=current_user,
                action=f"clock.{payload.action.value}",
                entity_type="fixture",
                entity_id=fixture_id,
                fixture_id=fixture_id,
                before_data=before,
                after_data=fixture,
                ruleset=ruleset.model_dump(mode="json"),
                request_id=request_id,
            )
            if overridden:
                await aq.record(
                    conn,
                    actor=current_user,
                    action="policy.override",
                    entity_type="fixture",
                    entity_id=fixture_id,
                    fixture_id=fixture_id,
                    after_data={
                        "decisions": [
                            {
                                "level": decision.level,
                                "code": decision.code,
                                "message": decision.message,
                            }
                            for decision in overridden
                        ],
                        "clock_action": payload.action.value,
                    },
                    reason=payload.override_reason.strip(),
                    ruleset=ruleset.model_dump(mode="json"),
                    request_id=request_id,
                )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    await manager.broadcast(
        fixture_id,
        {"type": "clock_update", "fixture": fixture},
    )
    return fixture


@router.delete("/{fixture_id}", status_code=204)
async def delete_fixture(
    fixture_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    deleted = await q.delete_fixture(conn, fixture_id)
    if not deleted:
        raise NotFoundError("Fixture")
