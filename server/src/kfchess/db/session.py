"""Database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kfchess.settings import get_settings

# Create async engine
_engine = create_async_engine(
    get_settings().database_url,
    echo=False,
    pool_pre_ping=True,
)

# Create session factory
async_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session.

    Usage:
        async with get_db_session() as session:
            # use session

    Or as a FastAPI dependency:
        session: AsyncSession = Depends(get_db_session)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncSession:
    """Get a database session (non-generator version).

    Caller is responsible for committing and closing the session.
    """
    return async_session_factory()
