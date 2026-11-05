"""Ingestão da legislação a partir do Planalto.

A base legal alimenta o RAG e, por consequência, a verificação dos alertas: um
artigo que não está aqui nunca recebe o selo "Artigo conferido", mesmo quando a
citação está correta. Antes deste script a base tinha 53 artigos escolhidos a
mão, o que deixava a maior parte das citações sem como conferir.

Aqui o texto vem da fonte oficial, lei inteira, e o chunking por artigo já
existente em `rag_service` faz o resto.

Uso:
    python -m app.scripts.ingest_planalto --listar
    python -m app.scripts.ingest_planalto --lei lgpd
    python -m app.scripts.ingest_planalto --todas
    python -m app.scripts.ingest_planalto --todas --dry-run
    python -m app.scripts.ingest_planalto --lei licitacoes --reprocessar --dry-run
    python -m app.scripts.ingest_planalto --lei licitacoes --reprocessar

--reprocessar refaz os chunks de uma lei já ingerida a partir do texto gravado
no banco, sem baixar do Planalto: normaliza, fatia, gera os embeddings e troca
os chunks antigos pelos novos numa transação só.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

import html as htmllib

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Mora no rag_service porque o RAG também a usa, no limite de trechos por lei.
from app.services.rag_service import chave_da_lei, normalizar_referencias

# O Planalto fecha a conexão sem User-Agent de navegador.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class Lei:
    slug: str
    titulo: str
    fonte: str        # como aparece na citação: "Lei 13.709/2018"
    categoria: str
    url: str


CATALOGO: list[Lei] = [
    # ── Base já usada pelas regras padrão ───────────────────────────────────
    # A pagina "compilada" e so um indice; o texto vive em L10406.htm
    Lei("codigo-civil", "Código Civil", "Lei 10.406/2002", "civil",
        "https://www.planalto.gov.br/ccivil_03/leis/2002/L10406.htm"),
    Lei("cdc", "Código de Defesa do Consumidor", "Lei 8.078/1990", "consumidor",
        "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm"),
    Lei("clt", "Consolidação das Leis do Trabalho", "Decreto-Lei 5.452/1943", "trabalhista",
        "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm"),
    Lei("lgpd", "Lei Geral de Proteção de Dados", "Lei 13.709/2018", "protecao_de_dados",
        "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm"),
    Lei("marco-civil", "Marco Civil da Internet", "Lei 12.965/2014", "internet",
        "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm"),
    Lei("anticorrupcao", "Lei Anticorrupção", "Lei 12.846/2013", "anticorrupcao",
        "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2013/lei/l12846.htm"),
    Lei("licitacoes", "Lei de Licitações e Contratos", "Lei 14.133/2021", "licitacoes",
        "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm"),

    # ── Áreas que hoje não têm nenhuma cobertura ────────────────────────────
    Lei("inquilinato", "Lei do Inquilinato", "Lei 8.245/1991", "locacao",
        "https://www.planalto.gov.br/ccivil_03/leis/l8245.htm"),
    Lei("sociedades-anonimas", "Lei das Sociedades por Ações", "Lei 6.404/1976", "societario",
        "https://www.planalto.gov.br/ccivil_03/leis/l6404compilada.htm"),
    Lei("propriedade-industrial", "Lei de Propriedade Industrial", "Lei 9.279/1996", "propriedade_industrial",
        "https://www.planalto.gov.br/ccivil_03/leis/l9279.htm"),
]

POR_SLUG = {lei.slug: lei for lei in CATALOGO}


def _decodificar(conteudo: bytes) -> str:
    """As páginas antigas do Planalto são latin-1, mesmo declarando utf-8."""
    for encoding in ("utf-8", "latin-1"):
        try:
            return conteudo.decode(encoding)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="replace")


def extrair_texto(conteudo: bytes) -> str:
    """Converte o HTML do Planalto em texto corrido.

    Feito com expressões regulares, e não com parser de árvore, de propósito: o
    HTML vem do FrontPage e tem tags mal fechadas que fazem o lxml abandonar o
    documento no meio. No Código Civil ele parava no artigo 57 de 2.046.

    Trechos em <strike> e <del> são descartados: o Planalto usa essa marcação
    para a redação revogada, que apareceria duplicada ao lado da vigente.
    """
    bruto = _decodificar(conteudo)

    texto = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", bruto)
    texto = re.sub(r"(?is)<(strike|del)\b[^>]*>.*?</\1>", " ", texto)
    texto = re.sub(r"(?is)<s\b[^>]*>.*?</s>", " ", texto)
    # No HTML, a quebra de linha do código-fonte é espaço; quem quebra linha são
    # as tags abaixo. Sem isto, o editor do Planalto, que quebra no meio da frase,
    # deixava "Art. \r\n 92" e "III \r\n - locação" no texto e nas referências.
    texto = re.sub(r"\s+", " ", texto)
    texto = re.sub(r"(?i)<(br|/p|/div|/tr|/h[1-6])[^>]*>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = htmllib.unescape(texto).replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return normalizar_referencias(texto.strip())


def normalizar_texto_gravado(texto: str) -> str:
    """Corrige um texto já extraído pela versão anterior de `extrair_texto`.

    Ali as quebras estruturais, vindas das tags, são "\\n", e as do código-fonte
    sobreviveram como "\\r\\n" no meio da frase: estas viram espaço. Lei cujo HTML
    usa só "\\n" não tem como ser separada assim, e fica com a normalização das
    referências, que vale para qualquer texto.
    """
    texto = re.sub(r"\r(?=\n[ \t]*\n)", "", texto)   # CR colado numa quebra estrutural
    texto = re.sub(r"[ \t]*\r\n[ \t]*", " ", texto)
    texto = texto.replace("\r", " ")
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return normalizar_referencias(texto)


def baixar_texto(lei: Lei, timeout: float = 120.0) -> str:
    """Baixa a lei e devolve o texto corrido, sem marcação."""
    resposta = httpx.get(
        lei.url, headers=_HEADERS, timeout=timeout, follow_redirects=True, verify=False
    )
    resposta.raise_for_status()
    return extrair_texto(resposta.content)


def contar_artigos(texto: str) -> int:
    """Artigos distintos. Acima de 999 o Planalto usa ponto de milhar: 'Art. 1.337'."""
    return len({m.replace(".", "") for m in re.findall(r"Art\.\s*([\d.]+\d)", texto)})


def _documentos_da_lei(lei: Lei, db: Session) -> list:
    from app.models import LegalDocument

    alvo = chave_da_lei(lei.fonte)
    return [
        doc for doc in db.execute(select(LegalDocument)).scalars().all()
        if chave_da_lei(doc.source) == alvo
    ]


def _referencias_quebradas(refs) -> int:
    return sum(1 for r in refs if r and re.search(r"[\r\n]|\s{2,}", r))


def reprocessar(lei: Lei, db: Session, gravar: bool = True) -> dict:
    """Refaz os chunks de uma lei já ingerida, a partir do texto gravado.

    Não baixa nada: vale para corrigir o fatiamento sem depender do Planalto no
    ar. Os embeddings são gerados antes de qualquer remoção, e a troca dos chunks
    vai numa transação só: se algo falhar no meio, a lei fica como estava.

    Com `gravar=False`, só calcula o que mudaria, sem gerar embeddings.
    """
    from app.models import LegalChunk
    from app.services.embedding_service import generate_embeddings_batch
    from app.services.rag_service import chunk_text

    documentos = _documentos_da_lei(lei, db)
    if len(documentos) != 1:
        raise ValueError(
            f"{lei.fonte}: {len(documentos)} documentos na base; reprocessar exige "
            "exatamente um. Use a ingestão normal, que substitui todos."
        )
    documento = documentos[0]
    antigos = db.execute(
        select(LegalChunk.article_ref).where(LegalChunk.document_id == documento.id)
    ).scalars().all()

    texto = normalizar_texto_gravado(documento.full_text or "")
    novos = chunk_text(texto)
    resumo = {
        "chunks_antes": len(antigos),
        "chunks_depois": len(novos),
        "refs_quebradas_antes": _referencias_quebradas(antigos),
        "refs_quebradas_depois": _referencias_quebradas(c["article_ref"] for c in novos),
        "artigos_antes": len({r for r in antigos if r}),
        "artigos_depois": len({c["article_ref"] for c in novos if c["article_ref"]}),
    }
    if not gravar:
        return resumo

    embeddings = generate_embeddings_batch([c["content"] for c in novos])
    db.execute(LegalChunk.__table__.delete().where(LegalChunk.document_id == documento.id))
    for dados, embedding in zip(novos, embeddings):
        db.add(LegalChunk(
            document_id=documento.id,
            chunk_index=dados["chunk_index"],
            content=dados["content"],
            article_ref=dados["article_ref"],
            embedding=embedding,
            metadata_={
                "source": documento.source,
                "category": documento.category,
                "char_count": len(dados["content"]),
            },
        ))
    documento.full_text = texto
    db.commit()
    return resumo


def ingerir(lei: Lei, db: Session, substituir: bool = True) -> int:
    """Ingere uma lei e devolve quantos chunks foram criados."""
    from app.models import LegalChunk, LegalDocument
    from app.services.rag_service import ingest_legal_document_sync

    # Baixa antes de apagar: com o Planalto fora do ar, a lei antiga fica.
    texto = baixar_texto(lei)

    if substituir:
        # Reingerir sem limpar duplicaria os artigos na busca. A comparação é pelo
        # número da lei, e não pelo texto da fonte, porque seeds antigos gravaram
        # a mesma lei com sufixo: "Lei 8.078/1990 (CDC)".
        alvo = chave_da_lei(lei.fonte)
        antigos = [
            doc
            for doc in db.execute(select(LegalDocument)).scalars().all()
            if chave_da_lei(doc.source) == alvo
        ]
        for antigo in antigos:
            db.execute(
                LegalChunk.__table__.delete().where(LegalChunk.document_id == antigo.id)
            )
            db.delete(antigo)
        db.commit()

    documento = ingest_legal_document_sync(
        title=lei.titulo,
        full_text=texto,
        source=lei.fonte,
        category=lei.categoria,
        db=db,
    )
    total = db.execute(
        select(LegalChunk).where(LegalChunk.document_id == documento.id)
    ).scalars().all()
    return len(total)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingere legislação do Planalto.")
    parser.add_argument("--lei", help="slug de uma lei do catálogo")
    parser.add_argument("--todas", action="store_true", help="ingere o catálogo inteiro")
    parser.add_argument("--listar", action="store_true", help="mostra o catálogo")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="baixa e conta os artigos, sem gravar nem gastar embeddings",
    )
    parser.add_argument(
        "--reprocessar", action="store_true",
        help="refaz os chunks a partir do texto já gravado no banco, sem baixar",
    )
    args = parser.parse_args(argv)

    if args.listar:
        print(f"{'slug':24s} {'fonte':26s} categoria")
        for lei in CATALOGO:
            print(f"{lei.slug:24s} {lei.fonte:26s} {lei.categoria}")
        return

    if args.lei:
        alvos = [POR_SLUG[args.lei]] if args.lei in POR_SLUG else []
        if not alvos:
            print(f"Lei desconhecida: {args.lei}. Use --listar para ver as opções.")
            sys.exit(1)
    elif args.todas:
        alvos = CATALOGO
    else:
        parser.print_help()
        sys.exit(1)

    if args.reprocessar:
        _main_reprocessar(alvos, gravar=not args.dry_run)
        return

    if args.dry_run:
        total = 0
        for lei in alvos:
            try:
                texto = baixar_texto(lei)
                artigos = contar_artigos(texto)
                total += artigos
                print(f"OK    {lei.slug:24s} {artigos:5d} artigos  ({len(texto):>8,} chars)")
            except Exception as exc:
                print(f"FALHA {lei.slug:24s} {type(exc).__name__}: {str(exc)[:60]}")
        print(f"\nTotal: {total} artigos")
        return

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        for lei in alvos:
            try:
                with Session(engine) as db:
                    chunks = ingerir(lei, db)
                print(f"OK    {lei.slug:24s} {chunks:5d} chunks")
            except Exception as exc:
                print(f"FALHA {lei.slug:24s} {type(exc).__name__}: {str(exc)[:80]}")
    finally:
        engine.dispose()


def _main_reprocessar(alvos: list, gravar: bool) -> None:
    from app.core.config import get_settings

    engine = create_engine(get_settings().DATABASE_URL_SYNC)
    try:
        alvo = f"{engine.url.host or 'local'}/{engine.url.database or ''}"
        print(f"Banco: {alvo}" + ("" if gravar else "  [dry-run: nada será gravado]"))
        for lei in alvos:
            try:
                with Session(engine) as db:
                    r = reprocessar(lei, db, gravar=gravar)
                print(
                    f"{'OK   ' if gravar else 'SERIA'} {lei.slug:24s} "
                    f"chunks {r['chunks_antes']} -> {r['chunks_depois']}, "
                    f"artigos {r['artigos_antes']} -> {r['artigos_depois']}, "
                    f"refs quebradas {r['refs_quebradas_antes']} -> {r['refs_quebradas_depois']}"
                )
            except Exception as exc:
                print(f"FALHA {lei.slug:24s} {type(exc).__name__}: {str(exc)[:100]}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
