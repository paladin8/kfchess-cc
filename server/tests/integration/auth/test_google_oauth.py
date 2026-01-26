"""Integration tests for Google OAuth authentication."""

import pytest
from httpx import ASGITransport, AsyncClient

from kfchess.main import app


def generate_test_email() -> str:
    """Generate a unique test email."""
    import uuid

    return f"test_{uuid.uuid4().hex[:8]}@example.com"


class TestGoogleOAuthRoutes:
    """Test Google OAuth route availability."""

    @pytest.mark.asyncio
    async def test_oauth_authorize_available_when_enabled(self):
        """Test that /auth/google/authorize is available when OAuth is enabled."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # The authorize endpoint returns JSON with authorization_url
            # (FastAPI-Users returns 200 with URL, not a 302 redirect)
            response = await client.get("/api/auth/google/authorize", follow_redirects=False)

            # Should return 200 with authorization URL in JSON body
            # or 404 if Google OAuth is not configured in test environment
            assert response.status_code in [200, 404]

            if response.status_code == 200:
                data = response.json()
                assert "authorization_url" in data
                # Should point to Google's OAuth endpoint
                assert "accounts.google.com" in data["authorization_url"]

    @pytest.mark.asyncio
    async def test_oauth_callback_endpoint_exists(self):
        """Test that the OAuth callback endpoint exists."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test callback without required params - should get 422 (validation error)
            # or 400 (missing code), not 404
            response = await client.get("/api/auth/google/callback")

            # Should be 422 (validation) or 400 (bad request), not 404 (not found)
            # If OAuth not enabled, might be 404
            assert response.status_code in [400, 404, 422]


class TestGoogleOAuthLegacyUserMigration:
    """Test legacy user migration during Google OAuth flow."""

    @pytest.mark.asyncio
    async def test_legacy_user_lookup_by_google_id(self):
        """Test that legacy users are found by their google_id during OAuth."""

        from kfchess.db.models import User
        from kfchess.db.session import async_session_factory

        # Create a legacy user (has google_id, no password)
        legacy_email = generate_test_email()
        legacy_username = f"LegacyUser_{legacy_email[:8]}"

        async with async_session_factory() as session:
            legacy_user = User(
                email=legacy_email,
                username=legacy_username,
                google_id=legacy_email,  # Legacy pattern: google_id = email
                hashed_password=None,  # No password (Google-only)
                is_active=True,
                is_verified=True,  # Already verified via Google
                is_superuser=False,
            )
            session.add(legacy_user)
            await session.commit()
            legacy_user_id = legacy_user.id

        # Verify we can find the legacy user by google_id
        from kfchess.db.repositories.users import UserRepository

        async with async_session_factory() as session:
            repo = UserRepository(session)
            found_user = await repo.get_by_google_id(legacy_email)

            assert found_user is not None
            assert found_user.id == legacy_user_id
            assert found_user.google_id == legacy_email
            assert found_user.hashed_password is None

    @pytest.mark.asyncio
    async def test_user_manager_oauth_callback_finds_legacy_user(self):
        """Test UserManager.oauth_callback finds legacy users."""
        from fastapi_users.db import SQLAlchemyUserDatabase

        from kfchess.auth.users import UserManager
        from kfchess.db.models import User
        from kfchess.db.session import async_session_factory

        # Create a legacy user
        legacy_email = generate_test_email()
        legacy_username = f"LegacyOAuth_{legacy_email[:8]}"

        async with async_session_factory() as session:
            legacy_user = User(
                email=legacy_email,
                username=legacy_username,
                google_id=legacy_email,
                hashed_password=None,
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(legacy_user)
            await session.commit()
            legacy_user_id = legacy_user.id

            # Create UserManager with real session
            from kfchess.db.models import OAuthAccount

            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)

            # Call oauth_callback - should find legacy user
            result = await user_manager.oauth_callback(
                oauth_name="google",
                access_token="test_access_token",
                account_id="google_account_123",
                account_email=legacy_email,
                expires_at=2147483647,
                refresh_token="test_refresh_token",
            )

            # Should return the legacy user
            assert result is not None
            assert result.id == legacy_user_id
            assert result.username == legacy_username

            # Should have created OAuth account for legacy user
            from sqlalchemy import select

            from kfchess.db.models import OAuthAccount

            oauth_result = await session.execute(
                select(OAuthAccount).where(OAuthAccount.user_id == legacy_user_id)
            )
            oauth_account = oauth_result.scalar_one_or_none()

            assert oauth_account is not None
            assert oauth_account.oauth_name == "google"
            assert oauth_account.access_token == "test_access_token"
            assert oauth_account.account_email == legacy_email

    @pytest.mark.asyncio
    async def test_user_manager_oauth_callback_creates_new_user_when_no_legacy(self):
        """Test UserManager.oauth_callback creates new user when no legacy exists."""
        from fastapi_users.db import SQLAlchemyUserDatabase
        from sqlalchemy import select

        from kfchess.auth.users import UserManager
        from kfchess.db.models import OAuthAccount, User
        from kfchess.db.session import async_session_factory

        new_email = generate_test_email()

        async with async_session_factory() as session:
            # Verify no user exists with this email
            result = await session.execute(select(User).where(User.email == new_email))
            assert result.scalar_one_or_none() is None

            # Create UserManager
            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)

            # Call oauth_callback - should create new user
            result = await user_manager.oauth_callback(
                oauth_name="google",
                access_token="new_user_token",
                account_id="new_google_account_456",
                account_email=new_email,
                expires_at=2147483647,
                refresh_token="new_refresh_token",
                is_verified_by_default=True,
            )

            # Should have created a new user
            assert result is not None
            assert result.email == new_email
            assert result.is_verified is True  # Should be verified via OAuth

            # Should have an auto-generated username
            assert result.username is not None
            parts = result.username.split()
            assert len(parts) == 4  # "Adjective Animal Piece Number" format


