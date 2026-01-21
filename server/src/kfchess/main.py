"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from kfchess.api.router import api_router
from kfchess.settings import get_settings
from kfchess.ws.handler import handle_websocket


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    settings = get_settings()
    print(f"Starting Kung Fu Chess server (dev_mode={settings.dev_mode})")

    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    # TODO: Register server with Redis for game distribution

    yield

    # Shutdown
    print("Shutting down Kung Fu Chess server")
    # TODO: Graceful game handoff
    # TODO: Close connections


app = FastAPI(
    title="Kung Fu Chess",
    description="Real-time multiplayer chess API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"] if settings.dev_mode else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# WebSocket endpoint
@app.websocket("/ws/game/{game_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    game_id: str,
    player_key: str | None = None,
) -> None:
    """WebSocket endpoint for real-time game communication."""
    await handle_websocket(websocket, game_id, player_key)
