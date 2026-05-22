import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register(client: AsyncClient):
    response = await client.post("/auth/register", json={
        "email": "newuser@test.com",
        "full_name": "New User",
        "password": "password123",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["email"] == "newuser@test.com"


async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/auth/register", json={
        "email": "dup@test.com",
        "full_name": "User One",
        "password": "password123",
    })
    response = await client.post("/auth/register", json={
        "email": "dup@test.com",
        "full_name": "User Two",
        "password": "password456",
    })
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


async def test_register_weak_password(client: AsyncClient):
    response = await client.post("/auth/register", json={
        "email": "weak@test.com",
        "full_name": "Weak",
        "password": "123",
    })
    assert response.status_code == 400


async def test_login_success(client: AsyncClient):
    await client.post("/auth/register", json={
        "email": "logintest@test.com",
        "full_name": "Login Test",
        "password": "password123",
    })
    response = await client.post("/auth/login", json={
        "email": "logintest@test.com",
        "password": "password123",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


async def test_login_wrong_password(client: AsyncClient):
    await client.post("/auth/register", json={
        "email": "wrongpass@test.com",
        "full_name": "Wrong Pass",
        "password": "correctpassword",
    })
    response = await client.post("/auth/login", json={
        "email": "wrongpass@test.com",
        "password": "wrongpassword",
    })
    assert response.status_code == 401


async def test_me(auth_client: AsyncClient):
    response = await auth_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@smartdocmerger.com"


async def test_me_unauthenticated(client: AsyncClient):
    response = await client.get("/auth/me")
    assert response.status_code in (401, 403)  # No bearer token


async def test_change_password(auth_client: AsyncClient):
    response = await auth_client.post("/auth/change-password", json={
        "current_password": "testpassword123",
        "new_password": "newpassword456",
    })
    assert response.status_code == 200

    # Change back
    await auth_client.post("/auth/change-password", json={
        "current_password": "newpassword456",
        "new_password": "testpassword123",
    })


async def test_change_password_wrong_current(auth_client: AsyncClient):
    response = await auth_client.post("/auth/change-password", json={
        "current_password": "wrongpassword",
        "new_password": "newpassword456",
    })
    assert response.status_code == 400
