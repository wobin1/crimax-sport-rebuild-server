from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.logging_middleware import RequestContextMiddleware
from app.database.migrator import run_migrations
from app.database.pool import close_pool, get_pool, init_pool
from app.routers import (
    auth,
    clubs,
    events,
    external_ids,
    fixtures,
    lineups,
    live,
    media,
    news,
    players,
    standings,
    tournaments,
    users,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    if get_settings().auto_migrate:
        await run_migrations(get_pool())
    yield
    await close_pool()


settings = get_settings()

app = FastAPI(
    title="Crimax Sports API",
    description="League management API for Crimax Sports",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _problem(
    *,
    status_code: int,
    title: str,
    detail,
    type_: str = "about:blank",
    headers: dict | None = None,
    extensions: dict | None = None,
) -> JSONResponse:
    body = {
        "type": type_,
        "title": title,
        "status": status_code,
        "detail": detail,
        # Transition compatibility for existing frontend parsers.
        "message": detail if isinstance(detail, str) else None,
    }
    if isinstance(detail, dict):
        # Keep structured detail intact (e.g. policy_decision) while also
        # exposing a flat message for simple clients.
        body["detail"] = detail
        message = detail.get("message")
        body["message"] = message if isinstance(message, str) else None
        for key in ("type", "level", "code", "can_override"):
            if key in detail:
                body[key] = detail[key]
    if extensions:
        body.update(extensions)
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    title = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        429: "Too Many Requests",
    }.get(exc.status_code, "HTTP Error")
    return _problem(
        status_code=exc.status_code,
        title=title,
        detail=exc.detail,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    return _problem(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Validation Error",
        detail=exc.errors(),
        type_="https://docs.crimax.ng/problems/validation-error",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logging.getLogger("crimax.api").exception(
        "unhandled_exception",
        extra={"request_id": request_id, "path": request.url.path},
    )
    return _problem(
        status_code=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
        extensions={"request_id": request_id},
    )


def _register_routers(target: FastAPI, *, prefix: str = "") -> None:
    routers = [
        auth.router,
        users.router,
        clubs.router,
        players.router,
        tournaments.router,
        fixtures.router,
        lineups.router,
        events.router,
        standings.router,
        news.router,
        media.router,
        live.router,
        external_ids.router,
    ]
    for router in routers:
        target.include_router(router, prefix=prefix)


# Canonical versioned surface.
_register_routers(app, prefix="/v1")
# Temporary unversioned aliases for existing clients.
_register_routers(app)


@app.get("/health", tags=["health"])
@app.get("/v1/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "crimax-sports-api"}


@app.get("/ready", tags=["health"])
@app.get("/v1/ready", tags=["health"])
async def ready(response: Response):
    """Readiness probe — confirms the API can reach PostgreSQL."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval("SELECT 1")
        if value != 1:
            raise RuntimeError("Unexpected database response")
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "unavailable",
            "detail": str(exc),
        }
