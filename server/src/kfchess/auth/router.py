"""Authentication route registration.

Configures and exports the authentication router with all FastAPI-Users
routes and optional Google OAuth support.
"""

from fastapi import APIRouter, Depends
from httpx_oauth.clients.google import GoogleOAuth2

from kfchess.api.users import router as users_router
from kfchess.auth.backend import auth_backend
from kfchess.auth.dependencies import fastapi_users
from kfchess.auth.rate_limit import (
    forgot_password_rate_limit,
    login_rate_limit,
    register_rate_limit,
    verify_rate_limit,
)
from kfchess.auth.schemas import UserCreate, UserRead
from kfchess.settings import get_settings


def get_auth_router() -> APIRouter:
    """Get the configured authentication router.

    Returns:
        APIRouter with all auth endpoints configured
    """
    router = APIRouter()

    # Login/logout routes (rate limited)
    # The auth router includes both login and logout, but we only want to
    # rate limit login. Since we can't selectively limit, we apply login
    # rate limit to the whole router (logout is harmless to rate limit)
    router.include_router(
        fastapi_users.get_auth_router(auth_backend),
        prefix="/auth",
        tags=["auth"],
        dependencies=[Depends(login_rate_limit)],
    )

    # Registration route (rate limited)
    router.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate),
        prefix="/auth",
        tags=["auth"],
        dependencies=[Depends(register_rate_limit)],
    )

    # Password reset routes (rate limited)
    router.include_router(
        fastapi_users.get_reset_password_router(),
        prefix="/auth",
        tags=["auth"],
        dependencies=[Depends(forgot_password_rate_limit)],
    )

    # Email verification routes (rate limited)
    router.include_router(
        fastapi_users.get_verify_router(UserRead),
        prefix="/auth",
        tags=["auth"],
        dependencies=[Depends(verify_rate_limit)],
    )

    # User management routes (me, update) - uses custom router with DEV_MODE bypass
    router.include_router(users_router)

    # Google OAuth routes (conditional on configuration)
    settings = get_settings()
    if settings.google_oauth_enabled:
        google_oauth_client = GoogleOAuth2(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )

        router.include_router(
            fastapi_users.get_oauth_router(
                google_oauth_client,
                auth_backend,
                settings.secret_key,
                redirect_url=f"{settings.frontend_url}/auth/google/callback",
                is_verified_by_default=True,  # Google verifies email addresses
            ),
            prefix="/auth/google",
            tags=["auth"],
        )

    return router
