"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "new@test.com",
        "password": "password123",
        "full_name": "New User",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "new@test.com"
    assert data["full_name"] == "New User"
    assert data["role"] == "user"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test that duplicate emails are rejected."""
    payload = {"email": "dup@test.com", "password": "password123", "full_name": "User"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 400
    assert "já cadastrado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Test successful login returns tokens."""
    await client.post("/api/v1/auth/register", json={
        "email": "login@test.com", "password": "password123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com", "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Test login with wrong password."""
    await client.post("/api/v1/auth/register", json={
        "email": "wrong@test.com", "password": "password123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "wrong@test.com", "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    """Test authenticated /me endpoint."""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@test.com"
    assert data["full_name"] == "Test User"


@pytest.mark.asyncio
async def test_get_me_no_auth(client: AsyncClient):
    """Test /me without token returns 403."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """Test token refresh flow."""
    await client.post("/api/v1/auth/register", json={
        "email": "refresh@test.com", "password": "password123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "refresh@test.com", "password": "password123",
    })
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()
