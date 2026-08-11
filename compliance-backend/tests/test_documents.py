"""
Integration tests for document endpoints.

Covers: upload, list, get, status polling, delete,
and report (JSON / HTML / PDF) endpoints.

Celery tasks are mocked via sys.modules to prevent
Redis/worker connections during tests.
"""
import sys
import uuid
from functools import lru_cache
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# ─── Mock Celery worker module before any test triggers its import ────────────
# The tasks module creates a Celery instance and a sync SQLAlchemy engine on
# import, which would fail without running Redis/Postgres. Replacing it with a
# MagicMock lets the API's lazy `from app.workers.tasks import ...` calls
# resolve cleanly in-process.
_fake_task_result = MagicMock()
_fake_task_result.id = "fake-celery-task-id"

_mock_tasks = MagicMock()
_mock_tasks.analyze_document_task.delay.return_value = _fake_task_result
_mock_tasks.celery_app.AsyncResult.return_value.state = "PENDING"

sys.modules["app.workers.tasks"] = _mock_tasks

from app import Document, Analysis  # noqa: E402  (after sys.modules patch)

# ─── WeasyPrint availability check ───────────────────────────────────────────
# WeasyPrint requires GTK native libraries that may be absent on Windows.
# Tests that actually generate PDFs are skipped gracefully when unavailable.
try:
    from weasyprint import HTML as _  # noqa: F401
    _WEASYPRINT_OK = True
except OSError:
    _WEASYPRINT_OK = False

weasyprint_required = pytest.mark.skipif(
    not _WEASYPRINT_OK,
    reason="WeasyPrint GTK libraries not installed — skipping PDF generation test",
)

# Mirror the same SQLite URL used in conftest so we can inject rows directly.
_TEST_DB_URL = "sqlite+aiosqlite:///./test.db"
_engine = create_async_engine(_TEST_DB_URL, echo=False)
_TestSession = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)


# ─── Helpers ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _pdf_bytes() -> bytes:
    """A real PDF carrying extractable text.

    The upload endpoint extracts the document text before persisting it, so the
    fixture has to be a file the extractor can actually parse — a byte string
    that merely looks like a PDF is rejected with a 400.
    """
    from weasyprint import HTML

    return HTML(
        string="<p>Contrato de teste. Cláusula de foro: comarca de Recife.</p>"
    ).write_pdf()


@lru_cache(maxsize=1)
def _docx_bytes() -> bytes:
    """A real DOCX carrying extractable text (see `_pdf_bytes`)."""
    import io

    from docx import Document as DocxDocument

    docx = DocxDocument()
    docx.add_paragraph("Contrato de teste. Cláusula de foro: comarca de Recife.")
    buffer = io.BytesIO()
    docx.save(buffer)
    return buffer.getvalue()


def _upload(client, headers, filename="doc.pdf", content=None, mime=None):
    """Convenience wrapper for the upload endpoint."""
    # NOTE: use `is None` — empty bytes b"" is falsy, so `or` would silently
    # replace it with valid PDF content, breaking the empty-file test.
    content = _pdf_bytes() if content is None else content
    mime = mime or "application/pdf"
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, content, mime)},
        headers=headers,
    )


# ─── Upload ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_pdf_success(client: AsyncClient, auth_headers: dict):
    """Authenticated user can upload a PDF and receives a task ID."""
    resp = await _upload(client, auth_headers, "contrato.pdf")

    assert resp.status_code == 201
    data = resp.json()
    assert "document_id" in data
    assert data["status"] == "uploaded"
    assert data["task_id"] == "fake-celery-task-id"
    assert "contrato.pdf" in data["message"]


@pytest.mark.asyncio
async def test_upload_docx_success(client: AsyncClient, auth_headers: dict):
    """Authenticated user can upload a DOCX file."""
    resp = await _upload(
        client, auth_headers,
        filename="acordo.docx",
        content=_docx_bytes(),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_invalid_format_rejected(client: AsyncClient, auth_headers: dict):
    """Unsupported file formats are rejected with HTTP 400."""
    resp = await _upload(
        client, auth_headers,
        filename="malware.exe",
        content=b"MZ\x90\x00" + b"\x00" * 64,
        mime="application/octet-stream",
    )

    assert resp.status_code == 400
    assert "Formato não suportado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file_rejected(client: AsyncClient, auth_headers: dict):
    """Empty files are rejected with HTTP 400."""
    resp = await _upload(client, auth_headers, filename="vazio.pdf", content=b"")

    assert resp.status_code == 400
    assert "vazio" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_unauthenticated(client: AsyncClient):
    """Unauthenticated upload requests are rejected with HTTP 401."""
    resp = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("contrato.pdf", _pdf_bytes(), "application/pdf")},
    )

    # FastAPI's HTTPBearer returns 403 (not 401) when the Authorization
    # header is missing entirely. This is correct RFC 9110 behaviour for
    # bearer token schemes that don't issue a WWW-Authenticate challenge.
    assert resp.status_code == 403


