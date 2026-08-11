"""
Shared test fixtures for ComplianceAI.

Uses SQLite async for fast, isolated tests.
"""
import os
os.environ["RATE_LIMIT_ENABLED"] = "false"

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app import User

app.state.limiter.enabled = False

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

engine_test = create_async_engine(TEST_DB_URL, echo=False)


@event.listens_for(engine_test.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _record):
    """Liga as foreign keys no SQLite.

    O SQLite as ignora por padrao, entao ON DELETE CASCADE e SET NULL nao rodariam
    nos testes, mesmo valendo no Postgres. Sem isto, a suite passa em cenarios que
    quebrariam em producao.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
TestSession = async_sessionmaker(
    bind=engine_test, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    """Override the database dependency for tests."""
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop after."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Register a test user and return auth headers."""
    await client.post("/api/v1/auth/register", json={
        "email": "test@test.com",
        "password": "test123456",
        "full_name": "Test User",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "test@test.com",
        "password": "test123456",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """Register an admin user and return auth headers."""
    # Create admin directly in DB
    async with TestSession() as db:
        admin = User(
            email="admin@test.com",
            password_hash=hash_password("admin123456"),
            full_name="Admin User",
            role="admin",
        )
        db.add(admin)
        await db.commit()

    resp = await client.post("/api/v1/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123456",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
