"""
RAG Service — Retrieval-Augmented Generation for legislation and legal documents.

Handles:
1. Text chunking with article-boundary awareness
2. Legal document ingestion with embedding generation
3. Semantic similarity search against legislation chunks
4. Context building for prompt enrichment
"""
import asyncio
import re
import logging
from collections import Counter
from typing import List, Dict, Any, Optional

from sqlalchemy import select, func, text as sa_text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_service import (
    generate_embedding,
    generate_embeddings_batch,
    generate_query_embeddings,
)

logger = logging.getLogger(__name__)

_NUMERO_DA_LEI = re.compile(r"(\d{1,3}(?:\.\d{3})*)\s*/\s*(\d{4})")


def chave_da_lei(fonte: str) -> str:
    """Identidade da lei, ignorando como a fonte foi escrita.

    "Lei 8.078/1990" e "Lei 8.078/1990 (CDC)" são a mesma lei, mas a limpeza
    comparava o texto inteiro e por isso não removia a versão antiga: as duas
    conviviam na base, e os trechos velhos, de artigos escolhidos a mão,
    competiam na busca com a lei íntegra.

    Sem número reconhecível, cai no texto normalizado, que ao menos casa consigo
    mesmo em reingestões.
    """
    m = _NUMERO_DA_LEI.search(fonte or "")
    if not m:
        return (fonte or "").strip().lower()
    return f"{m.group(1).replace('.', '')}/{m.group(2)}"

# ─── Article Reference Extraction ───

# Acima de 999 a numeracao usa ponto de milhar ("Art. 1.337"). Sem o grupo
# (?:\.\d{3})* o Codigo Civil inteiro acima do artigo 999 era lido como "Art. 1".
_NUM_ARTIGO = r"\d+(?:\.\d{3})*"

ARTICLE_PATTERN = re.compile(
    rf"(Art\.\s*{_NUM_ARTIGO}[\w°ºª]*(?:\s*,?\s*§\s*\d+[\w°ºª]*)?)"
    r"|"
    r"(§\s*\d+[\w°ºª]*)"
    r"|"
    r"(Parágrafo\s+[Úú]nico)",
    re.IGNORECASE,
)

# O \s* inicial e necessario: o texto oficial vem com espaco depois da quebra de
# linha (" Art. 7o"), e sem ele nenhum artigo era reconhecido como inicio de
# segmento. A lei inteira virava um bloco unico, cortado por tamanho.
ARTICLE_START_PATTERN = re.compile(
    rf"^[ 	]*(Art\.\s*{_NUM_ARTIGO}[\w°ºª]*\.?\s)",
    re.IGNORECASE | re.MULTILINE,
)


# Referência partida por uma quebra de linha: "Art. \r\n 92", "§ \n 2º",
# "Parágrafo \n único", "III \r\n - locação", "a \n )", "1 \n º". O texto do
# Planalto vinha assim porque o HTML quebra linha no meio do código-fonte, e o
# chunking gravava "Art. \r\n92" como article_ref: a verificação procurava
# "Art. 92" e não achava.
_QUEBRA = r"[ \t]*\r?\n\s*"
_REFERENCIAS_QUEBRADAS = [
    (re.compile(rf"\b(Art\.){_QUEBRA}(?=\d)", re.IGNORECASE), r"\1 "),
    (re.compile(rf"(§){_QUEBRA}(?=\d)"), r"\1 "),
    (re.compile(rf"\b(Par[áa]grafo){_QUEBRA}(?=[úu]nico)", re.IGNORECASE), r"\1 "),
    # Inciso: romano sozinho no começo da linha, com o travessão na linha seguinte.
    (re.compile(rf"^([ \t]*[IVXLCDM]+){_QUEBRA}(?=[-–—])", re.MULTILINE), r"\1 "),
    # Alínea: letra sozinha no começo da linha, com o parêntese na seguinte.
    (re.compile(rf"^([ \t]*[a-z]){_QUEBRA}(?=\))", re.MULTILINE), r"\1"),
    # Ordinal: "1" numa linha e "º" na outra.
    (re.compile(rf"(\d){_QUEBRA}(?=[º°ª])"), r"\1"),
]


