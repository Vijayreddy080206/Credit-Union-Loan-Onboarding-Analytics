"""
Async SQLAlchemy engine and session factory.

Design note: we use async SQLAlchemy (create_async_engine + AsyncSession) so
database I/O does not block the FastAPI event loop. This lets a single process
handle many concurrent requests while waiting for Postgres.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,          # logs all SQL in development
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,           # test connection before using from pool
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,       # avoids lazy-load errors after commit
)


class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass


async def get_db() -> AsyncSession:
    """
    FastAPI dependency that yields a database session per request.
    The session is committed if no error occurs, rolled back otherwise,
    and always closed — even if an exception is raised mid-request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
