"""Tests for HTML/PDF report generation."""
import pytest
from app.services.report_generator import generate_html_report, generate_pdf_report

try:
    from weasyprint import HTML as _  # noqa: F401
    _WEASYPRINT_OK = True
except OSError:
    _WEASYPRINT_OK = False

weasyprint_required = pytest.mark.skipif(
    not _WEASYPRINT_OK,
    reason="WeasyPrint GTK libraries not installed — skipping PDF generation test",
)


SAMPLE_DOC = {"filename": "contrato_teste.pdf"}
SAMPLE_ANALYSIS = {
    "risk_score": 72,
    "summary": "Contrato com riscos moderados. Foro fora de PE e LGPD ausente.",
    "alerts": [
        {
            "rule_name": "Foro em Pernambuco",
            "severity": "high",
            "excerpt": "foro de São Paulo/SP",
            "issue": "Foro definido fora de PE",
            "suggestion": "Alterar para Recife/PE",
        },
        {
            "rule_name": "Cláusula LGPD",
            "severity": "high",
            "excerpt": "—",
            "issue": "Sem menção à LGPD",
            "suggestion": "Incluir cláusula LGPD",
        },
    ],
    "missing_clauses": ["Cláusula LGPD"],
}
SAMPLE_RULES = [
    {"name": "Foro em Pernambuco", "severity": "high"},
    {"name": "Cláusula LGPD", "severity": "high"},
    {"name": "Confidencialidade", "severity": "high"},
]


def test_generate_html_report():
    """HTML report contains all expected sections."""
    html = generate_html_report(SAMPLE_DOC, SAMPLE_ANALYSIS, SAMPLE_RULES)

    assert "contrato_teste.pdf" in html
    assert "72" in html
    assert "Foro em Pernambuco" in html
    assert "Cláusula LGPD" in html
    assert "Confidencialidade" in html
    assert "Relatório de Compliance" in html
    assert "Resumo Executivo" in html


def test_generate_html_no_alerts():
    """HTML report handles zero alerts gracefully."""
    analysis = {"risk_score": 10, "summary": "OK", "alerts": [], "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analysis, SAMPLE_RULES)

    assert "documento em conformidade" in html.lower()


@weasyprint_required
def test_generate_pdf_report():
    """PDF report generates valid bytes."""
    html = generate_html_report(SAMPLE_DOC, SAMPLE_ANALYSIS, SAMPLE_RULES)
    pdf = generate_pdf_report(html)

    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000  # should be a real PDF
    assert pdf[:5] == b"%PDF-"  # PDF magic bytes