def normalizar_referencias(texto: str) -> str:
    """Junta artigos, parágrafos, incisos e alíneas partidos por quebra de linha.

    Só mexe dentro da referência; o resto das quebras, que separam artigos e
    incisos, fica como está. Roda em toda ingestão, de qualquer origem.
    """
    for padrao, troca in _REFERENCIAS_QUEBRADAS:
        texto = padrao.sub(troca, texto)
    return texto


def _extract_article_ref(text: str) -> Optional[str]:
    """Extract the first article reference from a text chunk."""
    match = ARTICLE_PATTERN.search(text)
    if match:
        # O \s* do padrão aceita quebra de linha; a referência gravada não deve tê-la.
        return " ".join((match.group(1) or match.group(2) or match.group(3)).split())
    return None


def _split_by_articles(text: str) -> List[str]:
    """Split legal text into segments at article boundaries.

    Returns:
        List of text segments, each starting at an article boundary.
        Preamble text (before first article) is returned as the first segment.
    """
    positions = [m.start() for m in ARTICLE_START_PATTERN.finditer(text)]

    if not positions:
        return [text]

    segments = []
    if positions[0] > 0:
        preamble = text[:positions[0]].strip()
        if preamble:
            segments.append(preamble)

    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        segment = text[pos:end].strip()
        if segment:
            segments.append(segment)

    return segments


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> List[Dict[str, Any]]:
    """Chunk legal text respecting article boundaries where possible.

    Strategy:
    1. Split by article boundaries (Art. X patterns)
    2. If a segment is <= chunk_size, keep as single chunk
    3. If a segment is > chunk_size, split with overlap within that segment

    Args:
        text: Full legal text.
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between chunks within same article.

    Returns:
        List of dicts with keys: content, article_ref, chunk_index.
    """
    segments = _split_by_articles(text)
    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for segment in segments:
        # So conta como artigo o segmento que comeca com "Art. N". O preambulo
        # institucional mencionava artigos no meio do texto e acabava rotulado
        # com uma referencia que nao era a dele.
        article_ref = (
            _extract_article_ref(segment)
            if ARTICLE_START_PATTERN.match(segment)
            else None
        )

        if len(segment) <= chunk_size:
            chunks.append({
                "content": segment,
                "article_ref": article_ref,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        else:
            start = 0
            while start < len(segment):
                end = start + chunk_size

                # Try to break at sentence boundary near the end
                if end < len(segment):
                    boundary_start = max(end - 80, start)
                    boundary_zone = segment[boundary_start:end + 20]
                    best_break = -1
                    for punct in [". ", ".\n", ";\n"]:
                        idx = boundary_zone.rfind(punct)
                        if idx > best_break:
                            best_break = idx
                    if best_break > 0:
                        end = boundary_start + best_break + 1

                chunk_content = segment[start:end].strip()
                if chunk_content:
                    # A referencia do artigo vale para todos os seus pedacos. Sem isto
                    # um pedaco iniciado por "§ 3o" ficava rotulado com o paragrafo, e
                    # uma citacao a "Art. 52" nao casava com o trecho recuperado.
                    sub_ref = article_ref or _extract_article_ref(chunk_content)
                    chunks.append({
                        "content": chunk_content,
                        "article_ref": sub_ref,
                        "chunk_index": chunk_index,
                    })
                    chunk_index += 1

                start = end - overlap if end < len(segment) else len(segment)

    return chunks


# ─── Ingestion ───

def ingest_legal_document_sync(
    title: str,
    full_text: str,
    source: str,
    category: str,
    db: Session,
    chunk_size: int = 800,
    overlap: int = 100,
) -> Any:
    """Ingest a legal document: chunk, embed, and store. SYNC version, for scripts.

    Args:
        title: Display title of the legislation.
        full_text: Full text of the legislation.
        source: Legal reference (e.g. "Lei 13.709/2018 (LGPD)").
        category: Category for filtering (e.g. "proteção_de_dados").
        db: Sync SQLAlchemy session.
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between chunks.

    Returns:
        The created LegalDocument instance.
    """
    from app.models import LegalDocument, LegalChunk

    full_text = normalizar_referencias(full_text)
    legal_doc = LegalDocument(
        title=title,
        source=source,
        category=category,
        full_text=full_text,
    )
    db.add(legal_doc)
    db.flush()

    chunks_data = chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)
    logger.info(f"Documento '{title}' dividido em {len(chunks_data)} chunks")

    texts = [c["content"] for c in chunks_data]
    embeddings = generate_embeddings_batch(texts)

    for chunk_data, embedding in zip(chunks_data, embeddings):
        chunk = LegalChunk(
            document_id=legal_doc.id,
            chunk_index=chunk_data["chunk_index"],
            content=chunk_data["content"],
            article_ref=chunk_data["article_ref"],
            embedding=embedding,
            metadata_={
                "source": source,
                "category": category,
                "char_count": len(chunk_data["content"]),
            },
        )
        db.add(chunk)

    db.commit()
    logger.info(f"Documento legal '{title}' ingerido: {len(chunks_data)} chunks com embeddings")
    return legal_doc


async def ingest_legal_document_async(
    title: str,
    full_text: str,
    source: str,
    category: str,
    db: AsyncSession,
    chunk_size: int = 800,
    overlap: int = 100,
) -> Any:
    """Ingest a legal document: chunk, embed, and store. ASYNC version for API.

    Args:
        title: Display title of the legislation.
        full_text: Full text of the legislation.
        source: Legal reference (e.g. "Lei 13.709/2018 (LGPD)").
        category: Category for filtering (e.g. "proteção_de_dados").
        db: Async SQLAlchemy session.
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between chunks.

    Returns:
        The created LegalDocument instance.
    """
    from app.models import LegalDocument, LegalChunk

    full_text = normalizar_referencias(full_text)
    legal_doc = LegalDocument(
        title=title,
        source=source,
        category=category,
        full_text=full_text,
    )
    db.add(legal_doc)
    await db.flush()

    chunks_data = chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)
    logger.info(f"Documento '{title}' dividido em {len(chunks_data)} chunks")

    texts = [c["content"] for c in chunks_data]
    embeddings = await asyncio.to_thread(generate_embeddings_batch, texts)

    for chunk_data, embedding in zip(chunks_data, embeddings):
        chunk = LegalChunk(
            document_id=legal_doc.id,
            chunk_index=chunk_data["chunk_index"],
            content=chunk_data["content"],
            article_ref=chunk_data["article_ref"],
            embedding=embedding,
            metadata_={
                "source": source,
                "category": category,
                "char_count": len(chunk_data["content"]),
            },
        )
        db.add(chunk)

    await db.flush()
    logger.info(f"Documento legal '{title}' ingerido: {len(chunks_data)} chunks com embeddings")
    return legal_doc


