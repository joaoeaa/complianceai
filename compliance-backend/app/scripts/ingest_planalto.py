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
    texto = re.sub(r"(?i)<(br|/p|/div|/tr|/h[1-6])[^>]*>", "\n", texto)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = htmllib.unescape(texto).replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


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


def ingerir(lei: Lei, db: Session, substituir: bool = True) -> int:
    """Ingere uma lei e devolve quantos chunks foram criados."""
    from app.models import LegalChunk, LegalDocument
    from app.services.rag_service import ingest_legal_document_sync

    if substituir:
        # Reingerir sem limpar duplicaria os artigos na busca.
        antigos = db.execute(
            select(LegalDocument).where(LegalDocument.source == lei.fonte)
        ).scalars().all()
        for antigo in antigos:
            db.execute(
                LegalChunk.__table__.delete().where(LegalChunk.document_id == antigo.id)
            )
            db.delete(antigo)
        db.commit()

    texto = baixar_texto(lei)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingere legislação do Planalto.")
    parser.add_argument("--lei", help="slug de uma lei do catálogo")
    parser.add_argument("--todas", action="store_true", help="ingere o catálogo inteiro")
    parser.add_argument("--listar", action="store_true", help="mostra o catálogo")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="baixa e conta os artigos, sem gravar nem gastar embeddings",
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
