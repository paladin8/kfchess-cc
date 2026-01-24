"""User API routes with DEV_MODE bypass support.

These routes replace FastAPI-Users' built-in /users routes to support
DEV_MODE authentication bypass for local development.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from kfchess.auth.dependencies import (
    get_required_user_with_dev_bypass,
    get_user_manager_dep,
)
from kfchess.auth.schemas import UserRead, UserUpdate
from kfchess.auth.users import UserManager
from kfchess.db.models import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_current_user_info(
    user: Annotated[User, Depends(get_required_user_with_dev_bypass)],
) -> User:
    """Get the current user's information.

    This endpoint supports DEV_MODE bypass - when DEV_MODE=true and
    DEV_USER_ID is set, returns the dev user without authentication.

    Returns:
        Current user's data
    """
    return user


class UserUpdateRequest(BaseModel):
    """Request model for user updates."""

    password: str | None = None
    username: str | None = None
    picture_url: str | None = None


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    update_data: UserUpdate,
    user: Annotated[User, Depends(get_required_user_with_dev_bypass)],
    user_manager: Annotated[UserManager, Depends(get_user_manager_dep)],
) -> User:
    """Update the current user's information.

    This endpoint supports DEV_MODE bypass - when DEV_MODE=true and
    DEV_USER_ID is set, allows updating the dev user without authentication.

    Args:
        update_data: Fields to update
        user: Current authenticated user (or dev user)
        user_manager: User manager for handling updates

    Returns:
        Updated user data

    Raises:
        HTTPException: 400 if username is already taken
    """
    try:
        updated_user = await user_manager.update(update_data, user)
        return updated_user
    except IntegrityError as e:
        # Check if this is a username conflict
        error_str = str(e).lower()
        if "username" in error_str or "unique" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username is already taken. Please choose another.",
            ) from e
        # Re-raise other integrity errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Update failed due to a constraint violation.",
        ) from e
