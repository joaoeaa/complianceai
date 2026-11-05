"""Referências partidas em linha na ingestão, e o reprocessamento de uma lei.

Regressão: o HTML do Planalto quebra linha no meio do código-fonte, e a Lei
14.133 tinha 467 chunks com article_ref "Art. \\r\\n92". A verificação procurava
"Art. 92" e não achava.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import LegalChunk, LegalDocument
from app.scripts.ingest_planalto import (
    POR_SLUG,
    extrair_texto,
    normalizar_texto_gravado,
    reprocessar,
)
from app.services.rag_service import chunk_text, normalizar_referencias


# ─── normalizar_referencias ──────────────────────────────────────────────────

@pytest.mark.parametrize("quebrado, certo", [
    ("Art. \r\n 92 O contrato", "Art. 92 O contrato"),
    ("Art.\n92 O contrato", "Art. 92 O contrato"),
    ("art. \r\n375 , no parágrafo", "art. 375 , no parágrafo"),
    ("Art. \r\n 1.337 O condômino", "Art. 1.337 O condômino"),
    ("referido no § \r\n 2º deste artigo", "referido no § 2º deste artigo"),
    ("Parágrafo \r\n único. Aplica-se", "Parágrafo único. Aplica-se"),
    ("Paragrafo\nunico. Aplica-se", "Paragrafo unico. Aplica-se"),
    ("encomenda;\n\n III \r\n - locação;", "encomenda;\n\n III - locação;"),
    ("serviço;\n\n XIV \n – obras", "serviço;\n\n XIV – obras"),
    ("seguinte:\n a \r\n ) prazo", "seguinte:\n a) prazo"),
    ("Art. 1 \r\n º Esta Lei", "Art. 1º Esta Lei"),
])
def test_junta_a_referencia_partida(quebrado, certo):
    assert normalizar_referencias(quebrado) == certo


@pytest.mark.parametrize("texto", [
    "Art. 1º Esta Lei.\n\nArt. 2º Aplica-se.",          # quebra entre artigos
    "contratações;\n\n IV - locação;\n\n V - obras",   # incisos já inteiros
    "conforme o § 2º.\n\nArt. 3º Fica",                # parágrafo inteiro
    "Seção I\nDas Disposições",                        # romano sem travessão
    "pelo valor de\n10 reais",                         # número sem ordinal
])
def test_nao_mexe_no_que_ja_esta_inteiro(texto):
    assert normalizar_referencias(texto) == texto


def test_chunk_de_texto_quebrado_grava_a_referencia_limpa():
    texto = "Art. \r\n 91 Os contratos serão escritos.\n\n Art. \r\n 92 São necessárias as cláusulas."
    refs = [c["article_ref"] for c in chunk_text(normalizar_referencias(texto))]
    assert refs == ["Art. 91", "Art. 92"]


def test_referencia_extraida_nunca_tem_quebra_de_linha():
    """Mesmo sem normalizar o texto, o rótulo gravado sai sem a quebra."""
    refs = [c["article_ref"] for c in chunk_text("Art. \r\n 92 São necessárias as cláusulas.")]
    assert refs == ["Art. 92"]


# ─── extrair_texto (HTML do Planalto) ────────────────────────────────────────

def test_quebra_do_codigo_fonte_html_vira_espaco():
    html = (
        "<html><body>"
        "<p>Art. \r\n 91 Os contratos e seus aditamentos terão forma \r\nescrita.</p>"
        "<p>Art. \r\n 92 São necessárias em todo contrato cláusulas que estabeleçam:</p>"
        "<p> III \r\n - o preço;</p>"
        "<p>Parágrafo \r\n único. Nos contratos.<br>Segunda linha.</p>"
        "</body></html>"
    ).encode("utf-8")

    texto = extrair_texto(html)

    assert "\r" not in texto
    assert "Art. 91 Os contratos e seus aditamentos terão forma escrita." in texto
    assert "Art. 92 São necessárias" in texto
    assert "III - o preço;" in texto
    assert "Parágrafo único. Nos contratos.\nSegunda linha." in texto
    refs = [c["article_ref"] for c in chunk_text(texto)]
    assert refs == ["Art. 91", "Art. 92"]


# ─── normalizar_texto_gravado (texto já extraído pela versão antiga) ─────────

def test_texto_gravado_perde_as_quebras_do_codigo_fonte():
    gravado = "contrato:\n\n Art. \r\n 92 São necessárias \r\ncláusulas.\n\n III \r\n - o preço;"
    assert normalizar_texto_gravado(gravado) == (
        "contrato:\n\n Art. 92 São necessárias cláusulas.\n\n III - o preço;"
    )


def test_cr_colado_numa_quebra_estrutural_nao_apaga_o_paragrafo():
    assert normalizar_texto_gravado("fim do artigo. \r\n\n Art. 5º Novo") == (
        "fim do artigo. \n\n Art. 5º Novo"
    )


def test_citacao_jogada_para_o_inicio_da_linha_deixa_de_ser_artigo():
    """'art. 20 da Lei 11.033' começava linha só pela quebra do HTML e virava artigo 20."""
    gravado = (
        "Art. 1º O imposto incide nos termos do \r\nart. 20 da Lei nº 11.033, de 2004, "
        "facultada a interposição de recurso."
    )
    antes = [c["article_ref"] for c in chunk_text(gravado)]
    depois = [c["article_ref"] for c in chunk_text(normalizar_texto_gravado(gravado))]
    assert antes == ["Art. 1º", "art. 20"]
    assert depois == ["Art. 1º"]


# ─── reprocessar ─────────────────────────────────────────────────────────────

LICITACOES = POR_SLUG["licitacoes"]
TEXTO_GRAVADO = (
    "Lei de Licitações\n\n Art. \r\n 91 Os contratos serão escritos.\n\n"
    " Art. \r\n 92 São necessárias as cláusulas:\n\n I \r\n - o objeto;"
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lei = LegalDocument(
            title="Lei de Licitações", source="Lei 14.133/2021",
            category="licitacoes", full_text=TEXTO_GRAVADO,
        )
        outra = LegalDocument(title="LGPD", source="Lei 13.709/2018", category="dados", full_text="x")
        session.add_all([lei, outra])
        session.flush()
        for i, ref in enumerate(["Art. \r\n91", "Art. \r\n92"]):
            session.add(LegalChunk(document_id=lei.id, chunk_index=i, content="velho",
                                   article_ref=ref, embedding=[0.0] * 1536, metadata_={}))
        session.add(LegalChunk(document_id=outra.id, chunk_index=0, content="lgpd",
                               article_ref="Art. 7º", embedding=[0.0] * 1536, metadata_={}))
        session.commit()
        yield session
    engine.dispose()


def _refs(db, source):
    return db.execute(
        select(LegalChunk.article_ref).join(LegalDocument)
        .where(LegalDocument.source == source).order_by(LegalChunk.chunk_index)
    ).scalars().all()


def _lote(textos):
    return [[0.5] * 1536 for _ in textos]


def test_reprocessar_troca_os_chunks_da_lei_e_so_dela(db):
    with patch("app.services.embedding_service.generate_embeddings_batch", side_effect=_lote) as lote:
        resumo = reprocessar(LICITACOES, db)

    # O preâmbulo, antes do primeiro artigo, é um chunk sem referência.
    assert _refs(db, "Lei 14.133/2021") == [None, "Art. 91", "Art. 92"]
    assert _refs(db, "Lei 13.709/2018") == ["Art. 7º"]
    assert resumo["refs_quebradas_antes"] == 2 and resumo["refs_quebradas_depois"] == 0
    lote.assert_called_once()
    novos = db.execute(select(LegalChunk.content).join(LegalDocument)
                       .where(LegalDocument.source == "Lei 14.133/2021")).scalars().all()
    assert "velho" not in novos
    assert "I - o objeto;" in "\n".join(novos)
    gravado = db.execute(select(LegalDocument.full_text)
                         .where(LegalDocument.source == "Lei 14.133/2021")).scalar_one()
    assert "\r" not in gravado


def test_reprocessar_sem_gravar_nao_mexe_em_nada_nem_gera_embedding(db):
    with patch("app.services.embedding_service.generate_embeddings_batch") as lote:
        resumo = reprocessar(LICITACOES, db, gravar=False)

    lote.assert_not_called()
    assert resumo["chunks_antes"] == 2
    assert resumo["refs_quebradas_depois"] == 0
    assert _refs(db, "Lei 14.133/2021") == ["Art. \r\n91", "Art. \r\n92"]


def test_falha_no_embedding_deixa_a_lei_como_estava(db):
    with patch("app.services.embedding_service.generate_embeddings_batch",
               side_effect=TimeoutError("lento")):
        with pytest.raises(TimeoutError):
            reprocessar(LICITACOES, db)
    db.rollback()

    assert _refs(db, "Lei 14.133/2021") == ["Art. \r\n91", "Art. \r\n92"]


def test_reprocessar_lei_que_nao_esta_na_base_falha_claro(db):
    with pytest.raises(ValueError, match="exatamente um"):
        reprocessar(POR_SLUG["clt"], db, gravar=False)
