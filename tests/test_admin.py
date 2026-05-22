import pytest
from unittest.mock import patch
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

ADMIN_EMAIL = "admin_test@smartdocmerger.com"


async def _make_admin_client(client: AsyncClient) -> AsyncClient:
    with patch("app.config.settings.ENVIRONMENT", "development"):
        await client.post("/auth/register", json={
            "email": ADMIN_EMAIL,
            "full_name": "Admin",
            "password": "adminpass123",
        })
    resp = await client.post("/auth/login", json={
        "email": ADMIN_EMAIL, "password": "adminpass123"
    })
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    return client


async def test_admin_me(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        resp = await ac.get("/admin/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


async def test_non_admin_blocked(auth_client: AsyncClient):
    with patch("app.config.settings.ADMIN_EMAIL", "somebody_else@test.com"):
        resp = await auth_client.get("/admin/me")
    assert resp.status_code == 403


async def test_list_users(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        resp = await ac.get("/admin/users")
    assert resp.status_code == 200
    assert "items" in resp.json()


async def test_create_user(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        resp = await ac.post("/admin/users", json={
            "email": "tharushi@sherlockit.com",
            "full_name": "Tharushi",
            "password": "password123",
            "send_welcome": True,
        })
    assert resp.status_code == 201
    assert resp.json()["email"] == "tharushi@sherlockit.com"


async def test_create_duplicate_email(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        await ac.post("/admin/users", json={
            "email": "dup3@sherlockit.com", "full_name": "A", "password": "password123"
        })
        resp = await ac.post("/admin/users", json={
            "email": "dup3@sherlockit.com", "full_name": "B", "password": "password123"
        })
    assert resp.status_code == 400


async def test_create_weak_password(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        resp = await ac.post("/admin/users", json={
            "email": "weak3@sherlockit.com", "full_name": "W", "password": "123"
        })
    assert resp.status_code == 400


async def test_deactivate_reactivate(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        cr = await ac.post("/admin/users", json={
            "email": "deact3@sherlockit.com", "full_name": "D", "password": "password123"
        })
        uid = cr.json()["id"]
        assert (await ac.post(f"/admin/users/{uid}/deactivate")).status_code == 200
        assert (await ac.post(f"/admin/users/{uid}/reactivate")).status_code == 200


async def test_reset_password(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        cr = await ac.post("/admin/users", json={
            "email": "resetpw3@sherlockit.com", "full_name": "R", "password": "password123"
        })
        uid = cr.json()["id"]
        resp = await ac.post(f"/admin/users/{uid}/reset-password", json={"new_password": "newpass456"})
    assert resp.status_code == 200


async def test_generate_token(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        cr = await ac.post("/admin/users", json={
            "email": "gentoken3@sherlockit.com", "full_name": "G", "password": "password123"
        })
        uid = cr.json()["id"]
        resp = await ac.post(f"/admin/users/{uid}/generate-token")
    assert resp.status_code == 200
    assert "token" in resp.json()


async def test_delete_user(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        cr = await ac.post("/admin/users", json={
            "email": "deleteme3@sherlockit.com", "full_name": "Del", "password": "password123"
        })
        uid = cr.json()["id"]
        assert (await ac.delete(f"/admin/users/{uid}")).status_code == 204


async def test_cannot_delete_self(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        my_id = (await ac.get("/auth/me")).json()["id"]
        resp = await ac.delete(f"/admin/users/{my_id}")
    assert resp.status_code == 400


async def test_cannot_deactivate_self(client: AsyncClient):
    ac = await _make_admin_client(client)
    with patch("app.config.settings.ADMIN_EMAIL", ADMIN_EMAIL):
        my_id = (await ac.get("/auth/me")).json()["id"]
        resp = await ac.post(f"/admin/users/{my_id}/deactivate")
    assert resp.status_code == 400


async def test_public_registration_blocked_in_production(client: AsyncClient):
    with patch("app.config.settings.ENVIRONMENT", "production"):
        resp = await client.post("/auth/register", json={
            "email": "sneaky2@test.com", "full_name": "Sneaky", "password": "password123"
        })
    assert resp.status_code == 403
