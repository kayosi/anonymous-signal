"""Async database connection pool and session management."""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.models import Base

# Disable SSL for local Docker connections
_db_url = settings.DATABASE_URL
if "?" not in _db_url:
    _db_url += "?ssl=disable"
elif "ssl=" not in _db_url:
    _db_url += "&ssl=disable"

engine = create_async_engine(
    _db_url,
    echo=False,
    poolclass=NullPool if settings.ENVIRONMENT == "testing" else None,
    pool_pre_ping=True,
    connect_args={"ssl": None},  # Explicitly disable SSL
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def create_db_and_tables():
    """Create all tables on startup — retries until Postgres is ready."""
    max_retries = 10
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return  # Success
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s, 8s...
                print(f"DB not ready (attempt {attempt+1}/{max_retries}), retrying in {wait}s... ({e})")
                await asyncio.sleep(wait)
            else:
                raise


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()