# User Authentication Design

This document describes the design and implementation of user authentication in Kung Fu Chess, with full backwards compatibility for legacy users.

> **Status: IMPLEMENTED** - All phases complete. See [Implementation Status](#implementation-status) for details.

---

## Table of Contents

1. [Implementation Status](#implementation-status)
2. [Overview](#overview)
3. [Legacy System Analysis](#legacy-system-analysis)
4. [Database Schema](#database-schema)
5. [Backend Architecture](#backend-architecture)
6. [API Endpoints](#api-endpoints)
7. [Frontend Integration](#frontend-integration)
8. [Security Features](#security-features)
9. [Migration Strategy](#migration-strategy)
10. [Testing](#testing)

---

## Implementation Status

All authentication features have been implemented and tested.

### Completed Features

| Feature | Status | Notes |
|---------|--------|-------|
| Email/password registration | ✅ Complete | With auto-generated usernames |
| Email/password login | ✅ Complete | Cookie-based JWT, 30-day lifetime |
| Google OAuth | ✅ Complete | Full flow with legacy user migration |
| Email verification | ✅ Complete | Via Resend, optional for login |
| Password reset | ✅ Complete | Token-based, 1-hour expiry |
| Rate limiting | ✅ Complete | Per-endpoint limits via SlowAPI |
| DEV_MODE bypass | ✅ Complete | Auto-login for development |
| Frontend pages | ✅ Complete | Login, Register, Verify, Reset Password |
| Verification banner | ✅ Complete | With client-side rate limiting |

### File Structure (Implemented)

```
server/src/kfchess/auth/
├── __init__.py          # Module exports
├── schemas.py           # UserRead, UserCreate, UserUpdate
├── users.py             # UserManager with OAuth + legacy support
├── backend.py           # Cookie-based JWT authentication
├── dependencies.py      # current_user, DEV_MODE bypass
├── router.py            # Route registration with rate limiting
├── email.py             # Resend email integration
└── rate_limit.py        # SlowAPI rate limiting

client/src/
├── pages/
│   ├── Login.tsx           # Email/password + Google OAuth
│   ├── Register.tsx        # Registration with optional username
│   ├── ForgotPassword.tsx  # Request password reset
│   ├── ResetPassword.tsx   # Set new password
│   ├── Verify.tsx          # Email verification handler
│   └── GoogleCallback.tsx  # OAuth callback handler
├── components/
│   ├── AuthProvider.tsx    # Auto-fetch user on load
│   └── layout/Header.tsx   # Verification banner + user menu
└── stores/auth.ts          # Zustand auth state
```

---

## Overview

### Goals

1. **Backwards Compatibility**: Preserve existing user IDs, usernames, emails, and ratings
2. **Dual Authentication**: Support both email/password AND Google OAuth
3. **Legacy Migration**: Existing Google-only users must continue working seamlessly
4. **DEV_MODE Bypass**: Auto-login for development without credentials

### Technology Choices

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Auth Library | FastAPI-Users 14+ | Battle-tested, handles OAuth, password reset, email verification |
| Password Hashing | passlib + bcrypt | Industry standard, already in dependencies |
| Session Management | Cookie-based JWT | 30-day tokens, httponly cookies for security |
| OAuth | httpx-oauth | FastAPI-Users integration for Google OAuth |

---

## Legacy System Analysis

### Existing Users Table (from ../kfchess)

```sql
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT UNIQUE,
    username      TEXT UNIQUE,
    picture_url   TEXT,
    ratings       JSONB,
    join_time     TIMESTAMP WITHOUT TIME ZONE,
    last_online   TIMESTAMP WITHOUT TIME ZONE,
    current_game  JSONB
);
```

### Legacy Authentication Flow

1. **Google OAuth Only** - No email/password support
2. **Email as Google ID** - The `email` field stores the Google email and is used for OAuth lookup
3. **Random Usernames** - Generated on first login: "Tiger Pawn 456" format
4. **Flask-Login Sessions** - Server-side session management
5. **CSRF Tokens** - Generated per-session for form protection

### Compatibility Constraints

- User IDs must remain BIGINT (not UUID) to preserve foreign key references
- Existing usernames and emails must be preserved exactly
- Legacy users (Google OAuth) must be able to login without any action
- Ratings data (JSONB) must be preserved

---

## Database Schema

### Users Table (New Schema)

```sql
CREATE TABLE users (
    -- Preserved from legacy
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    username VARCHAR(50) UNIQUE NOT NULL,
    picture_url TEXT,
    ratings JSONB DEFAULT '{}' NOT NULL,

    -- NEW: Authentication fields
    hashed_password VARCHAR(255),           -- NULL for Google-only users
    google_id VARCHAR(255) UNIQUE,          -- Extracted from email for OAuth lookup

    -- NEW: FastAPI-Users required fields
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE NOT NULL,
    is_superuser BOOLEAN DEFAULT FALSE NOT NULL,

    -- Timestamps (renamed from join_time)
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL,
    last_online TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL
);

-- Indexes
CREATE INDEX ix_users_email ON users(email);
CREATE INDEX ix_users_username ON users(username);
CREATE INDEX ix_users_google_id ON users(google_id);
```

### OAuth Accounts Table (New)

Required by FastAPI-Users for storing OAuth tokens:

```sql
CREATE TABLE oauth_accounts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    oauth_name VARCHAR(100) NOT NULL,       -- "google"
    access_token VARCHAR(1024) NOT NULL,
    expires_at INTEGER,
    refresh_token VARCHAR(1024),
    account_id VARCHAR(320) NOT NULL,       -- Google's user ID
    account_email VARCHAR(320),

    CONSTRAINT oauth_accounts_user_provider_unique UNIQUE(user_id, oauth_name)
);

CREATE INDEX ix_oauth_accounts_user ON oauth_accounts(user_id);
CREATE INDEX ix_oauth_accounts_provider ON oauth_accounts(oauth_name, account_id);
```

### Schema Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ID Type | BIGINT | Backwards compatibility with legacy BIGSERIAL |
| `hashed_password` nullable | Yes | Google-only users have no password |
| `google_id` field | Separate from email | Clean OAuth lookup, supports email changes |
| `is_verified` default | FALSE | New email users need verification; legacy users set to TRUE in migration |
| `current_game` column | Removed | Will use Redis for active game state instead |

---

## Backend Architecture

### Module Structure

```
server/src/kfchess/auth/
    __init__.py          # Module exports
    schemas.py           # Pydantic schemas (UserRead, UserCreate, UserUpdate)
    users.py             # UserManager with custom logic
    backend.py           # Cookie-based JWT authentication backend
    dependencies.py      # FastAPIUsers instance, current_user dependencies
    router.py            # Route registration
```

### User Model (SQLAlchemy)

```python
# server/src/kfchess/db/models.py

class OAuthAccount(SQLAlchemyBaseOAuthAccountTable[int], Base):
    """OAuth account linked to a user."""
    __tablename__ = "oauth_accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class User(SQLAlchemyBaseUserTable[int], Base):
    """User model supporting both email/password and Google OAuth."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # FastAPI-Users required
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # Application-specific
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    picture_url: Mapped[str | None] = mapped_column(String, nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    ratings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_online: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship("OAuthAccount", lazy="joined")
```

### Pydantic Schemas

```python
# server/src/kfchess/auth/schemas.py

class UserRead(schemas.BaseUser[int]):
    """Schema for reading user data (API responses)."""
    username: str
    picture_url: str | None = None
    google_id: str | None = None
    ratings: dict = Field(default_factory=dict)
    created_at: datetime
    last_online: datetime


class UserCreate(schemas.BaseUserCreate):
    """Schema for user registration."""
    username: str | None = None  # Auto-generated if not provided


class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating user profile."""
    username: str | None = None
    picture_url: str | None = None
```

### UserManager (Custom Logic)

```python
# server/src/kfchess/auth/users.py

ANIMALS = ["Tiger", "Leopard", "Crane", "Snake", "Dragon"]
CHESS_PIECES = ["Pawn", "Knight", "Bishop", "Rook", "Queen", "King"]

def generate_random_username() -> str:
    """Generate username like 'Tiger Pawn 456'."""
    animal = random.choice(ANIMALS)
    piece = random.choice(CHESS_PIECES)
    number = random.randint(100, 999)
    return f"{animal} {piece} {number}"


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """Custom user manager with application-specific logic."""

    reset_password_token_secret = get_settings().secret_key
    verification_token_secret = get_settings().secret_key

    async def create(self, user_create, safe=False, request=None) -> User:
        """Create user with auto-generated username if not provided."""
        if not getattr(user_create, 'username', None):
            # Generate unique random username
            for _ in range(10):
                username = generate_random_username()
                # Check uniqueness (implementation details omitted)
                if await self._is_username_available(username):
                    break
            user_create.username = username

        return await super().create(user_create, safe, request)

    async def oauth_callback(self, oauth_name, access_token, account_id, ...):
        """Handle OAuth with legacy user migration support."""
        # First check for legacy user by google_id
        user = await self._find_user_by_google_id(account_id)
        if user:
            # Update OAuth tokens and return existing user
            await self._update_oauth_tokens(user, ...)
            return user

        # Fall back to standard FastAPI-Users OAuth flow
        return await super().oauth_callback(...)
```

### Authentication Backend

```python
# server/src/kfchess/auth/backend.py

cookie_transport = CookieTransport(
    cookie_name="kfchess_auth",
    cookie_max_age=3600 * 24 * 30,  # 30 days
    cookie_secure=True,              # HTTPS only in production
    cookie_httponly=True,            # Not accessible via JavaScript
    cookie_samesite="lax",           # CSRF protection
)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=get_settings().secret_key,
        lifetime_seconds=3600 * 24 * 30,  # 30 days
    )

auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)
```

### DEV_MODE Bypass

```python
# server/src/kfchess/auth/dependencies.py

async def get_current_user_with_dev_bypass(
    request: Request,
    user: Annotated[User | None, Depends(optional_current_user)],
) -> User | None:
    """Get current user with DEV_MODE bypass.

    In DEV_MODE with DEV_USER_ID set, automatically returns that user
    without requiring authentication.
    """
    settings = get_settings()

    if settings.dev_mode and settings.dev_user_id is not None:
        async with async_session_factory() as session:
            repo = UserRepository(session)
            dev_user = await repo.get_by_id(settings.dev_user_id)
            if dev_user:
                return dev_user

    return user
```

---

## API Endpoints

### Endpoints Provided by FastAPI-Users

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Register with email/password |
| `/api/auth/login` | POST | Login with email/password (form-encoded) |
| `/api/auth/logout` | POST | Clear auth cookie |
| `/api/auth/forgot-password` | POST | Request password reset email |
| `/api/auth/reset-password` | POST | Reset password with token |
| `/api/auth/request-verify-token` | POST | Request email verification |
| `/api/auth/verify` | POST | Verify email with token |
| `/api/users/me` | GET | Get current authenticated user |
| `/api/users/me` | PATCH | Update current user profile |
| `/api/auth/google/authorize` | GET | Start Google OAuth flow |
| `/api/auth/google/callback` | GET | Google OAuth callback |

### Request/Response Examples

**Registration:**
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "player@example.com",
  "password": "securepassword123",
  "username": "ChessMaster"  // Optional, auto-generated if omitted
}
```

**Login:**
```http
POST /api/auth/login
Content-Type: application/x-www-form-urlencoded

username=player@example.com&password=securepassword123
```

**Get Current User:**
```http
GET /api/users/me
Cookie: kfchess_auth=<jwt_token>

Response:
{
  "id": 1,
  "email": "player@example.com",
  "username": "ChessMaster",
  "picture_url": null,
  "ratings": {"standard": 1200, "lightning": 1200},
  "is_active": true,
  "is_verified": true,
  "is_superuser": false,
  "created_at": "2024-01-15T10:30:00Z",
  "last_online": "2024-01-20T15:45:00Z"
}
```

---

## Frontend Integration

### Auth Store (Zustand)

```typescript
// client/src/stores/auth.ts

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => void;
  register: (email: string, password: string, username?: string) => Promise<void>;
  logout: () => Promise<void>;
  fetchCurrentUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  // ... state

  login: async (email, password) => {
    const formData = new URLSearchParams();
    formData.append('username', email);  // FastAPI-Users convention
    formData.append('password', password);

    await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
      credentials: 'include',  // Include cookies
    });

    await get().fetchCurrentUser();
  },

  loginWithGoogle: () => {
    window.location.href = '/api/auth/google/authorize';
  },

  // ... other actions
}));
```

### New Pages Required

1. **`/login`** - Email/password form + "Login with Google" button
2. **`/register`** - Registration form with optional username
3. **`/forgot-password`** - Email input for password reset
4. **`/reset-password`** - New password form (token from URL)
5. **`/auth/google/callback`** - Handles OAuth redirect, fetches user

### AuthProvider Component

```typescript
// Wrap app to auto-fetch user on load
function AuthProvider({ children }) {
  const fetchCurrentUser = useAuthStore((s) => s.fetchCurrentUser);

  useEffect(() => {
    fetchCurrentUser();
  }, []);

  return children;
}
```

---

## Security Features

### Rate Limiting

Per-endpoint rate limits to prevent abuse:

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| Login | 5/minute | Prevent brute force |
| Register | 3/minute | Prevent spam accounts |
| Forgot Password | 3/minute | Prevent email bombing |
| Email Verification | 5/minute | Allow retries |
| Google OAuth | 10/minute | Higher for OAuth flow |

Rate limiting can be disabled via `RATE_LIMITING_ENABLED=false` for tests.

### Token Security

| Feature | Implementation |
|---------|----------------|
| JWT Cookies | httponly, samesite=lax, secure in production |
| Token Lifetime | 30 days for session, 1 hour for password reset |
| URL Token Clearing | Tokens removed from URL after extraction (prevents Referer leaks) |

### Email Security

- **No enumeration**: Forgot-password and request-verify always return 202 (don't reveal if email exists)
- **Async sending**: Emails sent in thread pool to avoid blocking
- **Graceful failures**: Email errors don't fail auth flows

### Frontend Security

- **Redirect validation**: Post-login redirects must start with `/`, no `://` or `//`
- **OAuth state validation**: Full CSRF protection for Google OAuth
- **Error sanitization**: Google errors mapped to safe user messages

---

## Migration Strategy

### Alembic Migration: `002_add_users.py`

The migration handles two scenarios:

1. **Fresh Install**: Create new users table with all columns
2. **Legacy Migration**: Add new columns to existing users table

```python
def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "users" in tables:
        # Legacy migration path
        _migrate_legacy_users()
    else:
        # Fresh install path
        _create_users_table()

    # Always create oauth_accounts table
    _create_oauth_accounts_table()


def _migrate_legacy_users():
    """Add new columns to existing users table."""
    # Add new columns
    op.add_column("users", sa.Column("hashed_password", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("is_active", sa.Boolean(), server_default="true"))
    op.add_column("users", sa.Column("is_verified", sa.Boolean(), server_default="false"))
    op.add_column("users", sa.Column("is_superuser", sa.Boolean(), server_default="false"))

    # Migrate data: copy email to google_id, mark as verified
    # (All legacy users are Google OAuth, so their email IS their Google identifier)
    op.execute("""
        UPDATE users
        SET google_id = email,
            is_verified = true,
            is_active = true
        WHERE google_id IS NULL AND email IS NOT NULL
    """)

    # Add indexes and constraints
    op.create_unique_constraint("uq_users_google_id", "users", ["google_id"])
    op.create_index("ix_users_google_id", "users", ["google_id"])
```

### Migration Safety

1. **Non-destructive**: Only adds columns, never removes or modifies existing data
2. **Idempotent**: Checks for existing table before deciding migration path
3. **Reversible**: Downgrade function removes added columns
4. **Data preserved**: All legacy user data remains intact

---

## Testing

### Test Coverage

| Category | Files | Tests |
|----------|-------|-------|
| Unit - Schemas | `test_schemas.py` | Password validation, username optional |
| Unit - Dependencies | `test_dependencies.py` | DEV_MODE bypass, user retrieval |
| Unit - Email | `test_email.py` | Send verification, send reset, failure handling |
| Integration - Login | `test_login_flow.py` | Login, logout, wrong password |
| Integration - Registration | `test_registration_flow.py` | Register, username generation, duplicates |
| Integration - OAuth | `test_google_oauth.py` | OAuth flow, legacy user migration |
| Integration - DEV_MODE | `test_dev_mode.py` | Auto-login bypass |

### Running Tests

```bash
# All tests (rate limiting auto-disabled)
cd server && uv run pytest tests/ -v

# Auth tests only
uv run pytest tests/unit/auth tests/integration/auth -v
```

---

## Configuration

### Environment Variables

```bash
# Required
SECRET_KEY=your-secret-key-here

# Google OAuth (optional - disables Google login if not set)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Email via Resend (optional - logs tokens if not set)
RESEND_API_KEY=...
EMAIL_FROM=noreply@kfchess.com
SEND_EMAILS=true  # Must be explicitly enabled

# Frontend URL (for email links and OAuth redirects)
FRONTEND_URL=http://localhost:5173

# Development
DEV_MODE=true
DEV_USER_ID=1
RATE_LIMITING_ENABLED=true  # Auto-disabled in tests
```

### Google Cloud Console Setup

For Google OAuth:

1. Create OAuth 2.0 Client ID (Web application)
2. Add authorized JavaScript origins:
   - `http://localhost:5173` (dev)
   - `https://www.kfchess.com` (prod)
3. Add authorized redirect URIs:
   - `http://localhost:5173/auth/google/callback` (dev)
   - `https://www.kfchess.com/auth/google/callback` (prod)
4. Enable People API in Google Cloud Console

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ID Type | BIGINT | Backwards compatibility with legacy |
| `hashed_password` nullable | Yes | Google-only users have no password |
| `google_id` field | Separate from email | Clean OAuth lookup, supports email changes |
| `is_verified` default | FALSE | New email users need verification |
| Cookie auth | 30-day JWT | Balance security and convenience |
| Random usernames | "Animal Piece Number" | Matches legacy format, reduces friction |
| Email optional | Yes | Users can login unverified |
| Rate limit toggleable | Yes | Disabled for tests automatically |

### Out of Scope

- **Account Linking**: Linking Google OAuth to existing email/password accounts
- **Session Invalidation**: "Logout everywhere" functionality
- **2FA**: Two-factor authentication
