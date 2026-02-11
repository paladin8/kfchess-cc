"""FastAPI application entry point."""

import logging
import os
import signal
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import FrameType

from fastapi import FastAPI, HTTPException, WebSocket
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
    """Configure logging for the application.

    Log level is controlled by the LOG_LEVEL env var / setting (default: INFO).
    Third-party libraries are kept at WARNING to reduce noise.
    Set LOG_LEVEL=DEBUG for development or troubleshooting.
    """
    settings = get_settings()
    app_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Create formatter — includes server ID for multi-worker disambiguation
    server_id = settings.effective_server_id
    formatter = logging.Formatter(
        f"%(asctime)s [{server_id}] %(name)s %(levelname)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger — WARNING for third-party libraries
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Application logger — uses configured level
    logging.getLogger("kfchess").setLevel(app_level)

    # Uvicorn — INFO for startup messages and access logs
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    # Quiet known noisy libraries even in DEBUG mode
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)


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
        from kfchess.redis.routing import claim_game_routing, register_game_routing
        from kfchess.redis.snapshot_store import list_snapshot_game_ids, load_snapshot
        from kfchess.services.game_registry import register_restored_game
        from kfchess.services.game_service import get_game_service

        r = await get_redis()
        await start_heartbeat(r, server_id)

        # Restore games from Redis snapshots whose owning server is dead.
        # This works for both single-server crash recovery (our own previous
        # PID died, heartbeat expired) and multi-server failover (another
        # server died, we claim its orphaned games).
        # Uses atomic CAS on game:{id}:server to prevent two servers from
        # claiming the same game during simultaneous restarts.
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

            # Atomically claim the routing key from the dead server
            if snapshot.server_id:
                claimed = await claim_game_routing(
                    r, gid, snapshot.server_id, server_id
                )
                if not claimed:
                    logger.info(
                        f"Game {gid} already claimed by another server, skipping"
                    )
                    continue
            else:
                # No owner (empty server_id) — just register directly
                await register_game_routing(r, gid, server_id)

            if game_service.restore_game(snapshot):
                restored += 1
                # Re-register in active_games so restored games appear in live list
                managed = game_service.get_managed_game(gid)
                if managed is not None:
                    register_restored_game(
                        game_id=gid,
                        state=managed.state,
                        ai_player_nums=set(managed.ai_players.keys()),
                        campaign_level_id=snapshot.campaign_level_id,
                    )
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

    # Install SIGTERM handler that sets drain flag before uvicorn's shutdown.
    # This ensures is_draining() returns True when the lifespan shutdown runs.
    original_sigterm = signal.getsignal(signal.SIGTERM)

    def _drain_then_original(signum: int, frame: FrameType | None) -> None:
        from kfchess.drain import set_draining

        set_draining(True)
        if callable(original_sigterm):
            original_sigterm(signum, frame)
        elif original_sigterm == signal.SIG_DFL:
            # Re-raise with default handler
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)

    signal.signal(signal.SIGTERM, _drain_then_original)

    yield

    # Shutdown
    logger.info("Shutting down Kung Fu Chess server")

    # Drain sequence: if SIGTERM was received, write final snapshots and
    # close all connections before the normal shutdown cleanup.
    from kfchess.drain import is_draining

    if is_draining():
        logger.info("Drain mode active — performing graceful drain")
        try:
            from kfchess.game.state import GameStatus
            from kfchess.redis.client import get_redis
            from kfchess.redis.snapshot_store import save_snapshot
            from kfchess.services.game_service import get_game_service
            from kfchess.ws.handler import _build_snapshot, connection_manager
            from kfchess.ws.lobby_handler import close_all_lobby_websockets

            r = await get_redis()
            game_service = get_game_service()

            # 1. Write final snapshots synchronously for all active games
            snapshot_count = 0
            for gid, managed_game in game_service.games.items():
                if managed_game.state.status in (
                    GameStatus.PLAYING,
                    GameStatus.WAITING,
                ):
                    snapshot = _build_snapshot(gid, managed_game)
                    await save_snapshot(r, snapshot)
                    snapshot_count += 1
            if snapshot_count:
                logger.info(f"Saved {snapshot_count} final snapshots")

            # 2. Stop heartbeat (let TTL expire so other servers see us as dead)
            from kfchess.redis.heartbeat import stop_heartbeat

            await stop_heartbeat()
            logger.info("Heartbeat stopped (other servers will detect us as dead)")

            # 3. Close all game WS connections with code 4301.
            #    Routing keys are intentionally LEFT in Redis pointing to this
            #    server. When clients reconnect to another server, that server
            #    will detect our dead heartbeat and CAS-claim the game.
            await connection_manager.close_all(
                code=4301, reason="server shutting down"
            )

            # 4. Close all lobby WS connections.
            #    The finally block in handle_lobby_websocket will mark players
            #    as disconnected in Redis when their WS closes.
            await close_all_lobby_websockets(
                code=4301, reason="server shutting down"
            )

            logger.info("Drain sequence complete")
        except Exception:
            logger.exception("Error during drain sequence")

    # Normal shutdown cleanup (runs whether drain or not)
    try:
        from kfchess.redis.client import close_redis
        from kfchess.redis.heartbeat import stop_heartbeat

        await stop_heartbeat()  # Idempotent — no-op if already stopped during drain
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
    """Health check endpoint.

    Returns 503 during drain mode so nginx stops routing new traffic.
    """
    from kfchess.drain import is_draining

    if is_draining():
        raise HTTPException(status_code=503, detail="Server is draining")
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
