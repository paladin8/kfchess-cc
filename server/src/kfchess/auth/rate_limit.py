"""Rate limiting for authentication endpoints.

Uses SlowAPI to prevent brute-force attacks on login, registration,
and password reset endpoints.
"""

from collections.abc import Callable

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from kfchess.settings import get_settings

# Create the limiter instance using IP address as the key
limiter = Limiter(key_func=get_remote_address)

# Rate limit strings for different endpoints
# Format: "requests/period" (e.g., "5/minute", "3/hour")
LOGIN_LIMIT = "5/minute"
REGISTER_LIMIT = "3/minute"
FORGOT_PASSWORD_LIMIT = "3/minute"
VERIFY_LIMIT = "5/minute"
OAUTH_LIMIT = "10/minute"  # More lenient since OAuth involves redirects


def create_rate_limit_dependency(limit_string: str, name: str) -> Callable:
    """Create a rate limit dependency for use with FastAPI routers.

    This creates a dependency that can be added to router.include_router()
    to apply rate limiting to all routes in that router.

    Args:
        limit_string: Rate limit in format "requests/period" (e.g., "5/minute")
        name: Unique name for this rate limit (used by SlowAPI for tracking)

    Returns:
        An async dependency function that applies rate limiting
    """
    # Create the decorated function ONCE at dependency creation time,
    # not on every request. SlowAPI uses function identity to track limits.
    @limiter.limit(limit_string)
    async def _check_limit(request: Request, response: Response) -> None:
        pass

    # Give each function a unique name so SlowAPI tracks them separately
    _check_limit.__name__ = f"_check_limit_{name}"

    async def rate_limit_dependency(request: Request, response: Response) -> None:
        """Apply rate limiting to this request."""
        # Skip rate limiting if disabled (e.g., during tests)
        if not get_settings().rate_limiting_enabled:
            return

        await _check_limit(request, response)

    return rate_limit_dependency


# Pre-built dependencies for common rate limits
login_rate_limit = create_rate_limit_dependency(LOGIN_LIMIT, "login")
register_rate_limit = create_rate_limit_dependency(REGISTER_LIMIT, "register")
forgot_password_rate_limit = create_rate_limit_dependency(FORGOT_PASSWORD_LIMIT, "forgot_password")
verify_rate_limit = create_rate_limit_dependency(VERIFY_LIMIT, "verify")
oauth_rate_limit = create_rate_limit_dependency(OAUTH_LIMIT, "oauth")
