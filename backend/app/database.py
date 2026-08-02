from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=(settings.app_env == "development"))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class base(DeclarativeBase):
    """Base class for all ORM models. Tables are created by database /schema.sql, not by SQLAlchemy metadata - these classes exist for querying only."""
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency - yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session