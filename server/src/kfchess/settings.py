"""Application configuration."""

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

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "noreply@kfchess.com"

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

    @property
    def google_oauth_enabled(self) -> bool:
        """Check if Google OAuth is configured."""
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def s3_enabled(self) -> bool:
        """Check if S3 is configured."""
        return bool(self.aws_access_key_id and self.aws_secret_access_key and self.aws_bucket)

    @property
    def resend_enabled(self) -> bool:
        """Check if Resend email service is configured."""
        return bool(self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