# ─── List ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient, auth_headers: dict):
    """New user has an empty document list."""
    resp = await client.get("/api/v1/documents", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_documents_after_upload(client: AsyncClient, auth_headers: dict):
    """Uploaded document appears in the list with correct metadata."""
    await _upload(client, auth_headers, "lista_teste.pdf")

    resp = await client.get("/api/v1/documents", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["documents"][0]["filename"] == "lista_teste.pdf"
    assert data["documents"][0]["status"] == "uploaded"


@pytest.mark.asyncio
async def test_list_documents_search_filter(client: AsyncClient, auth_headers: dict):
    """Search filter narrows results by filename substring."""
    for name in ("alpha.pdf", "beta.pdf", "gamma.pdf"):
        await _upload(client, auth_headers, name)

    resp = await client.get("/api/v1/documents?search=beta", headers=auth_headers)

    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["filename"] == "beta.pdf"


@pytest.mark.asyncio
async def test_list_documents_pagination(client: AsyncClient, auth_headers: dict):
    """Pagination params (limit/offset) are respected."""
    for i in range(5):
        await _upload(client, auth_headers, f"doc_{i}.pdf")

    resp = await client.get("/api/v1/documents?limit=2&offset=0", headers=auth_headers)
    data = resp.json()

    assert resp.status_code == 200
    assert len(data["documents"]) == 2
    assert data["total"] == 5


@pytest.mark.asyncio
async def test_list_documents_isolation(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """Users only see their own documents; cross-user visibility is blocked."""
    await _upload(client, auth_headers, "user_doc.pdf")
    await _upload(client, admin_headers, "admin_doc.pdf")

    resp = await client.get("/api/v1/documents", headers=auth_headers)
    docs = resp.json()["documents"]

    assert len(docs) == 1
    assert docs[0]["filename"] == "user_doc.pdf"


# ─── Get Single Document ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_document_success(client: AsyncClient, auth_headers: dict):
    """Authenticated owner can retrieve a specific document by ID."""
    upload = await _upload(client, auth_headers, "detalhe.pdf")
    doc_id = upload.json()["document_id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == doc_id
    assert data["filename"] == "detalhe.pdf"


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient, auth_headers: dict):
    """Non-existent document ID returns HTTP 404."""
    fake_id = str(uuid.uuid4())

    resp = await client.get(f"/api/v1/documents/{fake_id}", headers=auth_headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_document_wrong_user_returns_404(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """A user cannot view another user's document — gets 404, not 403."""
    upload = await _upload(client, admin_headers, "privado.pdf")
    doc_id = upload.json()["document_id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}", headers=auth_headers)

    assert resp.status_code == 404


# ─── Status Polling ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_after_upload_is_uploaded(client: AsyncClient, auth_headers: dict):
    """Status endpoint returns 'uploaded' immediately after upload."""
    upload = await _upload(client, auth_headers, "status_test.pdf")
    doc_id = upload.json()["document_id"]
    task_id = upload.json()["task_id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/status?task_id={task_id}",
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "uploaded"
    assert data["document_id"] == doc_id


@pytest.mark.asyncio
async def test_status_not_found(client: AsyncClient, auth_headers: dict):
    """Status polling for unknown document returns 404."""
    fake_id = str(uuid.uuid4())

    resp = await client.get(f"/api/v1/documents/{fake_id}/status", headers=auth_headers)

    assert resp.status_code == 404


# ─── Helpers to inject a completed Analysis ──────────────────────────────────

async def _upload_and_inject_analysis(
    client, headers, filename, risk_score=65, alerts=None, missing=None
):
    """Upload a doc then inject an Analysis row directly into the test DB."""
    upload = await _upload(client, headers, filename)
    doc_id = upload.json()["document_id"]

    alerts = alerts or [
        {
            "rule_name": "Foro em Pernambuco",
            "severity": "high",
            "excerpt": "São Paulo/SP",
            "issue": "Foro definido fora de PE",
            "suggestion": "Alterar para Recife/PE",
        }
    ]
    missing = missing or ["Cláusula LGPD"]

    async with _TestSession() as db:
        # SQLAlchemy's UUID(as_uuid=True) requires a uuid.UUID object, not a
        # plain string.  The API returns the id as a str in JSON, so convert.
        doc_id_uuid = uuid.UUID(doc_id) if isinstance(doc_id, str) else doc_id
        doc_result = await db.execute(select(Document).where(Document.id == doc_id_uuid))
        doc = doc_result.scalar_one()
        doc.status = "analyzed"
        analysis = Analysis(
            document_id=doc.id,
            risk_score=risk_score,
            summary="Resumo gerado por IA.",
            alerts=alerts,
            missing_clauses=missing,
        )
        db.add(analysis)
        await db.commit()

    return doc_id


# ─── Report (JSON) ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_report_not_analyzed_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """Report endpoint returns 404 when analysis is not yet available."""
    upload = await _upload(client, auth_headers, "sem_analise.pdf")
    doc_id = upload.json()["document_id"]

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    assert resp.status_code == 404
    assert "não disponível" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_report_with_analysis(
    client: AsyncClient, auth_headers: dict, setup_db
):
    """Report endpoint returns full report when analysis is ready."""
    doc_id = await _upload_and_inject_analysis(
        client, auth_headers, "com_analise.pdf", risk_score=72
    )

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["analysis"]["risk_score"] == 72
    assert data["analysis"]["summary"] == "Resumo gerado por IA."
    assert len(data["analysis"]["alerts"]) == 1
    assert data["analysis"]["alerts"][0]["rule_name"] == "Foro em Pernambuco"
    assert data["document"]["id"] == doc_id
    assert isinstance(data["rules_checked"], list)


@pytest.mark.asyncio
async def test_get_report_wrong_user_returns_404(
    client: AsyncClient, auth_headers: dict, admin_headers: dict, setup_db
):
    """A user cannot retrieve another user's report."""
    doc_id = await _upload_and_inject_analysis(client, admin_headers, "admin_report.pdf")

    resp = await client.get(f"/api/v1/documents/{doc_id}/report", headers=auth_headers)

    assert resp.status_code == 404


# ─── Report HTML ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_report_html_success(
    client: AsyncClient, auth_headers: dict, setup_db
):
    """HTML report endpoint returns valid HTML containing report content."""
    doc_id = await _upload_and_inject_analysis(
        client, auth_headers, "html_report.pdf", risk_score=40,
        alerts=[], missing=[],
    )

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/report/html", headers=auth_headers
    )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "html_report.pdf" in resp.text
    assert "Relatório de Compliance" in resp.text
    assert "Resumo Executivo" in resp.text


@pytest.mark.asyncio
async def test_download_report_html_not_analyzed_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """HTML report returns 404 when no analysis exists."""
    upload = await _upload(client, auth_headers, "sem_html.pdf")
    doc_id = upload.json()["document_id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/report/html", headers=auth_headers
    )

    assert resp.status_code == 404


# ─── Report PDF ───────────────────────────────────────────────────────────────

@weasyprint_required
@pytest.mark.asyncio
async def test_download_report_pdf_success(
    client: AsyncClient, auth_headers: dict, setup_db
):
    """PDF report endpoint returns a valid PDF binary with correct headers."""
    doc_id = await _upload_and_inject_analysis(
        client, auth_headers, "relatorio_final.pdf", risk_score=80
    )

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/report/pdf", headers=auth_headers
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
    assert "attachment" in resp.headers["content-disposition"]
    assert len(resp.content) > 1_000  # real PDF, not empty


@pytest.mark.asyncio
async def test_download_report_pdf_not_analyzed_returns_404(
    client: AsyncClient, auth_headers: dict
):
    """PDF report returns 404 when document has no analysis."""
    upload = await _upload(client, auth_headers, "sem_pdf.pdf")
    doc_id = upload.json()["document_id"]

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/report/pdf", headers=auth_headers
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_report_pdf_wrong_user_returns_404(
    client: AsyncClient, auth_headers: dict, admin_headers: dict, setup_db
):
    """A user cannot download another user's PDF report."""
    doc_id = await _upload_and_inject_analysis(client, admin_headers, "admin_pdf.pdf")

    resp = await client.get(
        f"/api/v1/documents/{doc_id}/report/pdf", headers=auth_headers
    )

    assert resp.status_code == 404


# ─── Delete ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_document_success(client: AsyncClient, auth_headers: dict):
    """Deleted document returns 204 and disappears from list and get."""
    upload = await _upload(client, auth_headers, "deletar.pdf")
    doc_id = upload.json()["document_id"]

    del_resp = await client.delete(
        f"/api/v1/documents/{doc_id}", headers=auth_headers
    )
    assert del_resp.status_code == 204

    # Confirm it's gone from get
    get_resp = await client.get(
        f"/api/v1/documents/{doc_id}", headers=auth_headers
    )
    assert get_resp.status_code == 404

    # Confirm it's gone from list
    list_resp = await client.get("/api/v1/documents", headers=auth_headers)
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_delete_document_not_found(client: AsyncClient, auth_headers: dict):
    """Deleting a non-existent document returns 404."""
    resp = await client.delete(
        f"/api/v1/documents/{uuid.uuid4()}", headers=auth_headers
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_wrong_user_returns_404(
    client: AsyncClient, auth_headers: dict, admin_headers: dict
):
    """A user cannot delete another user's document."""
    upload = await _upload(client, admin_headers, "protegido.pdf")
    doc_id = upload.json()["document_id"]

    resp = await client.delete(
        f"/api/v1/documents/{doc_id}", headers=auth_headers
    )

    assert resp.status_code == 404
    # Admin's document should still exist
    admin_resp = await client.get(
        f"/api/v1/documents/{doc_id}", headers=admin_headers
    )
    assert admin_resp.status_code == 200
