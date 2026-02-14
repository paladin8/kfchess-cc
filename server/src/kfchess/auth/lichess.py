"""Lichess OAuth 2.0 integration with mandatory PKCE.

Lichess requires PKCE (Proof Key for Code Exchange) and does not use a client
secret. FastAPI-Users' built-in OAuth router doesn't support PKCE, so we
implement custom authorize/callback endpoints here while reusing the existing
UserManager.oauth_callback() for user creation.
"""

import base64
import hashlib
import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi_users.db import SQLAlchemyUserDatabase
from httpx_oauth.oauth2 import BaseOAuth2, OAuth2Token
from sqlalchemy.ext.asyncio import AsyncSession

from kfchess.auth.backend import auth_backend, get_jwt_strategy
from kfchess.auth.users import UserManager
from kfchess.db.models import OAuthAccount, User
from kfchess.db.session import get_db_session
from kfchess.settings import Settings

logger = logging.getLogger(__name__)

# PKCE and CSRF cookie settings
_COOKIE_MAX_AGE = 600  # 10 minutes
_PKCE_COOKIE = "lichess_pkce"
_CSRF_COOKIE = "lichess_csrf"


class LichessOAuth2(BaseOAuth2[dict]):
    """Lichess OAuth 2.0 client with PKCE support.

    Lichess uses no client secret and requires PKCE. Profile access
    requires no scopes; email requires the `email:read` scope which
    we intentionally skip to minimize permissions.
    """

    def __init__(self, client_id: str, redirect_url: str) -> None:
        super().__init__(
            client_id=client_id,
            client_secret="",
            authorize_endpoint="https://lichess.org/oauth",
            access_token_endpoint="https://lichess.org/api/token",
            name="lichess",
            base_scopes=[],
            token_endpoint_auth_method="client_secret_post",
        )
        self.redirect_url = redirect_url

    async def get_id_email(self, token: str) -> tuple[str, str | None]:
        """Get Lichess user ID and email from the API.

        Lichess username is used as the account ID. No email is returned
        since we don't request the email:read scope.

        Args:
            token: OAuth access token

        Returns:
            Tuple of (lichess_username, None)
        """
        async with self.get_httpx_client() as client:
            response = await client.get(
                "https://lichess.org/api/account",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            data = response.json()
            return data["id"], None


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge.

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # 64 random bytes -> 86 char base64url string
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")
    # S256 challenge = base64url(sha256(verifier))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def get_lichess_router(settings: Settings) -> APIRouter:
    """Create the Lichess OAuth router with PKCE support.

    Args:
        settings: Application settings

    Returns:
        APIRouter with /authorize and /callback endpoints
    """
    router = APIRouter()

    redirect_url = f"{settings.frontend_url}/auth/lichess/callback"
    lichess_client = LichessOAuth2(
        client_id=settings.lichess_client_id,
        redirect_url=redirect_url,
    )

    cookie_secure = not settings.dev_mode

    @router.get("/authorize")
    async def lichess_authorize() -> JSONResponse:
        """Start the Lichess OAuth flow.

        Generates PKCE verifier/challenge and CSRF state, stores them in
        httponly cookies, and returns the Lichess authorization URL.
        """
        code_verifier, code_challenge = _generate_pkce()
        state = secrets.token_urlsafe(32)

        authorization_url = await lichess_client.get_authorization_url(
            redirect_uri=redirect_url,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

        response = JSONResponse({"authorization_url": authorization_url})

        response.set_cookie(
            _PKCE_COOKIE,
            code_verifier,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )
        response.set_cookie(
            _CSRF_COOKIE,
            state,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )

        return response

    @router.get("/callback")
    async def lichess_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        *,
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> Response:
        """Handle the Lichess OAuth callback.

        Validates CSRF state, exchanges the authorization code for a token
        using the PKCE verifier, and creates/finds the user.
        """
        if error:
            return JSONResponse(
                {"detail": f"OAuth error: {error}"},
                status_code=400,
            )

        if not code or not state:
            return JSONResponse(
                {"detail": "Missing code or state parameter"},
                status_code=400,
            )

        # Validate CSRF (constant-time comparison to prevent timing attacks)
        csrf_cookie = request.cookies.get(_CSRF_COOKIE)
        if not csrf_cookie or not secrets.compare_digest(csrf_cookie, state):
            return JSONResponse(
                {"detail": "Invalid state parameter"},
                status_code=400,
            )

        # Get PKCE verifier
        code_verifier = request.cookies.get(_PKCE_COOKIE)
        if not code_verifier:
            return JSONResponse(
                {"detail": "Missing PKCE verifier"},
                status_code=400,
            )

        # Exchange code for token
        try:
            oauth2_token: OAuth2Token = await lichess_client.get_access_token(
                code=code,
                redirect_uri=redirect_url,
                code_verifier=code_verifier,
            )
        except Exception:
            logger.exception("Failed to exchange Lichess OAuth code for token")
            return JSONResponse(
                {"detail": "Failed to exchange authorization code"},
                status_code=400,
            )

        access_token = oauth2_token["access_token"]
        expires_at = oauth2_token.get("expires_at")
        refresh_token = oauth2_token.get("refresh_token")

        # Get user identity from Lichess
        try:
            account_id, account_email = await lichess_client.get_id_email(access_token)
        except Exception:
            logger.exception("Failed to get Lichess user info")
            return JSONResponse(
                {"detail": "Failed to get user info from Lichess"},
                status_code=400,
            )

        # Use UserManager to create/find user (reuse existing logic)
        user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
        user_manager = UserManager(user_db)

        try:
            user = await user_manager.oauth_callback(
                oauth_name="lichess",
                access_token=access_token,
                account_id=account_id,
                account_email=account_email or "",
                expires_at=expires_at,
                refresh_token=refresh_token,
                request=request,
                is_verified_by_default=True,
            )
        except Exception:
            logger.exception("Failed to process Lichess OAuth callback")
            return JSONResponse(
                {"detail": "Failed to create or find user"},
                status_code=400,
            )

        # Generate login response (sets JWT cookie)
        # Session is committed by the get_db_session dependency on success
        strategy = get_jwt_strategy()
        login_response = await auth_backend.login(strategy, user)

        # Clear PKCE and CSRF cookies (match security attributes from set_cookie)
        login_response.delete_cookie(
            _PKCE_COOKIE, httponly=True, secure=cookie_secure, samesite="lax",
        )
        login_response.delete_cookie(
            _CSRF_COOKIE, httponly=True, secure=cookie_secure, samesite="lax",
        )

        return login_response

    return router
