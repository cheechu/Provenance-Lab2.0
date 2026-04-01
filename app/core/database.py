"""
CasAI Provenance Lab — Async Database Layer
SQLAlchemy 2.x async engine + session factory.
Supports SQLite (dev) and PostgreSQL (prod) via DATABASE_URL.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    # SQLite-specific: allow use across threads (needed for async)
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass

# ---------------------------------------------------------------------------
# Dependency: yields a DB session per request
# ---------------------------------------------------------------------------

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Startup: create all tables
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create all tables if they don't exist. Called at app startup."""
    import app.models.db_models  # noqa: F401 — ensures models are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
