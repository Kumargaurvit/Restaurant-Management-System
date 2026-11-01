import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Settings requires JWT_SECRET_KEY. Give tests a value so they run without a real .env.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # cheap hashing keeps the suite fast

from restaurant_management_system.config import get_settings  # noqa: E402
from restaurant_management_system.db.base import Base  # noqa: E402
from restaurant_management_system.db.session import get_session  # noqa: E402
from restaurant_management_system.main import create_app  # noqa: E402
from tests.helpers import bearer  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A fresh in-memory SQLite database for each test."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def app(engine: AsyncEngine):
    application = create_app()
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with sessionmaker() as session:
            yield session

    application.dependency_overrides[get_session] = override_session
    return application


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def owner_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/bootstrap",
        json={
            "name": "Owner",
            "email": "owner@test.com",
            "password": "password123",
            "restaurant_name": "Spice Garden",
        },
    )
    return bearer(response.json()["access_token"])


@pytest.fixture
def make_staff(client: AsyncClient, owner_headers: dict[str, str]):
    async def _make(role: str) -> dict[str, str]:
        email = f"{role}@test.com"
        await client.post(
            "/api/auth/users",
            headers=owner_headers,
            json={"name": role.title(), "email": email, "password": "password123", "role": role},
        )
        login = await client.post(
            "/api/auth/login", json={"email": email, "password": "password123"}
        )
        return bearer(login.json()["access_token"])

    return _make


@pytest.fixture
async def menu(client: AsyncClient, owner_headers: dict[str, str]) -> dict[str, int]:
    """One category, two items (5% and 18% GST), and one table."""
    category = await client.post(
        "/api/billing/menu/categories", headers=owner_headers, json={"name": "Mains"}
    )
    category_id = category.json()["id"]
    paneer = await client.post(
        "/api/billing/menu/items",
        headers=owner_headers,
        json={"category_id": category_id, "name": "Paneer Tikka", "price": "200.00", "gst_rate": "5"},
    )
    cola = await client.post(
        "/api/billing/menu/items",
        headers=owner_headers,
        json={"category_id": category_id, "name": "Cola", "price": "50.00", "gst_rate": "18"},
    )
    table = await client.post(
        "/api/billing/tables", headers=owner_headers, json={"name": "T1", "capacity": 4}
    )
    return {
        "category_id": category_id,
        "paneer_id": paneer.json()["id"],
        "cola_id": cola.json()["id"],
        "table_id": table.json()["id"],
    }
