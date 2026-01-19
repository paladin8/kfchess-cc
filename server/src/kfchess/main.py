"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kfchess.settings import get_settings


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


# TODO: Include API routers
# from kfchess.api.router import api_router
# app.include_router(api_router, prefix="/api")

# TODO: WebSocket endpoint
# from kfchess.ws.handlers import websocket_endpoint
# app.add_api_websocket_route("/ws", websocket_endpoint)
