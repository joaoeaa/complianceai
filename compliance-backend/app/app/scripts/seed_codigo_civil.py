"""
Step 11B: Seed Código Civil Brasileiro Data
Standalone script with key Código Civil articles (Arts. 104, 138, 145, 151, 157, 171, 317, 389, 395, 421, 422, 423, 424, 472, 473, 475, 478, 479, 480, 927).
Focuses on CONTRACT compliance analysis.
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_codigo_civil
    # or
    python app/scripts/seed_codigo_civil.py
"""

import sys
import os
import uuid
from datetime import datetime, timezone
from uuid import uuid4
# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session

from app.core.config import Settings
settings = Settings()


# ── Código Civil Articles Data ──────────────────────────────────────────────────

CC_ARTICLES = [
    {
        "article_number": "Art. 104",
        "title": "Requisitos de Validade do Negócio Jurídico",
        "content": (
            "Art. 104. A validade do negócio jurídico requer:\n\n"
            "I - agente capaz;\n"
            "II - objeto lícito, possível, determinado ou determinável;\n"
            "III - forma prescrita ou não defesa em lei.\n\n"
            "Parágrafo único. Dispõe-se sobre a defesa de direitos pelo incapaz, sem prejuízo da nulidade do ato."
        ),
    },
    {
        "article_number": "Art. 138",
        "title": "Erro como Vício de Consentimento",
        "content": (
            "Art. 138. São anuláveis os negócios jurídicos, quando as vontades dos agentes, ao manifestarem-se, forem viciadas por erro, dolo, coação, estado de perigo, lesão ou fraude na formação.\n\n"
            "Parágrafo único. Pode também ser anulado o negócio jurídico realizado sem liberdade de manifestação de vontade, em razão de erro essencial relativo à pessoa, à coisa ou ao fundamento que o determinou."
        ),
    },
    {
        "article_number": "Art. 145",
        "title": "Dolo",
        "content": (
            "Art. 145. Considera-se dolo a astúcia, a falsidade ou malícia do agente, que com ela prejudica e induz a vítima ao erro.\n\n"
            "§ 1º Se ambas as partes procedem com dolo, nenhuma pode alegá-lo em proveito próprio.\n\n"
            "§ 2º Responde por dolo quem promete ou presta a obrigação sabendo ou devendo saber que é impossível."
        ),
    },
    {
        "article_number": "Art. 151",
        "title": "Coação",
        "content": (
            "Art. 151. A coação, para viciar a manifestação de vontade, há de ser tal que incuta ao paciente fundado receio de dano iminente e considerável à sua pessoa, à sua família, ou aos seus bens.\n\n"
            "Parágrafo único. Se disser respeito a pessoa não legalmente dependente do coagido, o fundado receio há de ser de dano considerável.\n\n"
            "Obs.: O descumprimento do dever de boa-fé não constitui fundamento para coação em sentido contratual."
        ),
    },
    {
        "article_number": "Art. 157",
        "title": "Lesão",
        "content": (
            "Art. 157. Ocorre lesão quando uma pessoa, sob premente necessidade, ou por inexperiência, se obriga a prestação manifestamente desproporcionada ao valor da prestação oposta.\n\n"
            "§ 1º Aprecia-se a desproporção das prestações segundo os valores vigentes ao tempo em que se celebrou o negócio jurídico.\n\n"
            "§ 2º Não se decretará a anulação do negócio, se for oferecido suplemento do valor ou outra prestação que, a juízo do juiz, equidistante a desproporção.\n\n"
            "§ 3º Executa ou renovou o contrato com pleno conhecimento da desproporção, não poderá o devedor reclamar, posteriormente, a anulação do negócio jurídico."
        ),
    },
    {
        "article_number": "Art. 171",
        "title": "Anulabilidade do Negócio Jurídico",
        "content": (
            "Art. 171. Além dos casos expressamente declarados nesta Lei, é anulável o negócio jurídico:\n\n"
            "I - por incapacidade relativa do agente;\n"
            "II - por vício resultante de erro, dolo, coação, estado de perigo, lesão ou fraude no consentimento;\n"
            "III - por incapacidade, ilicitude do objeto ou desrespeito à forma prescrita em lei.\n\n"
            "§ 1º A anulação não prejudicará os direitos de terceiros de boa-fé em relação aos quais se operou a prescrição.\n\n"
            "§ 2º Se o negócio jurídico for anulado por vícios no consentimento, vigoram as disposições do art. 182."
        ),
    },
    {
        "article_number": "Art. 317",
        "title": "Revisão por Onerosidade Excessiva - Prestações",
        "content": (
            "Art. 317. Quando, por ocasião da celebração do negócio jurídico, houve má distribuição das prestações entre as partes, do modo que uma delas tenha assumido prestação excessivamente onerosa, em comparação com a da outra, poderá o juiz, a pedido da parte prejudicada, conceder-lhe abatimento equitativo da prestação ou até mesmo rescindir o contrato.\n\n"
            "§ 1º A ação deverá ser proposta dentro de um ano depois de executado o negócio jurídico, se este for de execução instantânea, ou desde a data em que passou a ser excessivamente onerosa, se for de execução continuada ou diferida.\n\n"
            "§ 2º Não se aplica este artigo aos contratos aleatórios, nem aos que tenham por objeto prestações periódicas cujo valor seja reajustável conforme a cláusula de revisão ou indexação expressa na avença."
        ),
    },
    {
        "article_number": "Art. 389",
        "title": "Inadimplemento das Obrigações",
        "content": (
            "Art. 389. Não cumprida a obrigação, responde o devedor por perdas e danos, mais juros e atualização monetária segundo índices oficiais regularmente estabelecidos, e honorários de advogado.\n\n"
            "§ 1º As perdas e danos incluem, além do que o credor efetivamente perdeu, o que razoavelmente deixou de ganhar.\n\n"
            "§ 2º Se a obrigação for de fazer, a indenização compreenderá o custo da execução e de reparação do dano causado, bem como lucros cessantes.\n\n"
            "§ 3º Se a obrigação for de não fazer, a indenização compreenderá o valor da perda sofrida pelo credor, mais o lucro cessante."
        ),
    },
    {
        "article_number": "Art. 395",
        "title": "Mora do Devedor",
        "content": (
            "Art. 395. Responde o devedor pelos prejuízos resultantes de mora, mais juros, atualização dos valores monetários conforme índices oficiais regularmente estabelecidos e honorários de advogado.\n\n"
            "§ 1º Se o devedor não for constituído em mora, não lhe podem ser exigidos juros moratórios.\n\n"
            "§ 2º Para a constituição em mora é necessária interpelação, ressalvado o caso previsto no art. 397, inciso I, desta Lei.\n\n"
            "§ 3º O devedor responde pela mora ainda que dela decorra lesão ao credor."
        ),
    },
    {
        "article_number": "Art. 421",
        "title": "Função Social do Contrato",
        "content": (
            "Art. 421. A liberdade de contratar será exercida em razão e nos limites da função social do contrato.\n\n"
            "Parágrafo único. As partes são obrigadas a cumprir os contratos, respeitando a função social que lhes é inerente."
        ),
    },
    {
        "article_number": "Art. 422",
        "title": "Boa-fé Objetiva",
        "content": (
            "Art. 422. Os contratantes são obrigados a guardar, assim na conclusão do contrato, como em sua execução, os princípios de probidade e boa-fé.\n\n"
            "Parágrafo único. Incluem-se na obrigação de boa-fé:\n\n"
            "I - informar a contraparte sobre fatos relevantes ao contrato que o agente conhece ou deveria conhecer;\n"
            "II - agir com lealdade nas negociações e execução contratual;\n"
            "III - não frustrar a finalidade do contrato através de comportamentos oportunistas ou abusivos;\n"
            "IV - reparar danos causados por violação de deveres de informação ou cooperação."
        ),
    },
    {
        "article_number": "Art. 423",
        "title": "Contrato de Adesão",
        "content": (
            "Art. 423. Quando há entre os contratantes desigualdade de poder contratual, cabe ao juiz anular ou rescindir o contrato, ou ainda, modificar equitativamente as cláusulas contratadas, a fim de refletir adequadamente a alocação de riscos entre as partes.\n\n"
            "§ 1º Presume-se exagerada, havendo justo motivo para tanto, a cláusula que estabelece prestação excessivamente onerosa, comparada com a prestação da outra parte.\n\n"
            "§ 2º O juiz poderá, segundo as circunstâncias particulares do caso, conceder abatimento equitativo da prestação excessivamente onerosa."
        ),
    },
    {
        "article_number": "Art. 424",
        "title": "Cláusula de Renúncia Antecipada em Adesão",
        "content": (
            "Art. 424. Em contrato de adesão, são nulas as cláusulas que estipulem a renúncia antecipada a direito resultante da natureza do negócio.\n\n"
            "Parágrafo único. Perde sua eficácia a renúncia antecipada a reclamação ou defesa, quando realizada em contrato de adesão, salvo se a outra parte oferecer, imediatamente, alternativa razoável."
        ),
    },
    {
        "article_number": "Art. 472",
        "title": "Distrato",
        "content": (
            "Art. 472. A revogação do contrato será processada por acordo das partes, em instrumento público ou particular.\n\n"
            "§ 1º Não se admite revogação contratual de outra forma que não seja por acordo entre as partes, salvo nos casos previstos em lei.\n\n"
            "§ 2º Se a revogação prejudicar direitos de terceiros, observar-se-ão as disposições que a lei estabelecer."
        ),
    },
    {
        "article_number": "Art. 473",
        "title": "Resilição Unilateral",
        "content": (
            "Art. 473. A resilição unilateral, nos casos em que a lei expressa ou implicitamente o permita, opera mediante denúncia notificada à outra parte.\n\n"
            "§ 1º Se indenizável a resilição, a indenização será fixada conforme o que dispuserem as normas específicas deste Código, ou, na falta destas, de acordo com o que for equitativo.\n\n"
            "§ 2º A resilição é ineficaz se não expressa na forma do caput, ou se realizada de má-fé."
        ),
    },
    {
        "article_number": "Art. 475",
        "title": "Resolução por Inadimplemento",
        "content": (
            "Art. 475. A parte inocente pode pedir a resolução do contrato, se não preferir exigir o seu cumprimento, casos em que lhe será devida indenização por perdas e danos, quando da parte contrária proceder com dolo ou culpa.\n\n"
            "Parágrafo único. Se preferir a resolução, o contratante inocente não será obrigado a aguardar o seu cumprimento pelo outro, salvo nas hipóteses em que a lei o exija."
        ),
    },
    {
        "article_number": "Art. 478",
        "title": "Resolução por Onerosidade Excessiva",
        "content": (
            "Art. 478. Nos contratos de execução continuada ou diferida, se a prestação de uma das partes se tornar excessivamente onerosa, com extrema vantagem para a outra, em virtude de acontecimentos extraordinários e imprevisíveis, a parte lesada poderá pedir a resolução do contrato.\n\n"
            "§ 1º Não se concedem os efeitos deste artigo aos contratos aleatórios, nem aos de execução instantânea já realizada por completo.\n\n"
            "§ 2º A parte prejudicada pode também exigir a modificação do contrato a fim de adequar as prestações aos efeitos supervenientes."
        ),
    },
    {
        "article_number": "Art. 479",
        "title": "Modificação Equitativa das Condições Contratuais",
        "content": (
            "Art. 479. A resolução poderá ser evitada ofertando-se modificação das condições do contrato que as reduza a termos equitativos.\n\n"
            "Parágrafo único. Ouvidas as partes, o juiz decidirá, conforme as circunstâncias, sobre a modificação ou a resolução, observados os princípios da equidade e da função social do contrato."
        ),
    },
    {
        "article_number": "Art. 480",
        "title": "Reequilíbrio em Obrigações de Uma Parte",
        "content": (
            "Art. 480. Se no contrato as obrigações couberem a uma só parte, poderá ela pedir a resolução se pela superveniência de acontecimentos extraordinários e imprevisíveis a execução se tornar excessivamente onerosa.\n\n"
            "Parágrafo único. Neste caso, nem a resolução deverá ser decretada sem que antes o juiz tente adequar as condições do contrato a termos equitativos, salvo se isso se mostrar impossível ou contrário à natureza ou função do contrato."
        ),
    },
    {
        "article_number": "Art. 927",
        "title": "Responsabilidade Civil",
        "content": (
            "Art. 927. Aquele que, por ato ilícito (arts. 186 e 187), causar dano a outrem, fica obrigado a repará-lo.\n\n"
            "Parágrafo único. Haverá obrigação de reparar o dano, independentemente de culpa, nos casos especificados em lei, ou quando a atividade normalmente desenvolvida pelo autor do dano implicar, por sua natureza, risco para os direitos de outrem."
        ),
    },
]


