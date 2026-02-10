"""FastAPI application entry point."""

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from kfchess.api.router import api_router
from kfchess.auth.rate_limit import limiter
from kfchess.settings import get_settings
from kfchess.ws.handler import handle_websocket
from kfchess.ws.lobby_handler import handle_lobby_websocket
from kfchess.ws.replay_handler import handle_replay_websocket


def setup_logging() -> None:
    """Configure logging for the application."""
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set specific loggers
    logging.getLogger("kfchess").setLevel(logging.DEBUG)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


# Set up logging on import
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    settings = get_settings()
    server_id = settings.effective_server_id
    logger.info(f"Starting Kung Fu Chess server (dev_mode={settings.dev_mode}, server_id={server_id})")

    # Clean up stale active game entries from previous runs
    try:
        from kfchess.db.repositories.active_games import ActiveGameRepository
        from kfchess.db.session import async_session_factory

        async with async_session_factory() as session:
            repo = ActiveGameRepository(session)
            cleaned = await repo.cleanup_by_server(server_id)
            if cleaned:
                logger.info(f"Cleaned up {cleaned} stale active game entries from previous run")
            stale = await repo.cleanup_stale(max_age_hours=2)
            if stale:
                logger.info(f"Cleaned up {stale} globally stale active game entries")
            await session.commit()
    except Exception:
        logger.exception("Failed to clean up stale active games on startup")

    # Connect to Redis, start heartbeat, and restore games from snapshots
    try:
        from kfchess.redis.client import get_redis
        from kfchess.redis.heartbeat import is_server_alive, start_heartbeat
        from kfchess.redis.routing import register_game_routing
        from kfchess.redis.snapshot_store import list_snapshot_game_ids, load_snapshot
        from kfchess.services.game_registry import register_game_fire_and_forget
        from kfchess.services.game_service import get_game_service

        r = await get_redis()
        await start_heartbeat(r, server_id)

        # Restore games from Redis snapshots whose owning server is dead.
        # This works for both single-server crash recovery (our own previous
        # PID died, heartbeat expired) and multi-server failover (another
        # server died, we claim its orphaned games).
        # NOTE: Phase 5 will add atomic CAS on game:{id}:server to prevent
        # two servers from claiming the same game during simultaneous restarts.
        game_ids = await list_snapshot_game_ids(r)
        game_service = get_game_service()
        restored = 0
        for gid in game_ids:
            snapshot = await load_snapshot(r, gid)
            if snapshot is None:
                continue
            # Skip games owned by a server that is still alive
            if snapshot.server_id and await is_server_alive(r, snapshot.server_id):
                continue
            if game_service.restore_game(snapshot):
                restored += 1
                # Re-register in active_games so restored games appear in live list
                managed = game_service.get_managed_game(gid)
                if managed is not None:
                    state = managed.state
                    players_info = []
                    for pnum, pid in state.players.items():
                        is_ai = pnum in managed.ai_players
                        name = pid.split(":", 1)[1] if ":" in pid else pid
                        if is_ai:
                            name = f"Bot ({name})"
                        players_info.append(
                            {"slot": pnum, "username": name, "is_ai": is_ai}
                        )
                    game_type = "campaign" if snapshot.campaign_level_id else "restored"
                    register_game_fire_and_forget(
                        game_id=gid,
                        game_type=game_type,
                        speed=state.speed.value,
                        player_count=len(state.players),
                        board_type=state.board.board_type.value,
                        players=players_info,
                        campaign_level_id=snapshot.campaign_level_id,
                    )
                    # Register routing key pointing to us (claiming the game)
                    await register_game_routing(r, gid, server_id)
        if restored:
            logger.info(f"Restored {restored} games from Redis snapshots")

        # Clean up stale lobbies from previous runs
        from kfchess.lobby.manager import get_lobby_manager

        lobby_manager = get_lobby_manager()
        stale_lobbies = await lobby_manager.cleanup_stale_lobbies()
        if stale_lobbies:
            logger.info(f"Cleaned up {stale_lobbies} stale lobbies from Redis")
    except Exception:
        logger.exception("Failed to initialize Redis / restore games on startup")

    yield

    # Shutdown
    logger.info("Shutting down Kung Fu Chess server")

    # Stop heartbeat and close Redis
    try:
        from kfchess.redis.client import close_redis
        from kfchess.redis.heartbeat import stop_heartbeat

        await stop_heartbeat()
        await close_redis()
    except Exception:
        logger.exception("Failed to shut down Redis on shutdown")

    try:
        from kfchess.db.repositories.active_games import ActiveGameRepository
        from kfchess.db.session import async_session_factory

        async with async_session_factory() as session:
            repo = ActiveGameRepository(session)
            await repo.cleanup_by_server(server_id)
            await session.commit()
    except Exception:
        logger.exception("Failed to clean up active games on shutdown")


app = FastAPI(
    title="Kung Fu Chess",
    description="Real-time multiplayer chess API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
# In dev mode, allow localhost. In production, allow the configured frontend URL.
settings = get_settings()
cors_origins = (
    ["http://localhost:5173", "http://127.0.0.1:5173"]
    if settings.dev_mode
    else [settings.frontend_url]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Kung Fu Chess API", "version": "0.1.0"}


# Include API routers
app.include_router(api_router, prefix="/api")


# WebSocket endpoint for lobby real-time communication
@app.websocket("/ws/lobby/{code}")
async def lobby_websocket_endpoint(
    websocket: WebSocket,
    code: str,
    player_key: str,
) -> None:
    """WebSocket endpoint for lobby real-time communication."""
    await handle_lobby_websocket(websocket, code, player_key)


# WebSocket endpoint for live games
@app.websocket("/ws/game/{game_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    game_id: str,
    player_key: str | None = None,
) -> None:
    """WebSocket endpoint for real-time game communication."""
    await handle_websocket(websocket, game_id, player_key)


# WebSocket endpoint for replay playback
@app.websocket("/ws/replay/{game_id}")
async def replay_websocket_endpoint(
    websocket: WebSocket,
    game_id: str,
) -> None:
    """WebSocket endpoint for replay playback."""
    await handle_replay_websocket(websocket, game_id)
