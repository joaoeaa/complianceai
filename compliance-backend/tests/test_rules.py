"""Tests for rules CRUD endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_rule_as_admin(client: AsyncClient, admin_headers: dict):
    """Admin can create rules."""
    resp = await client.post("/api/v1/rules", json={
        "name": "Test Rule",
        "description": "Test description",
        "severity": "high",
        "criteria": "Verify something specific",
    }, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Rule"
    assert data["severity"] == "high"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_rule_as_user_forbidden(client: AsyncClient, auth_headers: dict):
    """Regular users cannot create rules."""
    resp = await client.post("/api/v1/rules", json={
        "name": "Blocked Rule",
        "criteria": "Should fail",
    }, headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_rules(client: AsyncClient, admin_headers: dict, auth_headers: dict):
    """Any authenticated user can list rules."""
    # Create a rule as admin
    await client.post("/api/v1/rules", json={
        "name": "Listed Rule", "criteria": "Check something",
    }, headers=admin_headers)

    # List as regular user
    resp = await client.get("/api/v1/rules", headers=auth_headers)
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 1
    assert any(r["name"] == "Listed Rule" for r in rules)


@pytest.mark.asyncio
async def test_update_rule(client: AsyncClient, admin_headers: dict):
    """Admin can update rules."""
    create_resp = await client.post("/api/v1/rules", json={
        "name": "Update Me", "criteria": "Original criteria",
    }, headers=admin_headers)
    rule_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/v1/rules/{rule_id}", json={
        "name": "Updated Name", "severity": "low",
    }, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"
    assert resp.json()["severity"] == "low"


@pytest.mark.asyncio
async def test_delete_rule(client: AsyncClient, admin_headers: dict):
    """Admin can delete rules."""
    create_resp = await client.post("/api/v1/rules", json={
        "name": "Delete Me", "criteria": "To be deleted",
    }, headers=admin_headers)
    rule_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/rules/{rule_id}", headers=admin_headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_toggle_rule(client: AsyncClient, admin_headers: dict):
    """Admin can toggle rule active state."""
    create_resp = await client.post("/api/v1/rules", json={
        "name": "Toggle Me", "criteria": "Toggleable",
    }, headers=admin_headers)
    rule_id = create_resp.json()["id"]

    # Should start active
    assert create_resp.json()["is_active"] is True

    # Toggle off
    resp = await client.patch(f"/api/v1/rules/{rule_id}/toggle", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Toggle on
    resp = await client.patch(f"/api/v1/rules/{rule_id}/toggle", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True