class TestGoogleOAuthLegacyUserRegistrationBlock:
    """Test that legacy Google users can't create password accounts."""

    @pytest.mark.asyncio
    async def test_registration_blocked_for_legacy_google_email(self):
        """Test that registering with a legacy Google user's email is blocked."""
        from kfchess.db.models import User
        from kfchess.db.session import async_session_factory

        # Create a legacy Google-only user
        legacy_email = generate_test_email()

        async with async_session_factory() as session:
            legacy_user = User(
                email=legacy_email,
                username=f"LegacyBlock_{legacy_email[:8]}",
                google_id=legacy_email,
                hashed_password=None,  # Google-only, no password
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(legacy_user)
            await session.commit()

        # Try to register with the same email - should be blocked
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": legacy_email,
                    "password": "newpassword123",
                },
            )

            # Should be rejected (400 = user already exists)
            assert response.status_code == 400
            data = response.json()
            assert data["detail"] == "REGISTER_USER_ALREADY_EXISTS"


class TestGoogleOAuthEdgeCases:
    """Test edge cases in Google OAuth flow."""

    @pytest.mark.asyncio
    async def test_oauth_callback_email_exists_as_password_user(self):
        """Test OAuth callback when email already exists as a password-based user."""
        from fastapi_users.db import SQLAlchemyUserDatabase
        from fastapi_users.exceptions import UserAlreadyExists

        from kfchess.auth.users import UserManager
        from kfchess.db.models import OAuthAccount, User
        from kfchess.db.session import async_session_factory

        # Create a password-based user (not legacy - has password, no google_id)
        password_user_email = generate_test_email()

        async with async_session_factory() as session:
            password_user = User(
                email=password_user_email,
                username=f"PasswordUser_{password_user_email[:8]}",
                google_id=None,  # Not a legacy user
                hashed_password="$argon2id$v=19$m=65536,t=3,p=4$hash",  # Has password
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(password_user)
            await session.commit()

            # Create UserManager
            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)

            # Try OAuth callback with same email - should raise UserAlreadyExists
            with pytest.raises(UserAlreadyExists):
                await user_manager.oauth_callback(
                    oauth_name="google",
                    access_token="test_token",
                    account_id="google_account_conflict",
                    account_email=password_user_email,
                    expires_at=2147483647,
                    refresh_token="test_refresh",
                )

    @pytest.mark.asyncio
    async def test_oauth_callback_returns_user_from_existing_oauth_account(self):
        """Test OAuth callback returns user when OAuth account exists."""
        from fastapi_users.db import SQLAlchemyUserDatabase
        from sqlalchemy import select

        from kfchess.auth.users import UserManager
        from kfchess.db.models import OAuthAccount, User
        from kfchess.db.session import async_session_factory

        # Create a user with an OAuth account
        test_email = generate_test_email()
        test_account_id = f"existing_account_{test_email[:8]}"

        async with async_session_factory() as session:
            # Create a user
            test_user = User(
                email=test_email,
                username=f"TestUser_{test_email[:8]}",
                hashed_password="$argon2id$v=19$m=65536,t=3,p=4$hash",
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.flush()
            test_user_id = test_user.id

            # Create OAuth account for this user
            oauth_account = OAuthAccount(
                user_id=test_user_id,
                oauth_name="google",
                access_token="old_token",
                account_id=test_account_id,
                account_email=test_email,
                expires_at=2147483647,
                refresh_token="old_refresh",
            )
            session.add(oauth_account)
            await session.commit()

        # Now try OAuth callback - should return the existing user
        async with async_session_factory() as session:
            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)

            result = await user_manager.oauth_callback(
                oauth_name="google",
                access_token="new_token",
                account_id=test_account_id,
                account_email=test_email,
                expires_at=2147483647,
                refresh_token="new_refresh",
                is_verified_by_default=True,
            )

            # Should return the existing user
            assert result is not None
            assert result.id == test_user_id
            assert result.email == test_email

            # OAuth account should have been updated with new tokens
            oauth_result = await session.execute(
                select(OAuthAccount).where(OAuthAccount.account_id == test_account_id)
            )
            updated_oauth = oauth_result.scalar_one_or_none()
            assert updated_oauth is not None
            assert updated_oauth.access_token == "new_token"
            assert updated_oauth.refresh_token == "new_refresh"

    @pytest.mark.asyncio
    async def test_oauth_callback_with_expired_token_logs_warning(self, caplog):
        """Test that OAuth callback logs warning for expired tokens."""
        import logging

        from fastapi_users.db import SQLAlchemyUserDatabase

        from kfchess.auth.users import UserManager
        from kfchess.db.models import OAuthAccount, User
        from kfchess.db.session import async_session_factory

        new_email = generate_test_email()

        async with async_session_factory() as session:
            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)

            # Set logging level to capture warnings
            with caplog.at_level(logging.WARNING, logger="kfchess.auth.users"):
                # Call oauth_callback with an expired token (timestamp in the past)
                result = await user_manager.oauth_callback(
                    oauth_name="google",
                    access_token="expired_token",
                    account_id=f"expired_account_{new_email[:8]}",
                    account_email=new_email,
                    expires_at=1,  # Expired timestamp (Jan 1, 1970)
                    refresh_token="test_refresh",
                    is_verified_by_default=True,
                )

                # Should still create user (token validation is just logging)
                assert result is not None
                assert result.email == new_email

                # Should have logged a warning about expired token
                assert any(
                    "expired token" in record.message.lower() for record in caplog.records
                )

    @pytest.mark.asyncio
    async def test_oauth_callback_with_empty_token_logs_warning(self, caplog):
        """Test that OAuth callback logs warning for empty access token."""
        import logging

        from fastapi_users.db import SQLAlchemyUserDatabase

        from kfchess.auth.users import UserManager
        from kfchess.db.models import OAuthAccount, User
        from kfchess.db.session import async_session_factory

        new_email = generate_test_email()

        async with async_session_factory() as session:
            user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
            user_manager = UserManager(user_db)

            with caplog.at_level(logging.WARNING, logger="kfchess.auth.users"):
                # Call oauth_callback with empty access token
                result = await user_manager.oauth_callback(
                    oauth_name="google",
                    access_token="",  # Empty token
                    account_id=f"empty_token_account_{new_email[:8]}",
                    account_email=new_email,
                    expires_at=2147483647,
                    refresh_token="test_refresh",
                    is_verified_by_default=True,
                )

                # Should still create user
                assert result is not None
                assert result.email == new_email

                # Should have logged a warning about empty token
                assert any(
                    "empty access_token" in record.message.lower()
                    for record in caplog.records
                )