# ── Seed Script ──────────────────────────────────────────────────────────────

def get_sync_engine():
    """Create a synchronous SQLAlchemy engine from settings."""
    # Convert async URL to sync if needed
    db_url = str(settings.DATABASE_URL)
    if db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
    elif db_url.startswith("postgresql+aiosqlite"):
        db_url = db_url.replace("postgresql+aiosqlite", "sqlite", 1)

    return create_engine(db_url, echo=False)


def check_table_exists(engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def seed_cc_articles(engine):
    """
    Seed key Código Civil articles into legal_documents table.
    Focuses on CONTRACT compliance analysis.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in CC_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'Código Civil - Lei 10.406/2002'"
                ),
                {"title": f"CC {article['article_number']} - {article['title']}"},
            ).fetchone()

            if existing:
                skipped_count += 1
                print(f"  ⏭  {article['article_number']} já existe, pulando...")
                continue

            doc_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            session.execute(
                text(
                    """
                    INSERT INTO legal_documents (id, title, source, category, full_text, created_at)
                    VALUES (:id, :title, :source, :category, :full_text, :created_at)
                    """
                ),
                {
                    "id": str(uuid4()),
                    "title": f"CC {article['article_number']} - {article['title']}",
                    "source": "Código Civil - Lei 10.406/2002",
                    "category": "legislation",
                    "full_text": article["content"],
                    "created_at": now,
                },
            )
            seeded_count += 1
            print(f"  ✅ {article['article_number']} inserido (id: {doc_id[:8]}...)")

        session.commit()

    print(f"\n📊 Resultado: {seeded_count} inseridos, {skipped_count} já existiam")
    return True


def trigger_embedding_generation(engine):
    """
    Optionally trigger chunking + embedding for newly seeded documents.
    This depends on whether rag_service is available.
    """
    try:
        from app.services.rag_service import chunk_and_embed_document_sync

        with Session(engine) as session:
            # Find legal_documents without chunks
            docs_without_chunks = session.execute(
                text(
                    """
                    SELECT ld.id, ld.title
                    FROM legal_documents ld
                    LEFT JOIN legal_chunks lc ON lc.document_id = ld.id
                    WHERE lc.id IS NULL
                      AND ld.source = 'Código Civil - Lei 10.406/2002'
                    """
                )
            ).fetchall()

            if not docs_without_chunks:
                print("\n✨ Todos os documentos já possuem chunks/embeddings.")
                return

            print(f"\n🔄 Gerando chunks + embeddings para {len(docs_without_chunks)} documentos...")
            for doc_id, title in docs_without_chunks:
                try:
                    chunk_and_embed_document_sync(session, doc_id)
                    print(f"  ✅ Embeddings gerados: {title}")
                except Exception as e:
                    print(f"  ⚠️  Erro ao gerar embeddings para {title}: {e}")

            session.commit()

    except ImportError:
        print("\n💡 rag_service não disponível. Embeddings serão gerados sob demanda.")
    except Exception as e:
        print(f"\n⚠️  Erro ao gerar embeddings: {e}")
        print("   Os embeddings podem ser gerados posteriormente via API POST /ingest.")


def main():
    print("=" * 60)
    print("🏛️  Código Civil Brasileiro Seed Script")
    print("   Artigos: 104, 138, 145, 151, 157, 171, 317, 389, 395,")
    print("            421, 422, 423, 424, 472, 473, 475, 478, 479, 480, 927")
    print("   Foco: CONTRACT Compliance Analysis")
    print("=" * 60)
    print()

    try:
        engine = get_sync_engine()

        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Conexão com banco de dados OK\n")

    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        print("   Verifique DATABASE_URL nas configurações.")
        sys.exit(1)

    # Seed articles
    print("📝 Inserindo artigos do Código Civil...\n")
    success = seed_cc_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed Código Civil concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()
