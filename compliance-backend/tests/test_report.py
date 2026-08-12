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
    assert "Relatório de conformidade contratual" in html
    assert "Resumo" in html


def test_generate_html_no_alerts():
    """HTML report handles zero alerts gracefully."""
    analysis = {"risk_score": 10, "summary": "OK", "alerts": [], "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analysis, SAMPLE_RULES)

    assert "Nenhum apontamento" in html
    assert "Nenhuma cláusula esperada" in html


@weasyprint_required
def test_generate_pdf_report():
    """PDF report generates valid bytes."""
    html = generate_html_report(SAMPLE_DOC, SAMPLE_ANALYSIS, SAMPLE_RULES)
    pdf = generate_pdf_report(html)

    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000  # should be a real PDF
    assert pdf[:5] == b"%PDF-"  # PDF magic bytes


# ─── O que o PDF precisa carregar da verificação ────────────────────────────
# O PDF é o que sai do sistema e sobrevive ao caso. Se ele mostrar menos do que a
# tela, o trabalho de conferência some justamente no artefato que fica.

ALERTA_VERIFICADO = {
    "rule_name": "Locação: garantias cumuladas",
    "severity": "high",
    "excerpt": "caução, fiança e seguro-fiança cumulativamente",
    "issue": "Vedada a cumulação de garantias.",
    "suggestion": "Manter apenas uma modalidade.",
    "legal_basis": "Art. 37, parágrafo único, Lei 8.245/1991",
    "excerpt_check": "exact",
    "excerpt_page": 2,
    "legal_basis_check": "grounded",
    "legal_source": {
        "source": "Lei 8.245/1991",
        "article_ref": "Art. 37",
        "content": "É vedado, sob pena de nulidade, mais de uma das modalidades de garantia.",
    },
}


def test_relatorio_traz_os_selos_de_verificacao():
    analise = {"risk_score": 60, "summary": "s", "alerts": [ALERTA_VERIFICADO],
               "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES)

    assert "Trecho conferido, pág. 2" in html
    assert "Artigo conferido na base" in html
    assert "Verificação automática" in html


def test_relatorio_assinala_o_que_nao_foi_conferido():
    """Alerta não conferido precisa aparecer marcado, e não sumir nem passar limpo."""
    alerta = {**ALERTA_VERIFICADO, "excerpt_check": "not_found", "excerpt_page": None,
              "legal_basis_check": "ungrounded", "legal_source": None}
    analise = {"risk_score": 60, "summary": "s", "alerts": [alerta], "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES)

    assert "Trecho não localizado" in html
    assert "Citação sem respaldo na base" in html
    # O alerta continua no relatório: a verificação anota, não censura.
    assert "Locação: garantias cumuladas" in html


def test_relatorio_traz_o_texto_da_lei():
    analise = {"risk_score": 60, "summary": "s", "alerts": [ALERTA_VERIFICADO],
               "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES)

    assert "mais de uma das modalidades de garantia" in html
    assert "Art. 37" in html


def test_relatorio_traz_a_marcacao_do_revisor():
    alerta = {**ALERTA_VERIFICADO, "resolution": "to_fix",
              "resolution_comment": "Negociar antes de assinar"}
    analise = {"risk_score": 60, "summary": "s", "alerts": [alerta], "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES)

    assert "A corrigir" in html
    assert "Negociar antes de assinar" in html


def test_relatorio_lista_as_regras_conformes():
    """Sem esta lista o relatório não distingue "está correto" de "não foi olhado"."""
    analise = {"risk_score": 20, "summary": "s", "alerts": [], "missing_clauses": []}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES)

    assert "Regras verificadas" in html
    assert "3 de 3 regras não geraram apontamento" in html
    for regra in SAMPLE_RULES:
        assert regra["name"] in html


def test_conteudo_do_contrato_nao_quebra_o_html():
    """O trecho citado é copiado do contrato, que pode conter < e &.

    Antes isso saía cru no HTML e destruía a página inteira do relatório.
    """
    alerta = {
        "rule_name": "Regra <script>",
        "severity": "high",
        "excerpt": 'cláusula 5 <b>abusiva</b> & correlatas',
        "issue": "Problema com & e <tags>",
        "suggestion": "Ajustar <cláusula>",
        "legal_basis": None,
        "excerpt_check": "exact",
    }
    analise = {"risk_score": 50, "summary": "Resumo com <b>tag</b> & símbolo",
               "alerts": [alerta], "missing_clauses": ["Cláusula <X>"]}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES)

    assert "<script>" not in html
    assert "&lt;b&gt;abusiva&lt;/b&gt;" in html
    assert "&amp; correlatas" in html


def test_relatorio_registra_modelo_e_versao_do_prompt():
    """Rastreabilidade: qual redação produziu um relatório emitido meses atrás."""
    analise = {"risk_score": 20, "summary": "s", "alerts": [], "missing_clauses": [],
               "model": "claude-sonnet-5", "prompt_version": "2"}
    html = generate_html_report(SAMPLE_DOC, analise, SAMPLE_RULES,
                                generated_by="Ana Souza")

    assert "claude-sonnet-5" in html
    assert "prompt v2" in html
    assert "Ana Souza" in html


def test_relatorio_avisa_que_nao_e_parecer():
    html = generate_html_report(SAMPLE_DOC, SAMPLE_ANALYSIS, SAMPLE_RULES)
    assert "não constitui" in html
    assert "parecer" in html
