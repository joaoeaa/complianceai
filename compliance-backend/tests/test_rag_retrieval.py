"""Recuperação do RAG: uma consulta por cláusula e por regra, fundidas.

Regressão: a consulta única, feita com os primeiros 500 caracteres do contrato,
trazia a lei do cabeçalho. Num contrato com cláusula inteira de tratamento de
dados pessoais, o contexto saía com Marco Civil, CLT e CDC, e nenhum artigo da LGPD.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.services import rag_service as rag
from app.services.rag_service import (
    consultas_da_analise,
    dividir_em_clausulas,
    selecionar_trechos,
)


def _corpo(tema: str) -> str:
    return f"O contrato trata de {tema} com o detalhe necessário para virar consulta."


# ─── Divisão por cláusula ────────────────────────────────────────────────────

CONTRATO = f"""CONTRATO DE PRESTAÇÃO DE SERVIÇOS
Entre as partes ACME LTDA e BETA S.A., qualificadas abaixo, fica ajustado o seguinte.

CLÁUSULA 1ª – DO OBJETO
{_corpo("objeto")}

CLÁUSULA 2ª – DO PREÇO
{_corpo("preço")} O reajuste segue o previsto
conforme a cláusula 5ª, sem outra correção.

--- Página 2 ---
CLÁUSULA 3ª – DO TRATAMENTO DE DADOS PESSOAIS
{_corpo("dados pessoais e compartilhamento com terceiros")}
"""


def test_divide_nas_clausulas_e_mantem_o_preambulo():
    partes = dividir_em_clausulas(CONTRATO)

    assert len(partes) == 4
    assert partes[0].startswith("CONTRATO DE PRESTAÇÃO")
    assert partes[1].startswith("CLÁUSULA 1ª")
    assert partes[2].startswith("CLÁUSULA 2ª")
    assert partes[3].startswith("CLÁUSULA 3ª")
    assert "dados pessoais" in partes[3]


def test_mencao_a_clausula_no_meio_da_frase_nao_parte_o_texto():
    """'conforme a cláusula 5ª' começa linha por quebra do PDF, mas não é ordinal de título."""
    partes = dividir_em_clausulas(CONTRATO)
    preco = next(p for p in partes if p.startswith("CLÁUSULA 2ª"))
    assert "conforme a cláusula 5ª" in preco


def test_marca_de_pagina_do_extrator_nao_entra_na_consulta():
    assert not any("Página 2" in p for p in dividir_em_clausulas(CONTRATO))


@pytest.mark.parametrize("titulo", [
    "CLÁUSULA PRIMEIRA", "Cláusula Décima Segunda", "CLAUSULA 10", "CLÁUSULA IV –",
    "  Cláusula 3ª:",
])
def test_reconhece_as_formas_usuais_de_titulo(titulo):
    texto = f"{titulo} DO OBJETO\n{_corpo('a')}\n{titulo} DO PREÇO\n{_corpo('b')}"
    assert len(dividir_em_clausulas(texto)) == 2


def test_pedaco_curto_demais_nao_vira_consulta():
    texto = f"CLÁUSULA 1ª\n{_corpo('a')}\nCLÁUSULA 2ª – FORO\nRecife.\n"
    partes = dividir_em_clausulas(texto)
    assert partes == [f"CLÁUSULA 1ª\n{_corpo('a')}"]


# ─── Fallback por parágrafo ──────────────────────────────────────────────────

def test_sem_clausulas_divide_por_paragrafos_juntando_os_curtos():
    curtos = [f"Parágrafo {i}. " + "x" * 180 for i in range(8)]  # ~195 chars cada
    texto = "\n\n".join(curtos)

    grupos = dividir_em_clausulas(texto)

    # 4 parágrafos de ~195 cabem em 800; o quinto já passaria.
    assert len(grupos) == 2
    assert all(len(g) <= rag.RAG_ALVO_PARAGRAFOS for g in grupos)
    assert grupos[0].startswith("Parágrafo 0.") and "Parágrafo 3." in grupos[0]
    assert grupos[1].startswith("Parágrafo 4.")


def test_paragrafo_maior_que_o_alvo_fica_sozinho_e_inteiro():
    longo = "L" * 1500
    texto = f"{_corpo('antes')}\n\n{longo}\n\n{_corpo('depois')}"
    grupos = dividir_em_clausulas(texto)
    assert longo in grupos
    assert len(grupos) == 3


def test_texto_sem_linha_em_branco_agrupa_por_linha():
    """PDF costuma vir com uma quebra simples por linha, sem parágrafo marcado."""
    linhas = [f"Linha {i} " + "y" * 90 for i in range(20)]  # ~98 chars cada
    grupos = dividir_em_clausulas("\n".join(linhas))
    assert len(grupos) > 1
    assert all(len(g) <= rag.RAG_ALVO_PARAGRAFOS for g in grupos)
    assert "\n".join(grupos) == "\n".join(linhas)


def test_uma_clausula_so_nao_conta_como_divisao_por_clausula():
    texto = f"{_corpo('preâmbulo')}\n\nCLÁUSULA ÚNICA\n{_corpo('tudo')}"
    grupos = dividir_em_clausulas(texto)
    # Caiu no agrupamento: tudo cabe num grupo de até 800 caracteres.
    assert len(grupos) == 1


# ─── Consultas ───────────────────────────────────────────────────────────────

def test_uma_consulta_por_regra_antes_das_clausulas():
    regras = [
        {"name": "LGPD: compartilhamento", "criteria": "Verificar base legal do compartilhamento"},
        {"name": "Foro", "criteria": "Verificar o foro"},
    ]
    consultas = consultas_da_analise(CONTRATO, regras)

    assert consultas[:2] == [
        "LGPD: compartilhamento: Verificar base legal do compartilhamento",
        "Foro: Verificar o foro",
    ]
    assert len(consultas) == 2 + 4


def test_sem_regras_so_as_clausulas():
    assert consultas_da_analise(CONTRATO, []) == dividir_em_clausulas(CONTRATO)


def test_consultas_respeitam_os_limites_da_requisicao():
    clausulas = "\n".join(
        f"CLÁUSULA {i}\n{'z' * (rag.RAG_MAX_CHARS_CONSULTA + 50)}"
        for i in range(1, rag.RAG_MAX_CONSULTAS + 20)
    )
    consultas = consultas_da_analise(clausulas, [{"name": "R", "criteria": "c"}])

    assert len(consultas) == rag.RAG_MAX_CONSULTAS
    assert consultas[0] == "R: c"  # as regras ficam; o que sai são as últimas cláusulas
    assert max(len(c) for c in consultas) == rag.RAG_MAX_CHARS_CONSULTA


# ─── Seleção ─────────────────────────────────────────────────────────────────

def _t(id_, sim, fonte="Lei 13.709/2018", ref="Art. 7º"):
    return {
        "id": id_, "similarity": sim, "document_source": fonte,
        "article_ref": ref, "content": f"conteudo {id_}", "document_title": "t",
    }


def test_trecho_repetido_entra_uma_vez_com_a_maior_similaridade():
    resultados = [
        [_t("a", 0.61), _t("b", 0.60)],
        [_t("a", 0.72), _t("c", 0.50)],
        [_t("a", 0.55)],
    ]
    escolhidos = selecionar_trechos(resultados, teto=12)

    assert [t["id"] for t in escolhidos] == ["a", "b", "c"]
    assert escolhidos[0]["similarity"] == 0.72


def test_ordena_por_similaridade_e_respeita_o_teto():
    resultados = [[_t(str(i), 0.5 + i / 100, fonte=f"Lei {i}/2000")] for i in range(20)]
    escolhidos = selecionar_trechos(resultados, teto=12)

    assert len(escolhidos) == 12
    sims = [t["similarity"] for t in escolhidos]
    assert sims == sorted(sims, reverse=True)
    assert escolhidos[0]["id"] == "19"


def test_no_maximo_cinco_trechos_por_lei():
    lgpd = [_t(f"lgpd{i}", 0.9 - i / 100) for i in range(8)]
    cdc = [_t(f"cdc{i}", 0.6 - i / 100, fonte="Lei 8.078/1990") for i in range(3)]
    escolhidos = selecionar_trechos([lgpd, cdc], teto=12)

    fontes = [t["document_source"] for t in escolhidos]
    assert fontes.count("Lei 13.709/2018") == rag.RAG_MAX_POR_LEI == 5
    assert fontes.count("Lei 8.078/1990") == 3
    assert len(escolhidos) == 8


def test_limite_por_lei_junta_a_mesma_lei_escrita_de_formas_diferentes():
    """Seeds antigos gravaram 'Lei 8.078/1990 (CDC)'; ainda é a mesma lei."""
    resultados = [
        [_t(f"n{i}", 0.9, fonte="Lei 8.078/1990") for i in range(3)],
        [_t(f"v{i}", 0.8, fonte="Lei 8.078/1990 (CDC)") for i in range(3)],
    ]
    assert len(selecionar_trechos(resultados, teto=12)) == 5


def test_abaixo_do_limiar_nao_entra():
    resultados = [[_t("a", 0.29), _t("b", 0.31)]]
    escolhidos = selecionar_trechos(resultados, teto=12, similarity_threshold=0.3)
    assert [t["id"] for t in escolhidos] == ["b"]


def test_empate_nao_depende_da_ordem_das_consultas():
    um = selecionar_trechos([[_t("b", 0.5)], [_t("a", 0.5)]], teto=1)
    outro = selecionar_trechos([[_t("a", 0.5)], [_t("b", 0.5)]], teto=1)
    assert um == outro


# ─── build_legal_context_sync ────────────────────────────────────────────────

def _db_com_base():
    db = MagicMock()
    db.execute.return_value.scalar.return_value = 100  # chunks com embedding
    return db


def test_todas_as_consultas_vao_numa_requisicao_so():
    """É a premissa de pior_caso_da_analise: uma requisição de embedding por tentativa."""
    regras = [{"name": "LGPD", "criteria": "dados pessoais"}]
    vetores = {}

    def lote(textos):
        vetores["textos"] = list(textos)
        return [[float(i)] for i in range(len(textos))]

    buscas = []

    def buscar(db, vetor, top_k):
        buscas.append((vetor, top_k))
        return [_t(f"t{vetor[0]}", 0.6, fonte=f"Lei {int(vetor[0])}/2000")]

    with patch.object(rag, "generate_query_embeddings", side_effect=lote) as em_lote, \
         patch.object(rag, "generate_embedding") as unico, \
         patch.object(rag, "_buscar_por_embedding", side_effect=buscar):
        contexto = rag.build_legal_context_sync(CONTRATO, regras, _db_com_base())

    em_lote.assert_called_once()
    unico.assert_not_called()
    assert vetores["textos"] == consultas_da_analise(CONTRATO, regras)
    assert len(buscas) == len(vetores["textos"]) == 5
    assert all(k == rag.RAG_TRECHOS_POR_CONSULTA == 3 for _, k in buscas)
    assert len(contexto) == 5
    assert set(contexto[0]) == {"source", "article_ref", "content"}


def test_teto_padrao_vem_da_configuracao(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "RAG_MAX_TRECHOS", 2)

    def buscar(db, vetor, top_k):
        return [_t(f"t{vetor[0]}-{j}", 0.6, fonte=f"Lei {vetor[0]}/2000") for j in range(3)]

    with patch.object(rag, "generate_query_embeddings",
                      side_effect=lambda t: [[float(i)] for i in range(len(t))]), \
         patch.object(rag, "_buscar_por_embedding", side_effect=buscar):
        contexto = rag.build_legal_context_sync(CONTRATO, [], _db_com_base())

    assert len(contexto) == 2


def test_falha_no_embedding_em_lote_segue_sem_contexto():
    with patch.object(rag, "generate_query_embeddings", side_effect=TimeoutError("lento")), \
         patch.object(rag, "_buscar_por_embedding") as buscar:
        contexto = rag.build_legal_context_sync(CONTRATO, [], _db_com_base())

    assert contexto == []
    buscar.assert_not_called()


def test_sem_base_indexada_nem_gera_embedding():
    db = MagicMock()
    db.execute.return_value.scalar.return_value = 0
    with patch.object(rag, "generate_query_embeddings") as em_lote:
        assert rag.build_legal_context_sync(CONTRATO, [], db) == []
    em_lote.assert_not_called()


# ─── Embedding em lote ───────────────────────────────────────────────────────

def _cliente_falso(*indices):
    base = MagicMock()
    limitado = base.with_options.return_value
    limitado.embeddings.create.return_value.data = [
        MagicMock(index=i, embedding=[float(i)]) for i in indices
    ]
    return base, limitado


def test_lote_da_consulta_usa_os_limites_da_consulta_unica():
    from app.services import embedding_service as emb

    base, limitado = _cliente_falso(1, 0)  # fora de ordem, como a API pode devolver
    with patch.object(emb, "_get_client", return_value=base):
        assert emb.generate_query_embeddings(["a", "b"]) == [[0.0], [1.0]]

    kwargs = base.with_options.call_args.kwargs
    assert kwargs["max_retries"] == emb.EMBEDDING_MAX_RETRIES == 1
    assert kwargs["timeout"].read == emb.EMBEDDING_TIMEOUT
    assert kwargs["timeout"].connect == emb.EMBEDDING_CONNECT_TIMEOUT
    base.embeddings.create.assert_not_called()
    limitado.embeddings.create.assert_called_once()
    assert limitado.embeddings.create.call_args.kwargs["input"] == ["a", "b"]


def test_lote_com_vetores_faltando_falha_em_vez_de_desalinhar():
    from app.services import embedding_service as emb

    base, _ = _cliente_falso(0)
    with patch.object(emb, "_get_client", return_value=base):
        with pytest.raises(ValueError):
            emb.generate_query_embeddings(["a", "b"])
