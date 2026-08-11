"""
Integration tests for the Dashboard & Analytics API (FASE 4).

Tests cover overview metrics, alert aggregation, feedback CRUD,
and permission checks.
"""
import sys
import uuid
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
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

_TEST_DB_URL = "sqlite+aiosqlite:///./test.db"
_engine = create_async_engine(_TEST_DB_URL, echo=False)
_TestSession = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


# ─── Helpers ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _pdf_bytes() -> bytes:
    """A real PDF with extractable text — the upload endpoint parses the file."""
    from weasyprint import HTML

    return HTML(string="<p>Contrato de teste para metricas do dashboard.</p>").write_pdf()


async def _upload_doc(client: AsyncClient, headers: dict, filename: str = "doc.pdf") -> str:
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, _pdf_bytes(), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["document_id"]


async def _inject_analysis(doc_id: str, risk_score: int = 50, alerts: list | None = None):
    """Inject an analysis directly into the DB for testing dashboard metrics."""
    from app import Document, Analysis
    from datetime import datetime, timezone

    async with _TestSession() as db:
        doc_uuid = uuid.UUID(doc_id) if isinstance(doc_id, str) else doc_id

        doc_result = await db.execute(select(Document).where(Document.id == doc_uuid))
        doc = doc_result.scalar_one()
        doc.status = "analyzed"

        analysis = Analysis(
            document_id=doc.id,
            risk_score=risk_score,
            summary=f"Test analysis score={risk_score}",
            alerts=alerts or [],
            missing_clauses=[],
            prompt_tokens=100,
            completion_tokens=50,
        )
        db.add(analysis)
        await db.commit()

        # Return analysis ID
        await db.refresh(analysis)
        return str(analysis.id)


# ─── Dashboard Overview ──────────────────────────────────────────────────────

async def test_dashboard_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["overview"]["total_documents"] == 0
    assert data["overview"]["total_analyzed"] == 0
    assert data["overview"]["avg_risk_score"] is None
    assert data["top_alerts"] == []
    assert data["risk_trend"] == []


async def test_dashboard_with_documents(client: AsyncClient, auth_headers: dict):
    # Upload 3 docs, analyze 2
    doc1 = await _upload_doc(client, auth_headers, "contract1.pdf")
    doc2 = await _upload_doc(client, auth_headers, "contract2.pdf")
    doc3 = await _upload_doc(client, auth_headers, "contract3.pdf")

    await _inject_analysis(doc1, risk_score=25, alerts=[
        {"rule_name": "LGPD", "severity": "high", "issue": "Sem consentimento"},
    ])
    await _inject_analysis(doc2, risk_score=75, alerts=[
        {"rule_name": "LGPD", "severity": "high", "issue": "Dados expostos"},
        {"rule_name": "Foro", "severity": "medium", "issue": "Foro errado"},
    ])

    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["overview"]["total_documents"] == 3
    assert data["overview"]["total_analyzed"] == 2
    assert data["overview"]["total_pending"] == 1
    assert data["overview"]["avg_risk_score"] == 50.0  # (25+75)/2
    assert data["overview"]["high_risk_count"] == 1  # 75 >= 61
    assert data["overview"]["low_risk_count"] == 1  # 25 <= 30


async def test_dashboard_top_alerts(client: AsyncClient, auth_headers: dict):
    doc1 = await _upload_doc(client, auth_headers, "a.pdf")
    doc2 = await _upload_doc(client, auth_headers, "b.pdf")

    await _inject_analysis(doc1, risk_score=60, alerts=[
        {"rule_name": "LGPD", "severity": "high", "issue": "A"},
        {"rule_name": "Foro", "severity": "medium", "issue": "B"},
    ])
    await _inject_analysis(doc2, risk_score=40, alerts=[
        {"rule_name": "LGPD", "severity": "high", "issue": "C"},
    ])

    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    data = resp.json()

    assert len(data["top_alerts"]) == 2
    # LGPD should be first (count=2)
    assert data["top_alerts"][0]["rule_name"] == "LGPD"
    assert data["top_alerts"][0]["count"] == 2
    # Foro should be second (count=1)
    assert data["top_alerts"][1]["rule_name"] == "Foro"
    assert data["top_alerts"][1]["count"] == 1


async def test_dashboard_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/dashboard")
    assert resp.status_code == 403


# ─── Feedback ─────────────────────────────────────────────────────────────────

async def test_submit_feedback(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    analysis_id = await _inject_analysis(doc_id, risk_score=65)

    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id,
        "rating": 4,
        "adjusted_score": 55,
        "comment": "Score parece um pouco alto.",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["rating"] == 4
    assert data["adjusted_score"] == 55


async def test_submit_feedback_duplicate(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    analysis_id = await _inject_analysis(doc_id, risk_score=50)

    await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id, "rating": 3,
    }, headers=auth_headers)

    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id, "rating": 5,
    }, headers=auth_headers)
    assert resp.status_code == 409


async def test_submit_feedback_analysis_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": "00000000-0000-0000-0000-000000000000",
        "rating": 3,
    }, headers=auth_headers)
    assert resp.status_code == 404


async def test_submit_feedback_invalid_rating(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    analysis_id = await _inject_analysis(doc_id, risk_score=50)

    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id, "rating": 0,  # invalid: min is 1
    }, headers=auth_headers)
    assert resp.status_code == 422

    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id, "rating": 6,  # invalid: max is 5
    }, headers=auth_headers)
    assert resp.status_code == 422


async def test_submit_feedback_invalid_adjusted_score(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    analysis_id = await _inject_analysis(doc_id, risk_score=50)

    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id, "rating": 3, "adjusted_score": 150,
    }, headers=auth_headers)
    assert resp.status_code == 422


async def test_list_feedback(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    analysis_id = await _inject_analysis(doc_id, risk_score=50)

    await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": analysis_id, "rating": 4, "comment": "Bom",
    }, headers=auth_headers)

    resp = await client.get(f"/api/v1/dashboard/feedback/{analysis_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["rating"] == 4


async def test_list_feedback_empty(client: AsyncClient, auth_headers: dict):
    doc_id = await _upload_doc(client, auth_headers)
    analysis_id = await _inject_analysis(doc_id, risk_score=50)

    resp = await client.get(f"/api/v1/dashboard/feedback/{analysis_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_feedback_unauthenticated(client: AsyncClient):
    resp = await client.post("/api/v1/dashboard/feedback", json={
        "analysis_id": "00000000-0000-0000-0000-000000000000", "rating": 3,
    })
    assert resp.status_code == 403
