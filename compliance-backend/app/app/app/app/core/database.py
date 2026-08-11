"""
Async database engine and session factory.
Uses SQLAlchemy 2.0 async pattern.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs = dict(
    echo=settings.DEBUG,
)
if not _is_sqlite:
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


async def get_db() -> AsyncSession:
    """Dependency that yields a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
