"""Pydantic schemas for user authentication.

Defines the data structures for user registration, reading, and updating.
"""

from datetime import datetime

from fastapi_users import schemas
from pydantic import Field, field_validator


class UserRead(schemas.BaseUser[int]):
    """Schema for reading user data (API responses).

    Extends FastAPI-Users base schema with application-specific fields.
    """

    email: str | None = None  # Override: nullable for OAuth-only users (e.g., Lichess)
    username: str
    picture_url: str | None = None
    google_id: str | None = None
    ratings: dict = Field(default_factory=dict)
    created_at: datetime
    last_online: datetime


class UserCreate(schemas.BaseUserCreate):
    """Schema for user registration.

    Username is optional - will be auto-generated if not provided.
    Password requirements: 8-128 characters.
    """

    username: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        """Validate username length if provided."""
        if v is None:
            return v
        if len(v) < 2:
            raise ValueError("Username must be at least 2 characters")
        if len(v) > 32:
            raise ValueError("Username must be at most 32 characters")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password meets minimum requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user profile.

    All fields are optional - only provided fields will be updated.
    """

    username: str | None = None
    picture_url: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        """Validate username length if provided."""
        if v is None:
            return v
        if len(v) < 2:
            raise ValueError("Username must be at least 2 characters")
        if len(v) > 32:
            raise ValueError("Username must be at most 32 characters")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        """Validate password if provided."""
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        return v
