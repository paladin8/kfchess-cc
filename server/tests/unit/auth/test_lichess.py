"""Tests for Lichess OAuth 2.0 integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kfchess.auth.lichess import LichessOAuth2, _generate_pkce, get_lichess_router


class TestGeneratePkce:
    """Tests for PKCE code verifier/challenge generation."""

    def test_returns_tuple_of_two_strings(self):
        """Test that _generate_pkce returns a verifier and challenge."""
        verifier, challenge = _generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_is_long_enough(self):
        """Test that the code verifier meets minimum length requirements."""
        verifier, _ = _generate_pkce()
        # RFC 7636 requires 43-128 characters
        assert len(verifier) >= 43

    def test_challenge_differs_from_verifier(self):
        """Test that the challenge is not the same as the verifier."""
        verifier, challenge = _generate_pkce()
        assert verifier != challenge

    def test_generates_unique_values(self):
        """Test that each call generates different values."""
        pairs = [_generate_pkce() for _ in range(10)]
        verifiers = {v for v, _ in pairs}
        assert len(verifiers) == 10

    def test_verifier_is_url_safe(self):
        """Test that the verifier uses only URL-safe characters."""
        import re

        for _ in range(20):
            verifier, _ = _generate_pkce()
            # base64url alphabet: A-Z, a-z, 0-9, -, _
            assert re.match(r'^[A-Za-z0-9_-]+$', verifier)

    def test_challenge_matches_sha256_of_verifier(self):
        """Test that the challenge is the SHA-256 hash of the verifier."""
        import base64
        import hashlib

        verifier, challenge = _generate_pkce()
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert challenge == expected_challenge


class TestLichessOAuth2:
    """Tests for the LichessOAuth2 client."""

    def test_init_sets_correct_endpoints(self):
        """Test that the client is configured with Lichess endpoints."""
        client = LichessOAuth2(client_id="test-app", redirect_url="http://localhost/callback")
        assert client.authorize_endpoint == "https://lichess.org/oauth"
        assert client.access_token_endpoint == "https://lichess.org/api/token"

    def test_init_sets_empty_secret(self):
        """Test that no client secret is set (Lichess uses PKCE only)."""
        client = LichessOAuth2(client_id="test-app", redirect_url="http://localhost/callback")
        assert client.client_secret == ""

    def test_init_sets_no_base_scopes(self):
        """Test that no scopes are requested (profile access needs none)."""
        client = LichessOAuth2(client_id="test-app", redirect_url="http://localhost/callback")
        assert client.base_scopes == []

    def test_name_is_lichess(self):
        """Test that the provider name is 'lichess'."""
        client = LichessOAuth2(client_id="test-app", redirect_url="http://localhost/callback")
        assert client.name == "lichess"

    @pytest.mark.asyncio
    async def test_get_id_email_returns_id_and_none(self):
        """Test that get_id_email returns Lichess username and no email."""
        client = LichessOAuth2(client_id="test-app", redirect_url="http://localhost/callback")

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "testplayer", "username": "TestPlayer"}
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client = AsyncMock()
        mock_httpx_client.get.return_value = mock_response
        mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client, "get_httpx_client", return_value=mock_httpx_client):
            account_id, email = await client.get_id_email("test_token")

        assert account_id == "testplayer"
        assert email is None

    @pytest.mark.asyncio
    async def test_get_id_email_sends_bearer_token(self):
        """Test that get_id_email sends the access token as Bearer auth."""
        client = LichessOAuth2(client_id="test-app", redirect_url="http://localhost/callback")

        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "testplayer"}
        mock_response.raise_for_status = MagicMock()

        mock_httpx_client = AsyncMock()
        mock_httpx_client.get.return_value = mock_response
        mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_httpx_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client, "get_httpx_client", return_value=mock_httpx_client):
            await client.get_id_email("my_access_token")

        mock_httpx_client.get.assert_called_once_with(
            "https://lichess.org/api/account",
            headers={"Authorization": "Bearer my_access_token"},
        )


class TestGetLichessRouter:
    """Tests for the Lichess router factory."""

    def test_returns_api_router(self):
        """Test that get_lichess_router returns an APIRouter."""
        from fastapi import APIRouter

        settings = MagicMock()
        settings.lichess_client_id = "test-app"
        settings.frontend_url = "http://localhost:5173"
        settings.dev_mode = True

        router = get_lichess_router(settings)
        assert isinstance(router, APIRouter)

    def test_router_has_authorize_and_callback_routes(self):
        """Test that the router has the expected routes."""
        settings = MagicMock()
        settings.lichess_client_id = "test-app"
        settings.frontend_url = "http://localhost:5173"
        settings.dev_mode = True

        router = get_lichess_router(settings)
        route_paths = [route.path for route in router.routes]
        assert "/authorize" in route_paths
        assert "/callback" in route_paths


class TestLichessSettings:
    """Tests for Lichess-related settings."""

    def test_lichess_oauth_enabled_when_client_id_set(self):
        """Test lichess_oauth_enabled returns True when client ID is set."""
        from kfchess.settings import Settings

        settings = Settings(lichess_client_id="kungfuchess.com")
        assert settings.lichess_oauth_enabled is True

    def test_lichess_oauth_disabled_when_client_id_empty(self):
        """Test lichess_oauth_enabled returns False when client ID is empty."""
        from kfchess.settings import Settings

        settings = Settings(lichess_client_id="")
        assert settings.lichess_oauth_enabled is False

    def test_lichess_oauth_enabled_by_default(self):
        """Test lichess_oauth_enabled is True by default (client ID has a default)."""
        from kfchess.settings import Settings

        settings = Settings()
        assert settings.lichess_oauth_enabled is True


class TestLichessOAuthCallbackNullEmail:
    """Tests for OAuth callback with null/empty email (Lichess pattern)."""

    @pytest.mark.asyncio
    async def test_oauth_callback_creates_user_with_null_email(self):
        """Test that OAuth callback with empty email creates user with email=None."""
        from kfchess.auth.users import UserManager

        mock_user_db = AsyncMock()
        mock_session = MagicMock()
        mock_user_db.session = mock_session

        user_manager = UserManager(mock_user_db)

        # Track what gets added to the session
        added_objects = []
        mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_session.flush = AsyncMock()

        with patch.object(user_manager, '_get_oauth_account', new_callable=AsyncMock, return_value=None), \
             patch.object(user_manager, '_generate_unique_username', new_callable=AsyncMock, return_value="Swift Tiger Pawn 12345"), \
             patch.object(user_manager, '_create_or_update_oauth_account', new_callable=AsyncMock), \
             patch.object(user_manager, 'on_after_register', new_callable=AsyncMock):

            await user_manager.oauth_callback(
                oauth_name="lichess",
                access_token="lichess_token",
                account_id="testplayer",
                account_email="",  # Empty email from Lichess
                is_verified_by_default=True,
            )

        # Find the User object that was added
        from kfchess.db.models import User
        created_users = [obj for obj in added_objects if isinstance(obj, User)]
        assert len(created_users) == 1
        assert created_users[0].email is None
