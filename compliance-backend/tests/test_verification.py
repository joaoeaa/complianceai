"""Testes da verificação de alertas contra as fontes."""
import pytest

from app.services.verification import (
    annotate_alerts,
    find_legal_source,
    locate_excerpt,
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


# ─── Texto da lei anexado ao alerta ───────────────────────────────────────────

CONTEXTO_COM_TEXTO = [
    {
        "source": "Lei 13.709/2018",
        "article_ref": "Art. 7º",
        "content": "O tratamento de dados pessoais somente podera ser realizado nas seguintes hipoteses: I - mediante o fornecimento de consentimento pelo titular;",
    },
]


def test_dispositivo_citado_vem_com_o_texto_da_lei():
    fonte = find_legal_source("Art. 7º, LGPD", CONTEXTO_COM_TEXTO)
    assert fonte is not None
    assert fonte["article_ref"] == "Art. 7º"
    assert fonte["source"] == "Lei 13.709/2018"
    assert "consentimento pelo titular" in fonte["content"]


def test_artigo_fora_do_contexto_nao_traz_texto():
    assert find_legal_source("Art. 99, LGPD", CONTEXTO_COM_TEXTO) is None


def test_alerta_sem_base_legal_nao_traz_texto():
    assert find_legal_source(None, CONTEXTO_COM_TEXTO) is None


def test_annotate_anexa_o_dispositivo():
    alertas = [{"rule_name": "LGPD", "excerpt": "—", "legal_basis": "Art. 7º da LGPD"}]
    resultado = annotate_alerts(alertas, CONTRATO, CONTEXTO_COM_TEXTO)[0]
    assert resultado["legal_source"]["article_ref"] == "Art. 7º"
    assert resultado["legal_basis_check"] == "grounded"


# ─── Localizacao por pagina ───────────────────────────────────────────────────

def test_localiza_trecho_na_primeira_pagina():
    status, pagina = locate_excerpt(
        "O pagamento de cada fatura será realizado em 90 (noventa) dias corridos",
        CONTRATO,
    )
    assert status == "exact"
    assert pagina == 1


def test_localiza_trecho_na_segunda_pagina():
    status, pagina = locate_excerpt(
        "Fica eleito o foro da Comarca de Manaus, Estado do Amazonas",
        CONTRATO,
    )
    assert status == "exact"
    assert pagina == 2


def test_trecho_nao_encontrado_nao_tem_pagina():
    status, pagina = locate_excerpt("clausula inexistente sobre SLA de 99,99%", CONTRATO)
    assert status == "not_found"
    assert pagina is None


def test_clausula_ausente_nao_tem_pagina():
    status, pagina = locate_excerpt("—", CONTRATO)
    assert status == "empty"
    assert pagina is None


def test_documento_sem_marcador_de_pagina():
    """DOCX nao tem paginacao no texto extraido; o alerta fica sem pagina."""
    texto = "Contrato simples com clausula de foro em Recife e prazo de 30 dias."
    status, pagina = locate_excerpt("clausula de foro em Recife", texto)
    assert status == "exact"
    assert pagina is None


def test_annotate_inclui_a_pagina():
    alertas = [{
        "rule_name": "Foro competente",
        "excerpt": "Fica eleito o foro da Comarca de Manaus, Estado do Amazonas",
        "legal_basis": None,
    }]
    resultado = annotate_alerts(alertas, CONTRATO, [])[0]
    assert resultado["excerpt_page"] == 2


# ─── Trecho com reticencias e artigo fora do contexto ─────────────────────────

def test_excerpt_com_reticencias_junta_dois_trechos():
    """O modelo usa [...] para unir passagens distantes; ambas existem."""
    citacao = "O pagamento de cada fatura [...] Fica eleito o foro da Comarca de Manaus"
    status, pagina = locate_excerpt(citacao, CONTRATO)
    assert status == "exact"
    assert pagina == 1


def test_excerpt_com_reticencias_e_parte_inventada():
    citacao = "O pagamento de cada fatura [...] clausula inexistente sobre SLA"
    status, _ = locate_excerpt(citacao, CONTRATO)
    assert status == "not_found"


def test_artigo_fora_do_contexto_mas_presente_na_base():
    """Sem consultar a base, uma citacao correta virava 'sem respaldo'."""
    def lookup(_):
        return {"source": "Lei 10.406/2002", "article_ref": "Art. 421", "content": "texto"}

    assert verify_legal_basis("Art. 421, CC", CONTEXTO, lookup) == "in_base"


def test_contexto_tem_prioridade_sobre_a_base():
    def lookup(_):
        return {"source": "x", "article_ref": "Art. 7o", "content": "y"}

    assert verify_legal_basis("Art. 7º, LGPD", CONTEXTO, lookup) == "grounded"


def test_artigo_inexistente_segue_sem_respaldo():
    assert verify_legal_basis("Art. 9999, CC", CONTEXTO, lambda _: None) == "ungrounded"


def test_find_legal_source_recorre_a_base():
    def lookup(_):
        return {"source": "Lei 10.406/2002", "article_ref": "Art. 421", "content": "A liberdade"}

    fonte = find_legal_source("Art. 421, CC", CONTEXTO, lookup)
    assert fonte["article_ref"] == "Art. 421"


def test_citacao_apenas_da_lei_confere():
    """Alerta sobre ausencia de clausula cita a lei, nao um artigo."""
    def lookup(_):
        return {"source": "Lei 12.846/2013", "article_ref": None, "content": None}

    assert verify_legal_basis("Lei 12.846/2013", CONTEXTO, lookup) == "law_only"


def test_citacao_apenas_da_lei_nao_exibe_dispositivo():
    def lookup(_):
        return {"source": "Lei 12.846/2013", "article_ref": None, "content": None}

    assert find_legal_source("Lei 12.846/2013", CONTEXTO, lookup) is None


def test_lei_inexistente_segue_sem_respaldo():
    assert verify_legal_basis("Lei 99.999/2099", CONTEXTO, lambda _: None) == "ungrounded"


def test_modelo_nao_consegue_forjar_o_selo():
    """O selo verde nunca pode vir do modelo.

    `annotate_alerts` espalha o alerta com `**alert` e sobrescreve os campos de
    verificação depois. Inverter essa ordem num refator entregaria ao modelo o
    controle do próprio selo, e a promessa inteira do produto se apoia em ele não
    ter esse controle. Como a inversão é uma linha e não quebra nada visível,
    este teste existe para que ela não passe despercebida.
    """
    alerta_forjado = {
        "rule_name": "Regra qualquer",
        "severity": "high",
        "excerpt": "trecho que nao aparece em lugar nenhum do documento",
        "excerpt_check": "exact",          # o modelo afirmando que conferiu
        "excerpt_page": 1,
        "legal_basis": "Art. 999, Lei 99.999/2099",
        "legal_basis_check": "grounded",   # idem
        "legal_source": {"source": "inventada", "article_ref": "Art. 999",
                         "content": "texto que nao existe"},
    }

    resultado = annotate_alerts(
        [alerta_forjado], "Contrato que nao contem aquela frase.", []
    )[0]

    assert resultado["excerpt_check"] == "not_found"
    assert resultado["excerpt_page"] is None
    assert resultado["legal_basis_check"] == "no_context"
    assert resultado["legal_source"] is None
    # Os demais campos do alerta seguem intactos: a verificação anota, não censura.
    assert resultado["rule_name"] == "Regra qualquer"
    assert resultado["severity"] == "high"


def test_selo_de_artigo_nao_depende_do_que_o_modelo_afirma():
    """Mesmo citando um artigo real, o selo vem da busca, não da citação."""
    contexto = [{"source": "Lei 13.709/2018", "article_ref": "Art. 6º",
                 "content": "Finalidade específica..."}]

    forjado = {"excerpt": "-", "legal_basis": "Art. 42, LGPD",
               "legal_basis_check": "grounded"}
    assert annotate_alerts([forjado], "doc", contexto)[0]["legal_basis_check"] != "grounded"

    honesto = {"excerpt": "-", "legal_basis": "Art. 6º, I, LGPD"}
    assert annotate_alerts([honesto], "doc", contexto)[0]["legal_basis_check"] == "grounded"