# ─── Semantic Search ───

def _fmt_embedding(emb: List[float]) -> str:
    """Format embedding list as pgvector-compatible string."""
    return "[" + ",".join(str(float(x)) for x in emb) + "]"


def _build_search_results(rows: Any) -> List[Dict[str, Any]]:
    """Convert raw DB rows to search result dicts."""
    return [
        {
            "id": str(row.id),
            "content": row.content,
            "article_ref": row.article_ref,
            "document_title": row.document_title,
            "document_source": row.document_source,
            "similarity": round(float(row.similarity), 4),
        }
        for row in rows
    ]


def _buscar_por_embedding(db: Session, embedding: List[float], top_k: int) -> List[Dict[str, Any]]:
    """Busca por similaridade a partir de um embedding já calculado."""
    result = db.execute(
        sa_text(_build_search_sql()),
        {"embedding": _fmt_embedding(embedding), "top_k": top_k},
    )
    return _build_search_results(result.fetchall())


def _build_search_sql(category: Optional[str] = None) -> str:
    """Build the full search SQL with optional category filter."""
    sql = """
        SELECT
            lc.id,
            lc.content,
            lc.article_ref,
            ld.title AS document_title,
            ld.source AS document_source,
            1 - (lc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM legal_chunks lc
        JOIN legal_documents ld ON ld.id = lc.document_id
        WHERE lc.embedding IS NOT NULL
    """
    if category:
        sql += " AND ld.category = :category"
    sql += " ORDER BY lc.embedding <=> CAST(:embedding AS vector) LIMIT :top_k"
    return sql


