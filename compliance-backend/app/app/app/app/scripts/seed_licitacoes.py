"""
Step 11: Seed Lei de Licitações Data
Standalone script with key articles from Lei 14.133/2021 (Arts. 5, 25, 89, 92, 104, 105, 115, 124, 137, 155, 156, 169).
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_licitacoes
    # or
    python app/scripts/seed_licitacoes.py
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


# ── Lei de Licitações Articles Data ──────────────────────────────────────────

LICITACOES_ARTICLES = [
    {
        "article_number": "Art. 5",
        "title": "Princípios das Licitações e Contratações",
        "content": (
            "Art. 5º Na aplicação desta Lei, serão observados os princípios de legalidade, impessoalidade, "
            "moralidade, publicidade, eficiência, probidade administrativa, equidade, bom senso, interesse público "
            "e não discriminação.\n\n"
            "§ 1º O princípio da legalidade compreende o respeito às normas estabelecidas por lei, decreto, "
            "regulamento ou ato normativo pertinente.\n\n"
            "§ 2º O princípio da impessoalidade implica que a administração não pode discriminar fornecedores ou "
            "contratados em função de considerações de índole pessoal.\n\n"
            "§ 3º O princípio da moralidade exige que a administração atue com honestidade, lealdade e boa-fé "
            "nas contratações.\n\n"
            "§ 4º O princípio da publicidade abrange a necessidade de transparência em todos os atos da licitação "
            "e contratação, permitindo o conhecimento de todos os interessados.\n\n"
            "§ 5º O princípio da eficiência impõe o dever de alcançar o melhor resultado com o menor custo possível."
        ),
    },
    {
        "article_number": "Art. 25",
        "title": "Fase Preparatória",
        "content": (
            "Art. 25. A fase preparatória tem como objetivo a formulação pela administração pública de estratégia "
            "adequada à contratação, visando à solução do problema identificado.\n\n"
            "§ 1º Integram a fase preparatória:\n"
            "I - a definição da necessidade de contratação e a justificativa desta;\n"
            "II - a identificação e análise das alternativas de solução para atender à necessidade;\n"
            "III - a escolha da solução que represente a melhor relação custo-benefício;\n"
            "IV - a definição de estratégia de contratação que contemple as melhores condições para a administração "
            "pública, tais como o modo de disputa, a forma de julgamento e os critérios de aceitabilidade;\n"
            "V - a definição das obrigações da contratada, seus prazos e as sanções pelo seu não cumprimento.\n\n"
            "§ 2º Durante a fase preparatória, a administração pública pode realizar consulta prévia ao mercado, "
            "destinada a subsidiar a definição de critérios, parâmetros e prazos para a contratação."
        ),
    },
    {
        "article_number": "Art. 89",
        "title": "Formalização dos Contratos",
        "content": (
            "Art. 89. A contratação será formalizada mediante a celebração de termo de contrato ou, quando couber, "
            "de acordo de cooperação técnica.\n\n"
            "§ 1º O termo de contrato é o instrumento formal que dá origem à obrigação de fazer, podendo ser celebrado "
            "por instrumento próprio ou pelo preenchimento de formulário-padrão.\n\n"
            "§ 2º O acordo de cooperação técnica é o instrumento por meio do qual a administração pública e a contratada "
            "estabelecem obrigações recíprocas em razão de interesse comum.\n\n"
            "§ 3º A celebração do contrato deverá ocorrer no prazo de sessenta dias após a assinatura da nota de "
            "empenho ou do termo de aceite da proposta, contado o prazo até o quinto dia útil subsequente, sendo "
            "prorrogável por igual período quando solicitado pela contratada antes de findo o prazo inicial, desde que "
            "apresentados motivos justificados."
        ),
    },
    {
        "article_number": "Art. 92",
        "title": "Cláusulas Necessárias dos Contratos",
        "content": (
            "Art. 92. Os contratos devem estabelecer com clareza as obrigações de cada parte, os direitos, deveres e "
            "responsabilidades das partes contratantes.\n\n"
            "§ 1º As cláusulas essenciais do contrato são:\n"
            "I - descrição do objeto da contratação, com as especificações necessárias à sua identificação;\n"
            "II - o regime de execução e o prazo de execução;\n"
            "III - o preço e as condições de pagamento, inclusive quanto aos reajustes;\n"
            "IV - a data de início da execução;\n"
            "V - a multa moratória e a multa por inadimplemento das obrigações contratuais;\n"
            "VI - os direitos e as responsabilidades das partes;\n"
            "VII - as hipóteses de extinção do contrato;\n"
            "VIII - as obrigações concernentes à responsabilidade civil.\n\n"
            "§ 2º O contrato deverá prever sanções pelo atraso na execução dos serviços ou na entrega dos bens, "
            "sem prejuízo da responsabilidade civil."
        ),
    },
    {
        "article_number": "Art. 104",
        "title": "Regime de Execução dos Contratos",
        "content": (
            "Art. 104. Os contratos podem ser executados sob os seguintes regimes:\n\n"
            "I - execução por preço global: quando o contrato é celebrado por um preço fixo e invariável durante toda "
            "a execução, independentemente da variação dos custos dos insumos necessários;\n"
            "II - execução por unidade: quando o pagamento é realizado por unidades efetivamente executadas, dentro "
            "do cronograma acordado;\n"
            "III - execução por tarefa: quando há a execução de tarefas específicas, com preço previamente acordado;\n"
            "IV - execução por empreitada integral: quando se realiza, de uma só vez, empreendimento ou serviço completo, "
            "como a construção de um edifício, por um preço global fixo;\n"
            "V - execução em regime de custo reembolsável: quando os custos decorrentes da execução são reembolsados à "
            "contratada, sem incluir o lucro, este fixado como percentual dos custos totais."
        ),
    },
    {
        "article_number": "Art. 105",
        "title": "Garantias na Execução do Contrato",
        "content": (
            "Art. 105. A administração pública pode exigir garantia de execução do contrato.\n\n"
            "§ 1º A garantia pode ser exigida em valor não inferior a cinco por cento do valor do contrato e não superior "
            "a dez por cento, exceto nos casos de contratos de pequeno valor ou quando justificado pela administração pública "
            "em razão de maior complexidade e risco.\n\n"
            "§ 2º A garantia pode ser prestada na modalidade de:\n"
            "I - caução em dinheiro;\n"
            "II - seguro-garantia;\n"
            "III - fiança bancária ou de sociedade seguradora;\n"
            "IV - título da dívida pública da União ou de ente federado com prazo de resgate compatível com a duração do contrato.\n\n"
            "§ 3º A garantia será liberada ou restituída ao final do contrato, após a comprovação do cumprimento de todas "
            "as obrigações contratuais."
        ),
    },
    {
        "article_number": "Art. 115",
        "title": "Duração dos Contratos",
        "content": (
            "Art. 115. Os contratos decorrentes de licitação terão duração determinada, observados os prazos especificados "
            "no instrumento convocatório.\n\n"
            "§ 1º A duração será a mínima necessária para o cumprimento das obrigações especificadas.\n\n"
            "§ 2º É permitida a renovação de contratos mediante a celebração de novo contrato ou a prorrogação de contrato "
            "existente, desde que expressamente autorizado no instrumento convocatório e justificado pela administração pública, "
            "observados os seguintes requisitos:\n"
            "I - a duração total do contrato, incluindo as prorrogações, não poderá ultrapassar cinco anos, salvo para contratos "
            "de prestação de serviços continuados;\n"
            "II - deverão ser respeitadas as normas pertinentes e os prazos para publicidade e divulgação da proposta de prorrogação."
        ),
    },
    {
        "article_number": "Art. 124",
        "title": "Alteração dos Contratos",
        "content": (
            "Art. 124. O contrato poderá ser alterado, unilateral ou bilateralmente, mediante termo aditivo assinado pelas partes, "
            "observados os requisitos e as formalidades previstos nesta Lei.\n\n"
            "§ 1º A alteração unilateral do contrato poderá ser realizada quando necessária para a adequação do contrato às normas "
            "legais, regulamentares ou administrativas que tenham entrado em vigor após a celebração do contrato, ou quando necessária "
            "para o cumprimento de decisão judicial ou administrativa.\n\n"
            "§ 2º A alteração bilateral será realizada quando acordada entre as partes, com a devida justificação, observadas as seguintes "
            "limitações:\n"
            "I - o valor final do contrato não poderá ser alterado além de vinte e cinco por cento acima ou abaixo do valor inicial, "
            "de forma isolada ou cumulativa;\n"
            "II - as alterações não poderão prejudicar os direitos e as obrigações estabelecidos no contrato original.\n\n"
            "§ 3º Qualquer alteração do contrato deve ser publicada para fins de transparência e publicidade."
        ),
    },
    {
        "article_number": "Art. 137",
        "title": "Extinção dos Contratos - Hipóteses",
        "content": (
            "Art. 137. O contrato será extinto nas seguintes hipóteses:\n\n"
            "I - conclusão do objeto do contrato;\n"
            "II - rescisão consensual, quando acordada entre as partes, mediante termo aditivo;\n"
            "III - rescisão unilateral, pela administração pública, quando a contratada descumprir obrigações contratuais essenciais;\n"
            "IV - rescisão administrativa, quando comprovado que a contratada não possui condições financeiras para executar o contrato;\n"
            "V - rescisão por força maior ou caso fortuito, quando eventos extraordinários e imprevisíveis impossibilitem a execução "
            "do contrato por qualquer uma das partes;\n"
            "VI - morte ou incapacidade da contratada;\n"
            "VII - fusão, incorporação ou transformação da contratada, salvo se aceita pela administração pública;\n"
            "VIII - vencimento do prazo estabelecido no contrato;\n"
            "IX - término do crédito orçamentário necessário ao pagamento das obrigações decorrentes do contrato.\n\n"
            "§ 1º A rescisão deverá ser precedida de processo administrativo que assegure o direito de defesa da contratada.\n\n"
            "§ 2º Será publicizado, na imprensa oficial, a extinção do contrato."
        ),
    },
    {
        "article_number": "Art. 155",
        "title": "Sanções Administrativas",
        "content": (
            "Art. 155. A contratada que inadimplir total ou parcialmente qualquer obrigação contratual fica sujeita à aplicação das "
            "seguintes sanções administrativas:\n\n"
            "I - advertência, sempre que ocorrer atraso no cumprimento de qualquer obrigação contratual;\n"
            "II - multa, na forma prevista no contrato, pelo atraso na execução do objeto da contratação;\n"
            "III - multa de até dez por cento sobre o valor do contrato, pelo descumprimento das obrigações contratuais ou pela "
            "recusa em executar o contrato;\n"
            "IV - multa de até vinte por cento sobre o valor do contrato, em caso de dano ao patrimônio público ou terceiros;\n"
            "V - suspensão do direito de participar de licitações e impedimento de contratar com a administração pública pelo período "
            "máximo de dois anos.\n\n"
            "§ 1º As multas serão descontadas dos valores devidos à contratada ou cobradas como dívida líquida.\n\n"
            "§ 2º As sanções podem ser aplicadas isoladamente ou cumulativamente, de acordo com a gravidade da infração."
        ),
    },
    {
        "article_number": "Art. 156",
        "title": "Sanções Específicas - Multa, Impedimento e Inidoneidade",
        "content": (
            "Art. 156. Além das sanções previstas no artigo anterior, a contratada fica sujeita às seguintes penalidades:\n\n"
            "I - aplicação de multa contratualmente estabelecida, pelo não cumprimento de prazos ou pela má execução do contrato;\n"
            "II - impedimento de contratar com a administração pública, pelo período máximo de cinco anos, quando a contratada agir "
            "com dolo ou fraude na execução do contrato;\n"
            "III - declaração de inidoneidade para contratar com a administração pública, quando comprovado ato ilícito ou condenação "
            "por crime contra a administração pública.\n\n"
            "§ 1º A declaração de inidoneidade será registrada em banco de dados próprio da administração pública, com publicação no "
            "diário oficial competente.\n\n"
            "§ 2º A empresa declarada inidônea não poderá participar de licitações ou contratar com a administração pública enquanto "
            "perdurar a causa de inidoneidade.\n\n"
            "§ 3º O procedimento administrativo para a imposição das sanções será precedido de ampla defesa, com oportunidade de resposta "
            "ao acusado."
        ),
    },
    {
        "article_number": "Art. 169",
        "title": "Controle das Contratações",
        "content": (
            "Art. 169. A administração pública exercerá controle sobre as contratações de bens, serviços e obras, inclusive consultoria, "
            "em todas as suas fases.\n\n"
            "§ 1º O controle será exercido pela própria administração pública e pelos órgãos competentes, incluindo órgãos de auditoria "
            "interna e externa, com o objetivo de verificar o cumprimento das obrigações contratuais e a adequação dos gastos públicos.\n\n"
            "§ 2º A administração pública deverá manter registro atualizado de todas as contratações realizadas, com informações que permitam "
            "rastreabilidade e transparência.\n\n"
            "§ 3º Serão criados e mantidos sob controle da administração pública:\n"
            "I - banco de dados com as informações sobre as contratações realizadas;\n"
            "II - relatórios periódicos sobre a execução dos contratos;\n"
            "III - relatórios sobre o desempenho das contratadas.\n\n"
            "§ 4º Os órgãos de controle interno e externo terão acesso às informações relativas aos contratos para fins de auditoria e "
            "fiscalização, observadas as restrições legais quanto a informações confidenciais ou sigilosas."
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


def seed_licitacoes_articles(engine):
    """
    Seed key Lei de Licitações articles into legal_documents table.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in LICITACOES_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'Lei de Licitações - Lei 14.133/2021'"
                ),
                {"title": f"Lei de Licitações {article['article_number']} - {article['title']}"},
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
                    "title": f"Lei de Licitações {article['article_number']} - {article['title']}",
                    "source": "Lei de Licitações - Lei 14.133/2021",
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
                      AND ld.source = 'Lei de Licitações - Lei 14.133/2021'
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
    print("🏛️  Lei de Licitações - Lei 14.133/2021 Seed Script")
    print("   Artigos: 5, 25, 89, 92, 104, 105, 115, 124, 137, 155, 156, 169")
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
    print("📝 Inserindo artigos da Lei de Licitações...\n")
    success = seed_licitacoes_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed Lei de Licitações concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()
