"""
Integration tests for the Webhooks API + unit tests for webhook_service (FASE 3).

Webhook CRUD is admin-only. The service tests mock httpx to avoid real HTTP calls.
"""
import sys
from unittest.mock import MagicMock, patch, AsyncMock

# ─── Mock Celery/Redis ───
_fake_task_result = MagicMock()
_fake_task_result.id = "fake-celery-task-id"
_mock_tasks = MagicMock()
_mock_tasks.analyze_document_task.delay.return_value = _fake_task_result
sys.modules.setdefault("app.workers.tasks", _mock_tasks)

import pytest
from httpx import AsyncClient


# ─── Webhook CRUD (Admin only) ───────────────────────────────────────────────

async def test_create_webhook(client: AsyncClient, admin_headers: dict):
    resp = await client.post("/api/v1/webhooks", json={
        "name": "Notificação Slack",
        "url": "https://hooks.slack.com/test",
        "events": ["document.analyzed", "workflow.approved"],
    }, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Notificação Slack"
    assert "document.analyzed" in data["events"]
    assert data["is_active"] is True


async def test_create_webhook_invalid_event(client: AsyncClient, admin_headers: dict):
    resp = await client.post("/api/v1/webhooks", json={
        "name": "Bad Events",
        "url": "https://example.com/hook",
        "events": ["invalid.event"],
    }, headers=admin_headers)
    assert resp.status_code == 400
    assert "inválidos" in resp.json()["detail"].lower()


async def test_create_webhook_non_admin_forbidden(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/webhooks", json={
        "name": "Forbidden", "url": "https://example.com",
    }, headers=auth_headers)
    assert resp.status_code == 403


async def test_create_webhook_unauthenticated(client: AsyncClient):
    resp = await client.post("/api/v1/webhooks", json={
        "name": "Unauth", "url": "https://example.com",
    })
    assert resp.status_code == 403


async def test_list_webhooks_empty(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/webhooks", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["webhooks"] == []


async def test_list_webhooks_after_create(client: AsyncClient, admin_headers: dict):
    await client.post("/api/v1/webhooks", json={
        "name": "Hook A", "url": "https://a.com/hook",
    }, headers=admin_headers)
    await client.post("/api/v1/webhooks", json={
        "name": "Hook B", "url": "https://b.com/hook",
    }, headers=admin_headers)
    resp = await client.get("/api/v1/webhooks", headers=admin_headers)
    assert resp.json()["total"] == 2


async def test_get_webhook(client: AsyncClient, admin_headers: dict):
    create_resp = await client.post("/api/v1/webhooks", json={
        "name": "Get Test", "url": "https://example.com/hook",
    }, headers=admin_headers)
    wh_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/webhooks/{wh_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


async def test_get_webhook_not_found(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/webhooks/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert resp.status_code == 404


async def test_update_webhook(client: AsyncClient, admin_headers: dict):
    create_resp = await client.post("/api/v1/webhooks", json={
        "name": "Old", "url": "https://old.com/hook",
    }, headers=admin_headers)
    wh_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/v1/webhooks/{wh_id}", json={
        "name": "Updated",
        "url": "https://new.com/hook",
        "events": ["document.uploaded"],
        "is_active": False,
    }, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated"
    assert data["url"] == "https://new.com/hook"
    assert data["is_active"] is False


async def test_update_webhook_invalid_events(client: AsyncClient, admin_headers: dict):
    create_resp = await client.post("/api/v1/webhooks", json={
        "name": "Update Bad", "url": "https://example.com",
    }, headers=admin_headers)
    wh_id = create_resp.json()["id"]

    resp = await client.patch(f"/api/v1/webhooks/{wh_id}", json={
        "events": ["bad.event"],
    }, headers=admin_headers)
    assert resp.status_code == 400


async def test_delete_webhook(client: AsyncClient, admin_headers: dict):
    create_resp = await client.post("/api/v1/webhooks", json={
        "name": "To Delete", "url": "https://example.com",
    }, headers=admin_headers)
    wh_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/webhooks/{wh_id}", headers=admin_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/webhooks/{wh_id}", headers=admin_headers)
    assert resp.status_code == 404


# ─── Webhook Service Unit Tests ──────────────────────────────────────────────

class TestWebhookService:
    """Unit tests for dispatch_webhook and _compute_signature."""

    def test_compute_signature(self):
        from app.services.webhook_service import _compute_signature
        sig = _compute_signature(b'{"event":"test"}', "my-secret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex digest

    def test_compute_signature_consistency(self):
        from app.services.webhook_service import _compute_signature
        payload = b'{"data":"test"}'
        sig1 = _compute_signature(payload, "secret")
        sig2 = _compute_signature(payload, "secret")
        assert sig1 == sig2

    def test_compute_signature_different_secrets(self):
        from app.services.webhook_service import _compute_signature
        payload = b'{"data":"test"}'
        sig1 = _compute_signature(payload, "secret1")
        sig2 = _compute_signature(payload, "secret2")
        assert sig1 != sig2

    @pytest.mark.asyncio
    async def test_dispatch_webhook_success(self):
        from app.services.webhook_service import dispatch_webhook

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await dispatch_webhook(
                url="https://example.com/hook",
                event="document.analyzed",
                data={"document_id": "123"},
                secret="my-secret",
            )

        assert result is True
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_webhook_failure(self):
        from app.services.webhook_service import dispatch_webhook

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await dispatch_webhook(
                url="https://example.com/hook",
                event="document.analyzed",
                data={},
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_dispatch_webhook_timeout(self):
        from app.services.webhook_service import dispatch_webhook
        import httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.webhook_service.httpx.AsyncClient", return_value=mock_client):
            result = await dispatch_webhook(
                url="https://example.com/hook",
                event="test",
                data={},
            )

        assert result is False
