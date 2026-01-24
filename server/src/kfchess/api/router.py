"""Main API router."""

from fastapi import APIRouter

from kfchess.api.games import router as games_router
from kfchess.api.lobbies import router as lobbies_router
from kfchess.api.replays import router as replays_router
from kfchess.auth import get_auth_router

api_router = APIRouter()
api_router.include_router(games_router)
api_router.include_router(lobbies_router)
api_router.include_router(replays_router)
api_router.include_router(get_auth_router())
