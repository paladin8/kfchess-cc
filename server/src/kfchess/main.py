"""FastAPI application entry point."""

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from kfchess.api.router import api_router
from kfchess.settings import get_settings
from kfchess.ws.handler import handle_websocket


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
    logger.info(f"Starting Kung Fu Chess server (dev_mode={settings.dev_mode})")

    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    # TODO: Register server with Redis for game distribution

    yield

    # Shutdown
    logger.info("Shutting down Kung Fu Chess server")
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
