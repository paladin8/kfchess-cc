"""Tests for UserManager and username generation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kfchess.auth.users import (
    ANIMALS,
    CHESS_PIECES,
    UserManager,
    generate_random_username,
)
from kfchess.db.models import OAuthAccount, User


class TestGenerateRandomUsername:
    """Tests for random username generation."""

    def test_generates_three_part_username(self):
        """Test username has format 'Animal Piece Number'."""
        username = generate_random_username()
        parts = username.split()
        assert len(parts) == 3

    def test_first_part_is_animal(self):
        """Test first part is a valid animal."""
        username = generate_random_username()
        animal = username.split()[0]
        assert animal in ANIMALS

    def test_second_part_is_chess_piece(self):
        """Test second part is a valid chess piece."""
        username = generate_random_username()
        piece = username.split()[1]
        assert piece in CHESS_PIECES

    def test_third_part_is_three_digit_number(self):
        """Test third part is a number between 100 and 999."""
        username = generate_random_username()
        number_str = username.split()[2]
        assert number_str.isdigit()
        number = int(number_str)
        assert 100 <= number <= 999

    def test_generates_variety(self):
        """Test that function generates different usernames."""
        usernames = {generate_random_username() for _ in range(50)}
        # With 10 animals * 6 pieces * 900 numbers, should get variety
        assert len(usernames) > 10

    def test_format_example(self):
        """Test username matches expected format pattern."""
        for _ in range(10):
            username = generate_random_username()
            parts = username.split()
            assert parts[0] in ANIMALS
            assert parts[1] in CHESS_PIECES
            assert parts[2].isdigit()
            assert len(parts[2]) == 3


class TestUserManager:
    """Tests for UserManager functionality."""

    @pytest.fixture
    def user_manager(self, mock_user_db):
        """Create a UserManager with mocked database."""
        return UserManager(mock_user_db)

    @pytest.mark.asyncio
    async def test_generate_unique_username_success(self, user_manager):
        """Test successful unique username generation."""
        # Mock session to return None (username not taken)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        user_manager.user_db.session.execute = AsyncMock(return_value=mock_result)

        username = await user_manager._generate_unique_username()

        # Should be a valid username format
        parts = username.split()
        assert len(parts) == 3
        assert parts[0] in ANIMALS
        assert parts[1] in CHESS_PIECES

    @pytest.mark.asyncio
    async def test_generate_unique_username_retries_on_collision(self, user_manager):
        """Test username generation retries when collision found."""
        existing_user = MagicMock(spec=User)

        # First two calls return existing user (collision), third returns None
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count < 3:
                mock_result.scalar_one_or_none.return_value = existing_user
            else:
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        user_manager.user_db.session.execute = AsyncMock(side_effect=side_effect)

        username = await user_manager._generate_unique_username()

        # Should have called execute 3 times
        assert call_count == 3
        assert username is not None

    @pytest.mark.asyncio
    async def test_generate_unique_username_fails_after_max_attempts(self, user_manager):
        """Test username generation fails after max attempts."""
        existing_user = MagicMock(spec=User)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        user_manager.user_db.session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(RuntimeError, match="Unable to generate unique username"):
            await user_manager._generate_unique_username(max_attempts=3)

        # Should have tried exactly 3 times
        assert user_manager.user_db.session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_find_legacy_google_user_found(self, user_manager, mock_legacy_user):
        """Test finding legacy user by google_id."""
        mock_result = MagicMock()
        mock_unique = MagicMock()
        mock_unique.scalar_one_or_none.return_value = mock_legacy_user
        mock_result.unique.return_value = mock_unique
        user_manager.user_db.session.execute = AsyncMock(return_value=mock_result)

        result = await user_manager._find_legacy_google_user("legacy@gmail.com")

        assert result == mock_legacy_user

    @pytest.mark.asyncio
    async def test_find_legacy_google_user_not_found(self, user_manager):
        """Test legacy user lookup returns None when not found."""
        mock_result = MagicMock()
        mock_unique = MagicMock()
        mock_unique.scalar_one_or_none.return_value = None
        mock_result.unique.return_value = mock_unique
        user_manager.user_db.session.execute = AsyncMock(return_value=mock_result)

        result = await user_manager._find_legacy_google_user("nonexistent@gmail.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_oauth_callback_finds_legacy_user(self, user_manager, mock_legacy_user):
        """Test oauth_callback finds and returns legacy Google user."""
        # Mock _find_legacy_google_user to return legacy user
        user_manager._find_legacy_google_user = AsyncMock(return_value=mock_legacy_user)
        user_manager._create_or_update_oauth_account = AsyncMock()

        result = await user_manager.oauth_callback(
            oauth_name="google",
            access_token="test_token",
            account_id="123456789",
            account_email="legacy@gmail.com",
        )

        assert result == mock_legacy_user
        user_manager._find_legacy_google_user.assert_called_once_with("legacy@gmail.com")
        user_manager._create_or_update_oauth_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_oauth_callback_creates_oauth_account_for_legacy_user(
        self, user_manager, mock_legacy_user
    ):
        """Test oauth_callback creates OAuth account when finding legacy user."""
        user_manager._find_legacy_google_user = AsyncMock(return_value=mock_legacy_user)
        user_manager._create_or_update_oauth_account = AsyncMock()

        await user_manager.oauth_callback(
            oauth_name="google",
            access_token="test_token",
            account_id="123456789",
            account_email="legacy@gmail.com",
            expires_at=9999999999,
            refresh_token="refresh_token",
        )

        # Verify OAuth account creation was called with correct params
        call_kwargs = user_manager._create_or_update_oauth_account.call_args[1]
        assert call_kwargs["user"] == mock_legacy_user
        assert call_kwargs["oauth_name"] == "google"
        assert call_kwargs["access_token"] == "test_token"
        assert call_kwargs["account_id"] == "123456789"
        assert call_kwargs["account_email"] == "legacy@gmail.com"

    @pytest.mark.asyncio
    async def test_oauth_callback_creates_new_user_when_no_legacy(self, user_manager):
        """Test oauth_callback creates new user when no legacy user found."""
        user_manager._find_legacy_google_user = AsyncMock(return_value=None)
        user_manager._get_oauth_account = AsyncMock(return_value=None)
        user_manager._generate_unique_username = AsyncMock(return_value="Tiger Pawn 123")
        user_manager._create_or_update_oauth_account = AsyncMock()
        user_manager.on_after_register = AsyncMock()
        user_manager.user_db.session.add = MagicMock()
        user_manager.user_db.session.flush = AsyncMock()

        result = await user_manager.oauth_callback(
            oauth_name="google",
            access_token="test_token",
            account_id="123456789",
            account_email="newuser@gmail.com",
            is_verified_by_default=True,
        )

        # Should have created a new user
        assert result is not None
        assert result.email == "newuser@gmail.com"
        assert result.username == "Tiger Pawn 123"
        assert result.is_verified is True

        # Should have called create methods
        user_manager._generate_unique_username.assert_called_once()
        user_manager._create_or_update_oauth_account.assert_called_once()
        user_manager.on_after_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_oauth_callback_skips_legacy_check_for_non_google(self, user_manager):
        """Test oauth_callback skips legacy lookup for non-Google providers."""
        user_manager._find_legacy_google_user = AsyncMock()
        user_manager._get_oauth_account = AsyncMock(return_value=None)
        user_manager._generate_unique_username = AsyncMock(return_value="Tiger Pawn 123")
        user_manager._create_or_update_oauth_account = AsyncMock()
        user_manager.on_after_register = AsyncMock()
        user_manager.user_db.session.add = MagicMock()
        user_manager.user_db.session.flush = AsyncMock()

        await user_manager.oauth_callback(
            oauth_name="github",  # Not Google
            access_token="test_token",
            account_id="123456789",
            account_email="user@github.com",
        )

        # Should not check for legacy Google users
        user_manager._find_legacy_google_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_or_update_oauth_account_creates_new(self, user_manager, mock_user):
        """Test creating new OAuth account for user."""
        # Mock no existing OAuth account
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        user_manager.user_db.session.execute = AsyncMock(return_value=mock_result)
        user_manager.user_db.session.add = MagicMock()
        user_manager.user_db.session.flush = AsyncMock()

        result = await user_manager._create_or_update_oauth_account(
            user=mock_user,
            oauth_name="google",
            access_token="token",
            account_id="12345",
            account_email="user@gmail.com",
            expires_at=9999999999,
            refresh_token="refresh",
        )

        # Should have added new OAuth account
        user_manager.user_db.session.add.assert_called_once()
        user_manager.user_db.session.flush.assert_called_once()
        assert isinstance(result, OAuthAccount)

    @pytest.mark.asyncio
    async def test_create_or_update_oauth_account_updates_existing(self, user_manager, mock_user):
        """Test updating existing OAuth account."""
        existing_oauth = MagicMock(spec=OAuthAccount)
        existing_oauth.user_id = mock_user.id
        existing_oauth.oauth_name = "google"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_oauth
        user_manager.user_db.session.execute = AsyncMock(return_value=mock_result)
        user_manager.user_db.session.flush = AsyncMock()

        result = await user_manager._create_or_update_oauth_account(
            user=mock_user,
            oauth_name="google",
            access_token="new_token",
            account_id="12345",
            account_email="user@gmail.com",
            expires_at=8888888888,
            refresh_token="new_refresh",
        )

        # Should have updated existing account
        assert existing_oauth.access_token == "new_token"
        assert existing_oauth.expires_at == 8888888888
        assert existing_oauth.refresh_token == "new_refresh"
        assert result == existing_oauth


class TestUserManagerCreate:
    """Tests for UserManager.create() method."""

    @pytest.fixture
    def user_manager(self, mock_user_db):
        """Create a UserManager with mocked database."""
        return UserManager(mock_user_db)

    @pytest.mark.asyncio
    async def test_create_rejects_legacy_google_user_email(self, user_manager, mock_legacy_user):
        """Test create() rejects registration with legacy Google user email."""
        from fastapi_users.exceptions import UserAlreadyExists

        from kfchess.auth.schemas import UserCreate

        # Mock finding legacy user
        user_manager._find_legacy_google_user = AsyncMock(return_value=mock_legacy_user)

        user_create = UserCreate(
            email="legacy@gmail.com",
            password="newpassword123",
        )

        with pytest.raises(UserAlreadyExists):
            await user_manager.create(user_create, safe=True)

    @pytest.mark.asyncio
    async def test_create_allows_email_if_user_has_password(self, user_manager, mock_user):
        """Test create() allows email if existing user has password (not legacy)."""
        from kfchess.auth.schemas import UserCreate

        # Mock user with password (not legacy Google-only)
        mock_user.hashed_password = "existing_hash"
        user_manager._find_legacy_google_user = AsyncMock(return_value=mock_user)

        # This should fall through to parent create (which would check email uniqueness)
        # We just verify it doesn't raise UserAlreadyExists from our check
        user_create = UserCreate(
            email="test@example.com",
            password="newpassword123",
        )

        with patch.object(
            UserManager.__bases__[1],
            "create",
            new_callable=AsyncMock,
        ) as mock_parent:
            mock_parent.return_value = mock_user
            user_manager._generate_unique_username = AsyncMock(return_value="Tiger Pawn 123")

            # Should not raise UserAlreadyExists from our check
            # (parent might raise it for duplicate email, but that's expected)
            await user_manager.create(user_create, safe=True)

    @pytest.mark.asyncio
    async def test_create_generates_username_when_not_provided(self, user_manager):
        """Test create() auto-generates username when not provided."""
        from kfchess.auth.schemas import UserCreate

        user_manager._find_legacy_google_user = AsyncMock(return_value=None)
        user_manager._generate_unique_username = AsyncMock(return_value="Dragon Knight 789")

        new_user = MagicMock(spec=User)

        with patch.object(
            UserManager.__bases__[1],
            "create",
            new_callable=AsyncMock,
            return_value=new_user,
        ) as mock_parent:
            user_create = UserCreate(
                email="newuser@example.com",
                password="validpassword123",
            )

            await user_manager.create(user_create, safe=True)

            # Should have generated username
            user_manager._generate_unique_username.assert_called_once()

            # Should have passed username to parent
            call_args = mock_parent.call_args[0][0]
            assert call_args.username == "Dragon Knight 789"

    @pytest.mark.asyncio
    async def test_create_preserves_provided_username(self, user_manager):
        """Test create() preserves username when provided."""
        from kfchess.auth.schemas import UserCreate

        user_manager._find_legacy_google_user = AsyncMock(return_value=None)
        user_manager._generate_unique_username = AsyncMock()

        new_user = MagicMock(spec=User)

        with patch.object(
            UserManager.__bases__[1],
            "create",
            new_callable=AsyncMock,
            return_value=new_user,
        ) as mock_parent:
            user_create = UserCreate(
                email="newuser@example.com",
                password="validpassword123",
                username="CustomUsername",
            )

            await user_manager.create(user_create, safe=True)

            # Should NOT have generated username
            user_manager._generate_unique_username.assert_not_called()

            # Should have preserved the provided username
            call_args = mock_parent.call_args[0][0]
            assert call_args.username == "CustomUsername"
