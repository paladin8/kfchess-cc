"""Application configuration."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://kfchess:kfchess@localhost:5432/kfchess"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Security
    secret_key: str = "change-me-to-a-real-secret-key"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Lichess OAuth (PKCE, no client secret needed)
    lichess_client_id: str = "kfchess.com"

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "noreply@kfchess.com"
    send_emails: bool = False  # Must be explicitly enabled to send real emails

    # Inbound email forwarding
    resend_webhook_secret: str = ""  # whsec_xxx from Resend dashboard
    email_forward_to: str = ""  # Destination email for forwarded inbound emails

    # Frontend
    frontend_url: str = "http://localhost:5173"

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_bucket: str = ""
    aws_region: str = "us-west-2"

    # Development mode
    dev_mode: bool = False
    dev_user_id: int | None = None

    # Rate limiting (disable for tests)
    rate_limiting_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    @property
    def effective_server_id(self) -> str:
        """Get server ID for active game tracking.

        Resolution order:
          1. KFCHESS_SERVER_ID env var (set per-process, not in .env)
          2. Fallback: hostname-pid (unique but won't survive restarts)

        For multiple processes sharing the same .env, launch each with a
        stable ID: ``KFCHESS_SERVER_ID=worker1 uvicorn ...``
        """
        from_env = os.environ.get("KFCHESS_SERVER_ID")
        if from_env:
            return from_env
        return f"{os.uname().nodename}-{os.getpid()}"

    @property
    def google_oauth_enabled(self) -> bool:
        """Check if Google OAuth is configured."""
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def lichess_oauth_enabled(self) -> bool:
        """Check if Lichess OAuth is configured."""
        return bool(self.lichess_client_id)

    @property
    def s3_enabled(self) -> bool:
        """Check if S3 is configured."""
        return bool(self.aws_access_key_id and self.aws_secret_access_key and self.aws_bucket)

    @property
    def resend_enabled(self) -> bool:
        """Check if Resend email service is configured."""
        return bool(self.resend_api_key)

    @property
    def inbound_email_enabled(self) -> bool:
        """Check if inbound email webhook forwarding is configured."""
        return bool(self.resend_webhook_secret and self.email_forward_to and self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
