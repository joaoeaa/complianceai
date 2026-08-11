"""
Integration tests for the Approval Workflows API (FASE 3).

Tests cover workflow creation, state transitions, permissions, and listing.
"""
import sys
from unittest.mock import MagicMock

# ─── Mock Celery/Redis ───
_fake_task_result = MagicMock()
_fake_task_result.id = "fake-celery-task-id"
_mock_tasks = MagicMock()
_mock_tasks.analyze_document_task.delay.return_value = _fake_task_result
sys.modules.setdefault("app.workers.tasks", _mock_tasks)

from functools import lru_cache

import pytest
from httpx import AsyncClient


# ─── Helpers ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _pdf_bytes() -> bytes:
    """A real PDF with extractable text — the upload endpoint parses the file."""
    from weasyprint import HTML

    return HTML(string="<p>Contrato de teste para workflow de aprovacao.</p>").write_pdf()


async def _upload_doc(client: AsyncClient, headers: dict, filename: str = "contract.pdf") -> str:
    """Upload a document and return its ID."""
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, _pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["document_id"]


# ─── Workflow CRUD ────────────────────────────────────────────────────────────

async def test_create_workflow(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    resp = await client.post("/api/v1/workflows", json={
        "document_id": doc_id,
        "total_steps": 2,
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["document_id"] == doc_id
    assert data["status"] == "pending_review"
    assert data["current_step"] == 1
    assert data["total_steps"] == 2


async def test_create_workflow_document_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/workflows", json={
        "document_id": "00000000-0000-0000-0000-000000000000",
    }, headers=auth_headers)
    assert resp.status_code == 404


async def test_create_workflow_duplicate_active(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    assert resp.status_code == 409


async def test_create_workflow_unauthenticated(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    resp = await client.post("/api/v1/workflows", json={"document_id": doc_id})
    assert resp.status_code == 403


async def test_list_workflows_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/workflows", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["workflows"] == []
    assert resp.json()["total"] == 0


async def test_list_workflows_after_create(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    resp = await client.get("/api/v1/workflows", headers=auth_headers)
    assert resp.json()["total"] == 1


async def test_list_workflows_filter_by_status(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)

    resp = await client.get("/api/v1/workflows", params={"status": "pending_review"}, headers=auth_headers)
    assert resp.json()["total"] == 1

    resp = await client.get("/api/v1/workflows", params={"status": "approved"}, headers=auth_headers)
    assert resp.json()["total"] == 0


async def test_get_workflow(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/workflows/{wf_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == wf_id


async def test_get_workflow_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/workflows/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


# ─── State Transitions ───────────────────────────────────────────────────────

async def test_advance_to_in_review(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "advance",
        "comment": "Iniciando revisão.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"
    assert len(resp.json()["comments"]) == 1
    assert resp.json()["comments"][0]["action"] == "advance"


async def test_approve_workflow(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    # pending_review → in_review
    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "advance"}, headers=auth_headers)
    # in_review → approved
    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "approve",
        "comment": "Documento aprovado.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["completed_at"] is not None


async def test_reject_workflow(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "advance"}, headers=auth_headers)
    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "reject",
        "comment": "Documento com problemas.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    assert resp.json()["completed_at"] is not None


async def test_request_revision(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "advance"}, headers=auth_headers)
    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "request_revision",
        "comment": "Precisa de ajustes.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "revision_requested"
    assert resp.json()["completed_at"] is None  # not terminal


async def test_revision_then_readvance(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "advance"}, headers=auth_headers)
    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "request_revision"}, headers=auth_headers)

    # revision_requested → in_review
    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "advance",
        "comment": "Corrigido, reenviando.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"


async def test_invalid_transition(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    # Can't approve from pending_review
    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "approve",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "não permitida" in resp.json()["detail"]


async def test_transition_on_terminal_workflow(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]

    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "advance"}, headers=auth_headers)
    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "approve"}, headers=auth_headers)

    # Already approved — can't transition again
    resp = await client.post(f"/api/v1/workflows/{wf_id}/transition", json={
        "action": "advance",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "finalizado" in resp.json()["detail"]


async def test_can_create_new_workflow_after_terminal(client: AsyncClient, auth_headers: dict):
    """After a workflow is approved/rejected, a new one can be created for the same doc."""
    doc_id = await _upload_doc(client, auth_headers)

    create_resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    wf_id = create_resp.json()["id"]
    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "advance"}, headers=auth_headers)
    await client.post(f"/api/v1/workflows/{wf_id}/transition", json={"action": "reject"}, headers=auth_headers)

    # Now create a new workflow
    resp = await client.post("/api/v1/workflows", json={"document_id": doc_id}, headers=auth_headers)
    assert resp.status_code == 201
