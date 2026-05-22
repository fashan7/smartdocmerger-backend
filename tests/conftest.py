import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.main import app
from app.database import get_db, Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_smartdocmerger.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db

# Patch processor's AsyncSessionLocal so background tasks use test DB
import app.services.processor as _processor
_processor.AsyncSessionLocal = TestSessionLocal


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient):
    """Returns a client with a valid JWT token for test user."""
    await client.post("/auth/register", json={
        "email": "test@smartdocmerger.com",
        "full_name": "Test User",
        "password": "testpassword123",
    })
    response = await client.post("/auth/login", json={
        "email": "test@smartdocmerger.com",
        "password": "testpassword123",
    })
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
