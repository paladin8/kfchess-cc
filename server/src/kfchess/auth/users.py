"""User management for FastAPI-Users.

Provides custom UserManager with random username generation,
email sending, and legacy Google OAuth user handling.
"""

import logging
import random
from typing import Any

from fastapi import Request
from fastapi_users import BaseUserManager, IntegerIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import select

from kfchess.auth.email import send_password_reset_email, send_verification_email
from kfchess.db.models import OAuthAccount, User
from kfchess.settings import get_settings

logger = logging.getLogger(__name__)

# Word lists for random username generation (matching legacy pattern)
ANIMALS = [
    "Tiger",
    "Leopard",
    "Crane",
    "Snake",
    "Dragon",
    "Phoenix",
    "Mantis",
    "Monkey",
    "Eagle",
    "Panther",
]

CHESS_PIECES = [
    "Pawn",
    "Knight",
    "Bishop",
    "Rook",
    "Queen",
    "King",
]


def generate_random_username() -> str:
    """Generate a random username like 'Tiger Pawn 456'.

    Returns:
        A random username in the format "Animal Piece Number"
    """
    animal = random.choice(ANIMALS)
    piece = random.choice(CHESS_PIECES)
    number = random.randint(100, 999)
    return f"{animal} {piece} {number}"


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """Custom user manager with application-specific logic.

    Features:
    - Auto-generates usernames if not provided during registration
    - Sends verification and password reset emails via Resend
    - Uses integer IDs for legacy compatibility
    - Handles legacy Google OAuth users by google_id lookup
    """

    reset_password_token_secret = get_settings().secret_key
    verification_token_secret = get_settings().secret_key

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        """Called after successful user registration.

        Logs the registration and sends verification email if email service
        is configured.
        """
        logger.info(f"User {user.id} ({user.username}) registered")

        # Send verification email if Resend is configured
        if user.email and get_settings().resend_enabled:
            try:
                token = await self._generate_verify_token(user)
                await send_verification_email(user.email, token)
            except Exception as e:
                logger.warning(f"Failed to send verification email: {e}")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        """Called after password reset is requested.

        Sends the password reset email with token.
        """
        logger.info(f"Password reset requested for user {user.id}")

        if user.email:
            await send_password_reset_email(user.email, token)

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        """Called when email verification is requested.

        Sends the verification email with token.
        """
        logger.info(f"Verification requested for user {user.id}")

        if user.email:
            await send_verification_email(user.email, token)

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Request | None = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> User:
        """Handle OAuth callback with legacy user migration support.

        This method extends the default FastAPI-Users OAuth handling to:
        1. First check for legacy users by google_id (which stores their email)
        2. If found, create/update OAuth account and return existing user
        3. Check for existing OAuth account
        4. Check for existing user by email (if associate_by_email is True)
        5. Create new user with auto-generated username

        Legacy users in the old system:
        - Used Google OAuth only
        - Had their Google email stored in both 'email' and 'google_id' columns
        - Have no OAuth account record (those are new in this system)

        Args:
            oauth_name: Name of the OAuth provider (e.g., "google")
            access_token: OAuth access token
            account_id: Provider's account ID
            account_email: Email from OAuth provider
            expires_at: Token expiration timestamp
            refresh_token: OAuth refresh token
            request: FastAPI request object
            associate_by_email: Whether to associate with existing email account
            is_verified_by_default: Whether new users should be verified

        Returns:
            The authenticated user (existing legacy user or newly created)
        """
        # For Google OAuth, check for legacy users by google_id
        # Legacy users have their email stored in google_id field
        if oauth_name == "google" and account_email:
            legacy_user = await self._find_legacy_google_user(account_email)
            if legacy_user:
                logger.info(
                    f"Found legacy Google user {legacy_user.id} ({legacy_user.username}) "
                    f"for email {account_email}"
                )
                # Create or update OAuth account for this user
                await self._create_or_update_oauth_account(
                    user=legacy_user,
                    oauth_name=oauth_name,
                    access_token=access_token,
                    account_id=account_id,
                    account_email=account_email,
                    expires_at=expires_at,
                    refresh_token=refresh_token,
                )
                return legacy_user

        # Check for existing OAuth account
        oauth_account = await self._get_oauth_account(oauth_name, account_id)
        if oauth_account:
            # Update existing OAuth account
            oauth_account.access_token = access_token
            oauth_account.expires_at = expires_at
            oauth_account.refresh_token = refresh_token
            await self.user_db.session.flush()

            # Return the associated user
            user = await self.user_db.get(oauth_account.user_id)
            if user:
                return user

        # Check for existing user by email (if associate_by_email is True)
        if associate_by_email and account_email:
            user = await self.user_db.get_by_email(account_email)
            if user:
                # Create OAuth account for existing user
                await self._create_or_update_oauth_account(
                    user=user,
                    oauth_name=oauth_name,
                    access_token=access_token,
                    account_id=account_id,
                    account_email=account_email,
                    expires_at=expires_at,
                    refresh_token=refresh_token,
                )
                return user

        # Create new user with auto-generated username
        username = await self._generate_unique_username()
        new_user = User(
            email=account_email,
            username=username,
            hashed_password=self.password_helper.hash(self.password_helper.generate()),
            is_active=True,
            is_verified=is_verified_by_default,
            is_superuser=False,
        )
        self.user_db.session.add(new_user)
        await self.user_db.session.flush()

        logger.info(f"Created new OAuth user {new_user.id} ({new_user.username})")

        # Create OAuth account for new user
        await self._create_or_update_oauth_account(
            user=new_user,
            oauth_name=oauth_name,
            access_token=access_token,
            account_id=account_id,
            account_email=account_email,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

        await self.on_after_register(new_user, request)
        return new_user

    async def _get_oauth_account(self, oauth_name: str, account_id: str) -> OAuthAccount | None:
        """Get an OAuth account by provider name and account ID.

        Args:
            oauth_name: OAuth provider name
            account_id: Provider account ID

        Returns:
            The OAuth account if found, None otherwise
        """
        result = await self.user_db.session.execute(
            select(OAuthAccount).where(
                OAuthAccount.oauth_name == oauth_name,
                OAuthAccount.account_id == account_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_legacy_google_user(self, email: str) -> User | None:
        """Find a legacy user by their google_id (which stores their email).

        Args:
            email: The email address to search for in google_id

        Returns:
            The legacy user if found, None otherwise
        """
        result = await self.user_db.session.execute(select(User).where(User.google_id == email))
        return result.unique().scalar_one_or_none()

    async def _create_or_update_oauth_account(
        self,
        user: User,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None,
        refresh_token: str | None,
    ) -> OAuthAccount:
        """Create or update an OAuth account for a user.

        Args:
            user: The user to associate with
            oauth_name: OAuth provider name
            access_token: Access token
            account_id: Provider account ID
            account_email: Email from provider
            expires_at: Token expiration
            refresh_token: Refresh token

        Returns:
            The created or updated OAuth account
        """
        # Check if OAuth account already exists
        result = await self.user_db.session.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user.id,
                OAuthAccount.oauth_name == oauth_name,
            )
        )
        oauth_account = result.scalar_one_or_none()

        if oauth_account:
            # Update existing account
            oauth_account.access_token = access_token
            oauth_account.account_id = account_id
            oauth_account.account_email = account_email
            oauth_account.expires_at = expires_at
            oauth_account.refresh_token = refresh_token
            logger.info(f"Updated OAuth account for user {user.id}")
        else:
            # Create new account
            oauth_account = OAuthAccount(
                user_id=user.id,
                oauth_name=oauth_name,
                access_token=access_token,
                account_id=account_id,
                account_email=account_email,
                expires_at=expires_at,
                refresh_token=refresh_token,
            )
            self.user_db.session.add(oauth_account)
            logger.info(f"Created OAuth account for user {user.id}")

        await self.user_db.session.flush()
        return oauth_account

    async def create(
        self,
        user_create: Any,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        """Create a new user with auto-generated username if needed.

        Checks for legacy Google-only users and prevents duplicate accounts.

        Args:
            user_create: User creation schema
            safe: If True, only allow safe fields (for registration endpoints)
            request: The FastAPI request object

        Returns:
            The created user

        Raises:
            UserAlreadyExists: If email belongs to a legacy Google-only user
        """
        from fastapi_users.exceptions import UserAlreadyExists

        # Check if this email belongs to a legacy Google-only user
        # Legacy users have google_id set (same as email) but no password
        email = getattr(user_create, "email", None)
        if email:
            legacy_user = await self._find_legacy_google_user(email)
            if legacy_user and legacy_user.hashed_password is None:
                # This email belongs to a legacy Google OAuth user
                # They should use Google login, not create a new password account
                logger.warning(
                    f"Registration attempt for legacy Google user email: {email}. "
                    f"User should login via Google OAuth instead."
                )
                raise UserAlreadyExists()

        # Auto-generate username if not provided
        if not getattr(user_create, "username", None):
            username = await self._generate_unique_username()
            # Create a new instance with the username set
            user_dict = user_create.model_dump()
            user_dict["username"] = username
            user_create = user_create.__class__(**user_dict)

        return await super().create(user_create, safe, request)

    async def _generate_unique_username(self, max_attempts: int = 10) -> str:
        """Generate a unique random username.

        Tries up to max_attempts times to find an available username.

        Args:
            max_attempts: Maximum number of generation attempts

        Returns:
            A unique username

        Raises:
            RuntimeError: If unable to generate a unique username
        """
        for _ in range(max_attempts):
            username = generate_random_username()
            # Check if username is available with a direct query
            result = await self.user_db.session.execute(
                select(User).where(User.username == username)
            )
            if result.scalar_one_or_none() is None:
                return username

        raise RuntimeError("Unable to generate unique username after multiple attempts")

    async def _generate_verify_token(self, user: User) -> str:
        """Generate a verification token for the user.

        This is a simplified implementation - FastAPI-Users handles this
        internally when you use the verification routes.
        """
        from fastapi_users.jwt import generate_jwt

        return generate_jwt(
            data={"sub": str(user.id), "email": user.email, "aud": "fastapi-users:verify"},
            secret=self.verification_token_secret,
            lifetime_seconds=86400,  # 24 hours
        )


async def get_user_db(
    session: Any,
) -> SQLAlchemyUserDatabase[User, int]:
    """Get the user database adapter.

    Args:
        session: The database session

    Returns:
        SQLAlchemy user database adapter
    """
    return SQLAlchemyUserDatabase(session, User, OAuthAccount)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase[User, int],
) -> UserManager:
    """Get the user manager.

    Args:
        user_db: The user database adapter

    Returns:
        UserManager instance
    """
    return UserManager(user_db)
