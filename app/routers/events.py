from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
import asyncpg

from app.core.dependencies import assert_club_access, get_current_user
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.match_rules import evaluate_event, evaluate_event_deletion
from app.core.pagination import PaginationParams, get_pagination
from app.core.policy import enforce_policy
from app.core.rate_limit import client_key, limiter
from app.core.rulesets import resolve_ruleset
from app.core.websocket import manager
from app.database.pool import get_conn
from app.queries import audit as aq
from app.queries import events as q
from app.queries import fixtures as fq
from app.schemas.events import EventCreate, EventOut
from app.schemas.pagination import Paginated, paginated

router = APIRouter(prefix="/events", tags=["events"])


def _same_event(existing: dict, requested: dict) -> bool:
    fields = (
        "fixture_id",
        "player_id",
        "club_id",
        "event_type",
        "minute",
        "extra_time_minute",
        "description",
    )
    return all(existing.get(field) == requested.get(field) for field in fields)


@router.get("/fixture/{fixture_id}", response_model=Paginated[EventOut])
async def list_fixture_events(
    fixture_id: str,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    items, total = await q.get_fixture_events(
        conn, fixture_id, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.post("", response_model=EventOut, status_code=201)
async def create_event(
    payload: EventCreate,
    request: Request,
    response: Response,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    request_id: str | None = Header(None, alias="X-Request-ID"),
):
    limiter.hit(client_key(request, "event-create"), limit=60, window_seconds=60)
    data = payload.model_dump(mode="json")
    if idempotency_key is not None and not 1 <= len(idempotency_key) <= 64:
        raise BadRequestError("Idempotency-Key must be between 1 and 64 characters.")
    if idempotency_key and data.get("client_event_id"):
        if idempotency_key != data["client_event_id"]:
            raise ConflictError("Idempotency-Key does not match client_event_id.")
    data["client_event_id"] = idempotency_key or data.get("client_event_id")

    replayed = False
    async with conn.transaction():
        if not await fq.lock_fixture(conn, payload.fixture_id):
            raise NotFoundError("Fixture")

        fixture = await fq.get_fixture_by_id(conn, payload.fixture_id)
        await assert_club_access(payload.club_id, current_user, conn)
        fixture_clubs = {
            fixture["home_club"]["id"],
            fixture["away_club"]["id"],
        }
        if payload.club_id not in fixture_clubs:
            raise BadRequestError("The selected club is not part of this fixture.")
        if payload.player_id and not await q.player_belongs_to_club(
            conn, payload.player_id, payload.club_id
        ):
            raise BadRequestError("The selected player does not belong to this club.")

        event = None
        if data["client_event_id"]:
            event = await q.get_event_by_client_id(
                conn, payload.fixture_id, data["client_event_id"]
            )
            if event:
                if not _same_event(event, data):
                    raise ConflictError(
                        "This idempotency key was already used for a different event."
                    )
                replayed = True

        if not replayed:
            if fixture["status"] not in ("live", "scheduled", "completed"):
                raise BadRequestError(
                    "Cannot add events to a postponed or cancelled fixture."
                )

            existing_events, _ = await q.get_fixture_events(
                conn, payload.fixture_id, limit=1000, offset=0
            )
            ruleset = resolve_ruleset(
                await fq.get_effective_ruleset(conn, payload.fixture_id)
            )
            evaluation = evaluate_event(data, fixture, existing_events, ruleset)
            overridden = enforce_policy(
                evaluation,
                actor=current_user,
                acknowledged_warnings=payload.acknowledged_warnings,
                override=payload.override,
                override_reason=payload.override_reason,
            )

            if fixture.get("ruleset_snapshot") is None:
                await fq.snapshot_ruleset(
                    conn, payload.fixture_id, ruleset.model_dump(mode="json")
                )

            # First event kicks the match live so public /live surfaces pick it up.
            if fixture["status"] == "scheduled":
                await fq.update_fixture(conn, payload.fixture_id, {"status": "live"})

            event_data = {
                key: value
                for key, value in data.items()
                if key
                not in ("acknowledged_warnings", "override", "override_reason")
            }
            event = await q.create_event(conn, event_data)
            if event is None:
                raise ConflictError("Could not safely create this event.")
            committed_events = [event]
            if evaluation.auto_red:
                auto_red = await q.create_event(
                    conn,
                    {
                        **event_data,
                        "client_event_id": None,
                        "source_event_id": event["id"],
                        "event_type": "red_card",
                        "description": "Automatic red card after second yellow.",
                    },
                )
                if auto_red:
                    committed_events.append(auto_red)
            home_score, away_score = await q.recalculate_score(conn, payload.fixture_id)
            updated = await fq.get_fixture_by_id(conn, payload.fixture_id)
            await aq.record(
                conn,
                actor=current_user,
                action="event.create",
                entity_type="match_event",
                entity_id=event["id"],
                fixture_id=payload.fixture_id,
                club_id=payload.club_id,
                after_data={
                    "events": committed_events,
                    "score": {"home": home_score, "away": away_score},
                },
                ruleset=ruleset.model_dump(mode="json"),
                request_id=request_id,
            )
            if overridden:
                await aq.record(
                    conn,
                    actor=current_user,
                    action="policy.override",
                    entity_type="match_event",
                    entity_id=event["id"],
                    fixture_id=payload.fixture_id,
                    club_id=payload.club_id,
                    after_data={
                        "decisions": [
                            {
                                "level": decision.level,
                                "code": decision.code,
                                "message": decision.message,
                            }
                            for decision in overridden
                        ],
                        "event": event,
                    },
                    reason=payload.override_reason.strip(),
                    ruleset=ruleset.model_dump(mode="json"),
                    request_id=request_id,
                )

    if replayed:
        response.status_code = status.HTTP_200_OK
        return event

    for committed_event in committed_events:
        await manager.broadcast(
            str(payload.fixture_id),
            {
                "type": "event",
                "event": committed_event,
                "score": {"home": home_score, "away": away_score},
                "status": updated["status"],
                "fixture": updated,
            },
        )

    return event


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    acknowledged_warning: str | None = Query(None, max_length=100),
    override: bool = Query(False),
    override_reason: str | None = Query(None, max_length=500),
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
    request_id: str | None = Header(None, alias="X-Request-ID"),
):
    async with conn.transaction():
        event = await conn.fetchrow(
            """
            SELECT id::text, fixture_id::text, client_event_id,
                   source_event_id::text, player_id::text,
                   club_id::text, event_type::text, minute, extra_time_minute,
                   description, created_at::text
            FROM match_events
            WHERE id = $1
            """,
            event_id,
        )
        if not event:
            raise NotFoundError("Event")

        if not await fq.lock_fixture(conn, event["fixture_id"]):
            raise NotFoundError("Fixture")
        event = await conn.fetchrow(
            """
            SELECT id::text, fixture_id::text, client_event_id,
                   source_event_id::text, player_id::text,
                   club_id::text, event_type::text, minute, extra_time_minute,
                   description, created_at::text
            FROM match_events
            WHERE id = $1
            """,
            event_id,
        )
        if not event:
            raise NotFoundError("Event")

        await assert_club_access(event["club_id"], current_user, conn)
        fixture = await fq.get_fixture_by_id(conn, event["fixture_id"])
        ruleset = resolve_ruleset(
            await fq.get_effective_ruleset(conn, event["fixture_id"])
        )
        evaluation = evaluate_event_deletion(fixture, ruleset)
        overridden = enforce_policy(
            evaluation,
            actor=current_user,
            acknowledged_warnings=(
                [acknowledged_warning] if acknowledged_warning else []
            ),
            override=override,
            override_reason=override_reason,
        )
        await q.delete_event(conn, event_id)
        home_score, away_score = await q.recalculate_score(conn, event["fixture_id"])
        updated = await fq.get_fixture_by_id(conn, event["fixture_id"])
        await aq.record(
            conn,
            actor=current_user,
            action="event.delete",
            entity_type="match_event",
            entity_id=event_id,
            fixture_id=event["fixture_id"],
            club_id=event["club_id"],
            before_data={
                "event": dict(event),
                "score_after_delete": {"home": home_score, "away": away_score},
            },
            ruleset=ruleset.model_dump(mode="json"),
            request_id=request_id,
        )
        if overridden:
            await aq.record(
                conn,
                actor=current_user,
                action="policy.override",
                entity_type="match_event",
                entity_id=event_id,
                fixture_id=event["fixture_id"],
                club_id=event["club_id"],
                before_data={"event": dict(event)},
                after_data={
                    "decisions": [
                        {
                            "level": decision.level,
                            "code": decision.code,
                            "message": decision.message,
                        }
                        for decision in overridden
                    ],
                    "deleted": True,
                },
                reason=override_reason.strip(),
                ruleset=ruleset.model_dump(mode="json"),
                request_id=request_id,
            )

    await manager.broadcast(
        str(event["fixture_id"]),
        {
            "type": "score_update",
            "score": {"home": home_score, "away": away_score},
            "fixture": updated,
        },
    )
