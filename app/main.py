from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database.pool import close_pool, init_pool
from app.routers import auth, clubs, events, fixtures, lineups, live, media, news, players, standings, tournaments


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


settings = get_settings()

app = FastAPI(
    title="Crimax Sports API",
    description="League management API for Crimax Sports",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clubs.router)
app.include_router(players.router)
app.include_router(tournaments.router)
app.include_router(fixtures.router)
app.include_router(lineups.router)
app.include_router(events.router)
app.include_router(standings.router)
app.include_router(news.router)
app.include_router(media.router)
app.include_router(live.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "crimax-sports-api"}