def search_relevant_chunks_sync(
    query: str,
    db: Session,
    top_k: int = 5,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for relevant legal chunks using cosine similarity. SYNC version."""
    query_embedding = generate_embedding(query)
    emb_str = _fmt_embedding(query_embedding)

    sql = _build_search_sql(category)
    params: Dict[str, Any] = {"embedding": emb_str, "top_k": top_k}
    if category:
        params["category"] = category

    result = db.execute(sa_text(sql), params)
    return _build_search_results(result.fetchall())


async def search_relevant_chunks_async(
    query: str,
    db: AsyncSession,
    top_k: int = 5,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for relevant legal chunks using cosine similarity. ASYNC version."""
    query_embedding = await asyncio.to_thread(generate_embedding, query)
    emb_str = _fmt_embedding(query_embedding)

    sql = _build_search_sql(category)
    params: Dict[str, Any] = {"embedding": emb_str, "top_k": top_k}
    if category:
        params["category"] = category

    result = await db.execute(sa_text(sql), params)
    return _build_search_results(result.fetchall())


# ─── Context Building for Prompt Enrichment ───

def make_base_lookup(db: Session) -> Any:
    """Devolve uma função que procura um artigo citado na base legal inteira.

    A busca semântica traz só o top-k, então um artigo correto e pertinente pode
    ficar de fora do contexto de uma análise. Sem consultar a base, esse artigo
    seria rotulado como citação sem respaldo, embora exista e possa ser lido.
    """
    from sqlalchemy import text as sa_text

    def lookup(legal_basis: str) -> Optional[Dict[str, str]]:
        from app.services.verification import _article_numbers, _law_tokens

        artigos = _article_numbers(legal_basis)
        leis = _law_tokens(legal_basis)

        if not artigos:
            # Citacao so da lei, sem artigo: acontece quando o alerta aponta a
            # AUSENCIA de uma clausula inteira. Basta confirmar que a lei existe.
            if not leis:
                return None
            fontes = db.execute(
                sa_text("SELECT DISTINCT source FROM legal_documents")
            ).scalars().all()
            for fonte in fontes:
                if leis & _law_tokens(fonte or ""):
                    return {"source": fonte, "article_ref": None, "content": None}
            return None

        linhas = db.execute(
            sa_text(
                "SELECT ld.source, lc.article_ref, lc.content "
                "FROM legal_chunks lc JOIN legal_documents ld ON ld.id = lc.document_id "
                "WHERE lc.article_ref IS NOT NULL"
            )
        ).fetchall()

        candidatos = []
        for source, ref, content in linhas:
            if not (_article_numbers(ref or "") & artigos):
                continue
            mesma_lei = bool(leis & _law_tokens(f"{source} {ref}"))
            candidatos.append((mesma_lei, source, ref, content))

        if not candidatos:
            return None
        # Prefere o artigo da lei citada; sem isso, "Art. 51" casaria com o
        # artigo 51 de qualquer uma das dez leis da base.
        candidatos.sort(key=lambda c: not c[0])
        if leis and not candidatos[0][0]:
            return None

        _, source, ref, content = candidatos[0]
        return {"source": source, "article_ref": ref, "content": (content or "").strip()}

    return lookup


# ─── Consultas da análise ───
#
# Uma consulta só, feita com o começo do contrato, recuperava a lei do cabeçalho
# e não a das cláusulas: num contrato com cláusula inteira de tratamento de dados,
# a consulta pegava a qualificação das partes e trazia Marco Civil, CLT e CDC,
# nenhum artigo da LGPD. Cada cláusula agora é uma consulta, e cada regra ativa
# também, e os resultados são fundidos.

# Trechos aproveitados de cada consulta, antes da fusão.
RAG_TRECHOS_POR_CONSULTA = 3
# Nenhuma lei ocupa mais que isto do contexto, por mais que domine a busca.
RAG_MAX_POR_LEI = 5
# Alvo do agrupamento de parágrafos, no contrato que não usa "CLÁUSULA".
RAG_ALVO_PARAGRAFOS = 800
# Pedaço curto demais para dizer sobre o que é (um título solto, uma assinatura).
RAG_MIN_CHARS_CONSULTA = 40
# Limites de uma requisição de embedding: cada texto fica bem abaixo dos 8.192
# tokens por entrada, e 120 x 6.000 caracteres, ~200 mil tokens, abaixo dos 300
# mil por requisição.
RAG_MAX_CHARS_CONSULTA = 6000
RAG_MAX_CONSULTAS = 120
# Requisições de embedding por tentativa da análise; pior_caso_da_analise conta com isto.
CHAMADAS_DE_EMBEDDING_POR_ANALISE = 1

# "CLÁUSULA" no início da linha seguida de ordinal: número ("4ª", "10"), romano
# ("IV") ou ordinal por extenso ("QUARTA", "Décima"). Sem exigir o começo de linha,
# "conforme a cláusula 5ª" no meio de uma frase partiria o texto.
_INICIO_DE_CLAUSULA = re.compile(
    r"^[ \t]*CL[ÁA]USULA\s+(?:\d+|[IVXLC]+\b|\w+a\b)", re.IGNORECASE | re.MULTILINE
)
_MARCA_DE_PAGINA = re.compile(
    r"^[ \t]*---\s*Página\s+\d+[^\n]*---[ \t]*$", re.IGNORECASE | re.MULTILINE
)


def _agrupar_paragrafos(texto: str, alvo: int = RAG_ALVO_PARAGRAFOS) -> List[str]:
    """Parágrafos, com os curtos juntados aos vizinhos até ~`alvo` caracteres.

    Parágrafo é o que fica entre linhas em branco. Texto sem linha em branco, comum
    em PDF, cai para uma linha por parágrafo. Um parágrafo maior que o alvo fica
    sozinho, inteiro.
    """
    paragrafos = [p.strip() for p in re.split(r"\n[ \t]*\n", texto) if p.strip()]
    if len(paragrafos) <= 1:
        paragrafos = [p.strip() for p in texto.splitlines() if p.strip()]

    grupos: List[str] = []
    atual = ""
    for p in paragrafos:
        if atual and len(atual) + 1 + len(p) > alvo:
            grupos.append(atual)
            atual = p
        else:
            atual = f"{atual}\n{p}" if atual else p
    if atual:
        grupos.append(atual)
    return grupos


def dividir_em_clausulas(texto: str) -> List[str]:
    """Divide o contrato em cláusulas, ou em grupos de parágrafos se não houver.

    Conta como dividido em cláusulas o texto com pelo menos duas: com uma só, a
    divisão separaria apenas o preâmbulo do resto. O preâmbulo, antes da primeira
    cláusula, vira uma consulta como as outras; considerandos costumam morar nele.
    """
    texto = _MARCA_DE_PAGINA.sub("", texto or "")
    inicios = [m.start() for m in _INICIO_DE_CLAUSULA.finditer(texto)]
    if len(inicios) >= 2:
        limites = inicios + [len(texto)]
        partes = [texto[: inicios[0]]] + [texto[a:b] for a, b in zip(limites, limites[1:])]
    else:
        partes = _agrupar_paragrafos(texto)
    return [p.strip() for p in partes if len(p.strip()) >= RAG_MIN_CHARS_CONSULTA]


def consultas_da_analise(document_text: str, rules: List[Dict[str, Any]]) -> List[str]:
    """As consultas de uma análise: uma por regra ativa e uma por cláusula.

    As regras vêm primeiro porque são poucas e cada uma é um tema que a análise
    vai verificar de qualquer jeito. Se o total passar de RAG_MAX_CONSULTAS, o que
    sobra são as últimas cláusulas, e isso fica no log.
    """
    por_regra = [
        f"{r.get('name', '').strip()}: {r.get('criteria', '').strip()}".strip(": ")
        for r in rules
    ]
    consultas = [c for c in por_regra if c] + dividir_em_clausulas(document_text)
    if len(consultas) > RAG_MAX_CONSULTAS:
        logger.warning(
            "RAG: %d consultas, acima do limite de %d; as últimas cláusulas ficam de fora",
            len(consultas), RAG_MAX_CONSULTAS,
        )
        consultas = consultas[:RAG_MAX_CONSULTAS]
    return [c[:RAG_MAX_CHARS_CONSULTA] for c in consultas]


def selecionar_trechos(
    resultados_por_consulta: List[List[Dict[str, Any]]],
    teto: int,
    por_lei: int = RAG_MAX_POR_LEI,
    similarity_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    """Funde os resultados das consultas no contexto da análise.

    O mesmo trecho trazido por várias consultas entra uma vez, com a maior
    similaridade que teve. Depois, por similaridade decrescente, até `teto`
    trechos e no máximo `por_lei` de cada lei: uma lei longa e genérica, como o
    Código Civil, não toma o lugar de todas as outras.
    """
    melhores: Dict[str, Dict[str, Any]] = {}
    for resultados in resultados_por_consulta:
        for trecho in resultados:
            if trecho["similarity"] < similarity_threshold:
                continue
            atual = melhores.get(trecho["id"])
            if atual is None or trecho["similarity"] > atual["similarity"]:
                melhores[trecho["id"]] = trecho

    # O id desempata, para a seleção não depender da ordem das consultas.
    ordenados = sorted(melhores.values(), key=lambda t: (-t["similarity"], t["id"]))
    escolhidos: List[Dict[str, Any]] = []
    por_fonte: Counter = Counter()
    for trecho in ordenados:
        lei = chave_da_lei(trecho["document_source"])
        if por_fonte[lei] >= por_lei:
            continue
        escolhidos.append(trecho)
        por_fonte[lei] += 1
        if len(escolhidos) >= teto:
            break
    return escolhidos


def build_legal_context_sync(
    document_text: str,
    rules: List[Dict[str, Any]],
    db: Session,
    top_k: Optional[int] = None,
    similarity_threshold: float = 0.3,
) -> List[Dict[str, str]]:
    """Contexto legal da análise. Versão síncrona, para a thread da análise.

    Uma consulta por cláusula do contrato e uma por regra ativa, com todos os
    embeddings numa requisição só. Cada consulta traz os RAG_TRECHOS_POR_CONSULTA
    trechos mais próximos, e `selecionar_trechos` funde tudo.

    Args:
        document_text: Texto extraído do contrato.
        rules: Regras ativas do escopo da análise (com 'name' e 'criteria').
        db: Sessão síncrona.
        top_k: Teto de trechos no contexto; padrão RAG_MAX_TRECHOS.
        similarity_threshold: Similaridade mínima para um trecho entrar.

    Returns:
        Lista de dicts com source, article_ref e content. Vazia se não houver base
        indexada ou se o embedding falhar: a análise segue sem contexto legal.
    """
    # Check if any legislation is indexed WITH embeddings
    from app.models import LegalChunk
    count = db.execute(
        select(func.count()).select_from(LegalChunk).where(LegalChunk.embedding.isnot(None))
    ).scalar()
    if not count:
        logger.info("Nenhuma legislação indexada — pulando contexto legal")
        return []

    if top_k is None:
        from app.core.config import get_settings

        top_k = get_settings().RAG_MAX_TRECHOS

    consultas = consultas_da_analise(document_text, rules)
    if not consultas:
        logger.info("Contrato sem texto para consultar — pulando contexto legal")
        return []

    try:
        vetores = generate_query_embeddings(consultas)
    except Exception as exc:
        logger.warning("Embedding das consultas do RAG falhou (seguindo sem contexto): %s", exc)
        return []

    resultados = [_buscar_por_embedding(db, v, RAG_TRECHOS_POR_CONSULTA) for v in vetores]
    relevant = selecionar_trechos(
        resultados, teto=top_k, similarity_threshold=similarity_threshold
    )

    if not relevant:
        logger.info("Nenhum contexto legal relevante acima do threshold")
        return []

    logger.info(
        "Contexto legal: %d trechos de %d consultas (%s)",
        len(relevant), len(consultas),
        dict(Counter(chave_da_lei(c["document_source"]) for c in relevant)),
    )

    return [
        {
            "source": c["document_source"],
            "article_ref": c["article_ref"] or "Sem referência",
            "content": c["content"],
        }
        for c in relevant
    ]
