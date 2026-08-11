"""Testes da verificação de alertas contra as fontes."""
import pytest

from app.services.verification import (
    annotate_alerts,
    verification_summary,
    verify_excerpt,
    verify_legal_basis,
)

CONTRATO = """--- Página 1 ---
CLÁUSULA TERCEIRA - DO PAGAMENTO
O pagamento de cada fatura será realizado em 90 (noventa) dias corridos
contados do aceite formal da entrega pela CONTRATANTE.

--- Página 2 ---
CLÁUSULA NONA - DO FORO
Fica eleito o foro da Comarca de Manaus, Estado do Amazonas.
"""


# ─── Trecho do documento ──────────────────────────────────────────────────────

def test_excerpt_exato_e_reconhecido():
    assert verify_excerpt(
        "O pagamento de cada fatura será realizado em 90 (noventa) dias corridos",
        CONTRATO,
    ) == "exact"


def test_excerpt_ignora_quebra_de_linha_e_espacos():
    """O modelo costuma devolver o trecho em uma linha só."""
    assert verify_excerpt(
        "O pagamento de cada fatura será realizado em 90 (noventa) dias corridos contados do aceite formal",
        CONTRATO,
    ) == "exact"


def test_excerpt_ignora_aspas_e_acentuacao():
    assert verify_excerpt(
        '"Fica eleito o foro da Comarca de Manaus, Estado do Amazonas."',
        CONTRATO,
    ) == "exact"


def test_excerpt_parafraseado_e_aproximado():
    """Reescrita próxima conta como aproximada, não como invenção."""
    resultado = verify_excerpt(
        "O pagamento de cada fatura sera realizado em 90 (noventa) dias corridos contados do aceite",
        CONTRATO,
    )
    assert resultado in {"exact", "approximate"}


def test_excerpt_inventado_e_sinalizado():
    assert verify_excerpt(
        "A CONTRATADA garante disponibilidade de 99,9% e responde por danos indiretos",
        CONTRATO,
    ) == "not_found"


def test_excerpt_ausente_para_clausula_inexistente():
    """O prompt manda usar travessão quando a cláusula não existe no contrato."""
    for vazio in ["—", "-", "", None, "N/A"]:
        assert verify_excerpt(vazio, CONTRATO) == "empty"


def test_excerpt_curto_nao_vira_aproximado_por_acaso():
    assert verify_excerpt("dias corridos xyz", CONTRATO) == "not_found"


# ─── Base legal ───────────────────────────────────────────────────────────────

CONTEXTO = [
    {"source": "Lei 13.709/2018", "article_ref": "Art. 7º", "content": "..."},
    {"source": "Lei 13.709/2018", "article_ref": "Art. 18", "content": "..."},
]


def test_artigo_recuperado_e_fundamentado():
    assert verify_legal_basis("Art. 7º, Lei 13.709/2018 (LGPD)", CONTEXTO) == "grounded"


def test_artigo_sem_ordinal_tambem_confere():
    assert verify_legal_basis("Art. 18 da LGPD", CONTEXTO) == "grounded"


def test_lei_certa_artigo_nao_recuperado():
    """A lei bate, mas o artigo não veio na busca: vale conferir na fonte."""
    assert verify_legal_basis("Art. 46, LGPD", CONTEXTO) == "law_only"


def test_citacao_sem_respaldo_no_contexto():
    assert verify_legal_basis("Art. 51, CDC", CONTEXTO) == "ungrounded"


def test_sem_base_legal_citada():
    assert verify_legal_basis(None, CONTEXTO) == "empty"
    assert verify_legal_basis("   ", CONTEXTO) == "empty"


def test_analise_sem_contexto_legal():
    """Quando o RAG não retorna nada, não há como verificar."""
    assert verify_legal_basis("Art. 7º, LGPD", []) == "no_context"


# ─── Anotação em lote ─────────────────────────────────────────────────────────

def test_annotate_preserva_campos_e_adiciona_checagens():
    alertas = [
        {
            "rule_name": "Prazo de Pagamento",
            "severity": "medium",
            "excerpt": "O pagamento de cada fatura será realizado em 90 (noventa) dias corridos",
            "issue": "Prazo excede 60 dias",
            "suggestion": "Reduzir para 60 dias",
            "legal_basis": "Art. 7º, LGPD",
        }
    ]
    resultado = annotate_alerts(alertas, CONTRATO, CONTEXTO)

    assert len(resultado) == 1
    alerta = resultado[0]
    assert alerta["rule_name"] == "Prazo de Pagamento"
    assert alerta["issue"] == "Prazo excede 60 dias"
    assert alerta["excerpt_check"] == "exact"
    assert alerta["legal_basis_check"] == "grounded"


def test_summary_conta_por_categoria():
    alertas = [
        {"excerpt_check": "exact", "legal_basis_check": "grounded"},
        {"excerpt_check": "not_found", "legal_basis_check": "ungrounded"},
        {"excerpt_check": "empty", "legal_basis_check": "empty"},
    ]
    s = verification_summary(alertas)
    assert s["total"] == 3
    assert s["excerpt_exact"] == 1
    assert s["excerpt_unverified"] == 1
    assert s["legal_grounded"] == 1
    assert s["legal_ungrounded"] == 1
