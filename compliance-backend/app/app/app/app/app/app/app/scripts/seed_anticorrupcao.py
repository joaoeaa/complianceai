"""
Step 13: Seed Lei Anticorrupção Data
Standalone script with key articles from Lei 12.846/2013 (Arts. 1, 2, 3, 5, 6, 7, 16, 17, 18, 41, 42).
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_anticorrupcao
    # or
    python app/scripts/seed_anticorrupcao.py
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


# ── Lei Anticorrupção Articles Data ────────────────────────────────────────────

ANTICORRUPCAO_ARTICLES = [
    {
        "article_number": "Art. 1",
        "title": "Disposições Gerais - Responsabilização de Pessoas Jurídicas",
        "content": (
            "Art. 1º Esta Lei dispõe sobre a responsabilização objetiva de pessoas jurídicas de "
            "direito privado e de direito público que cometam atos lesivos à administração pública "
            "nacional ou estrangeira.\n\n"
            "§ 1º - A responsabilização das pessoas jurídicas não exclui a responsabilidade civil ou "
            "penal de pessoas físicas que tenham praticado os atos ilícitos.\n\n"
            "§ 2º - A pessoa jurídica é responsável pelos atos praticados por seus administradores, "
            "diretores, empregados, mandatários ou qualquer outro agente que atue em seu nome ou "
            "interesse, ainda que em desconformidade com instruções internas ou normas legais.\n\n"
            "§ 3º - Aplicam-se esta Lei às pessoas jurídicas constituídas sob as leis brasileiras, "
            "com sede no Brasil ou no exterior, que pratiquem atos lesivos à administração pública "
            "brasileira ou estrangeira.\n\n"
            "§ 4º - É irrelevante a verificação, para fins desta Lei, de culpa ou dolo na conduta "
            "da pessoa jurídica."
        ),
    },
    {
        "article_number": "Art. 2",
        "title": "Responsabilidade Objetiva da Pessoa Jurídica",
        "content": (
            "Art. 2º - Constituem atos lesivos à administração pública nacional ou estrangeira, para "
            "os fins desta Lei, todos aqueles praticados pelas pessoas jurídicas mencionadas no artigo "
            "anterior que ensejem perda, estrago ou corrupção de bens públicos ou bens públicos "
            "estrangeiros, ou percepção indevida de valores do erário ou tesouro estrangeiro.\n\n"
            "§ 1º - Considera-se pessoa jurídica, para os fins desta Lei, a empresa individual de "
            "responsabilidade limitada prevista na Lei nº 6.404, de 15 de dezembro de 1976, e a "
            "sociedade limitada.\n\n"
            "§ 2º - A responsabilização objetiva da pessoa jurídica não impede que sejam responsabilizados "
            "concorrentemente os administradores, diretores, empregados e demais agentes que "
            "participaram dos atos ilícitos."
        ),
    },
    {
        "article_number": "Art. 3",
        "title": "Responsabilização Independente de Culpa ou Dolo",
        "content": (
            "Art. 3º - A pessoa jurídica será responsabilizada independentemente da existência de culpa "
            "ou dolo em relação aos atos praticados por seus agentes ou administradores, ainda que "
            "contra suas orientações ou instruções internas.\n\n"
            "§ 1º - A responsabilização será baseada na responsabilidade objetiva, isto é, no "
            "cometimento do ato lesivo pela pessoa jurídica ou por seus agentes em seu nome ou interesse.\n\n"
            "§ 2º - Na apuração da responsabilidade objetiva, a administração pública não necessita "
            "demonstrar culpa ou dolo, apenas a existência do ato lesivo e a vinculação da pessoa "
            "jurídica ao ato.\n\n"
            "§ 3º - A pessoa jurídica poderá exonerar-se de responsabilidade total ou parcialmente "
            "demonstrando que adotou programa de integridade adequado e implementado no momento do "
            "cometimento do ato ilícito."
        ),
    },
    {
        "article_number": "Art. 5",
        "title": "Atos Lesivos à Administração Pública",
        "content": (
            "Art. 5º - Constituem atos lesivos à administração pública, inclusive à administração pública "
            "estrangeira, para os fins desta Lei:\n\n"
            "I - prometer, oferecer ou dar, direta ou indiretamente, vantagem indevida a agente público, "
            "ou a terceira pessoa a ele relacionada;\n"
            "II - financiar, custear, patrocinar ou de qualquer modo subvencionar a prática dos atos "
            "ilícitos previstos nesta Lei;\n"
            "III - comprovar a existência de vantagem patrimonial, privada ou indevida, obtida ou "
            "transferida, durante ou após a realização dos atos ilícitos;\n"
            "IV - obstruir, impedir ou dificultar a investigação ou fiscalização de irregularidades ou "
            "infrações desta Lei;\n"
            "V - destruir, falsificar ou ocultar documentos relacionados à realização dos atos ilícitos;\n"
            "VI - exercer influência sobre testemunhas, peritos ou autoridades com o objetivo de "
            "impedir a investigação ou fiscalização;\n"
            "VII - tentar ocular a participação ou envolvimento em atos ilícitos.\n\n"
            "Parágrafo único. A configuração dos atos lesivos independe da verificação de culpa ou "
            "dolo, sendo suficiente o cometimento da ação descrita neste artigo."
        ),
    },
    {
        "article_number": "Art. 6",
        "title": "Sanções Administrativas",
        "content": (
            "Art. 6º - As pessoas jurídicas que cometerem os atos previstos nesta Lei estarão sujeitas "
            "às seguintes sanções:\n\n"
            "I - multa, no valor de 0,1% (um décimo por cento) a 20% (vinte por cento) do faturamento "
            "bruto da pessoa jurídica, excludentes os tributos, no ano anterior ao da instauração do "
            "processo administrativo, ou no ano em que se consumou o ato ilícito, se este ocorrer em "
            "período diverso;\n"
            "II - perda dos benefícios fiscais e subsídios concedidos por órgãos e entidades da "
            "administração pública federal;\n"
            "III - suspensão ou interdição parcial de atividades;\n"
            "IV - dissolução compulsória da pessoa jurídica;\n"
            "V - proibição de contratar com a administração pública.\n\n"
            "§ 1º - A multa será multiplicada por três (3) nas hipóteses em que a pessoa jurídica seja "
            "reincidente.\n\n"
            "§ 2º - A suspensão ou interdição será aplicada por período que não pode ser inferior a um "
            "(1) ano e nem superior a cinco (5) anos."
        ),
    },
    {
        "article_number": "Art. 7",
        "title": "Parâmetros para Aplicação de Sanções - Atenuantes",
        "content": (
            "Art. 7º - As sanções serão aplicadas gradativa ou cumulativamente, e considerados os "
            "seguintes fatores:\n\n"
            "I - a gravidade da infração;\n"
            "II - a vantagem auferida ou pretendida pelo infrator;\n"
            "III - a consequência do ato ilícito;\n"
            "IV - o grau de envolvimento ou responsabilidade da pessoa jurídica;\n"
            "V - a existência de mecanismos e procedimentos internos de detecção e correção de "
            "irregularidades;\n"
            "VI - o cumprimento de deveres de diligência e vigilância;\n"
            "VII - a adoção de programa de integridade;\n"
            "VIII - a pronta adoção de medidas para reparação ou mitigação do dano;\n"
            "IX - a cooperação com as autoridades encarregadas da investigação ou fiscalização;\n"
            "X - a confissão ou reconhecimento da responsabilidade.\n\n"
            "§ 1º - Na aplicação das sanções, poderão ser considerados como fatores atenuantes os "
            "esforços para implantação de programa de integridade, mesmo incompletos.\n\n"
            "§ 2º - Considera-se programa de integridade, para os fins desta Lei, o conjunto de "
            "mecanismos e procedimentos de integridade, auditoria e incentivos instituídos pela "
            "pessoa jurídica."
        ),
    },
    {
        "article_number": "Art. 16",
        "title": "Acordo de Leniência - Negociação e Requisitos",
        "content": (
            "Art. 16. A pessoa jurídica poderá celebrar acordo de leniência com a administração pública "
            "federal, visando à isenção ou à redução das sanções administrativas previstas nesta Lei, "
            "desde que a pessoa jurídica:\n\n"
            "I - seja a primeira a se apresentar voluntariamente com informações que comprovem a prática "
            "do ato ilícito por seus agentes;\n"
            "II - tenha cessado completamente seu envolvimento na prática do ato ilícito a partir da "
            "data de apresentação da proposta de acordo;\n"
            "III - coopere plenamente com as autoridades investigadoras e judiciárias;\n"
            "IV - atenda aos demais requisitos previstos em regulamentação.\n\n"
            "§ 1º - O acordo de leniência será celebrado com a administração pública federal, por meio "
            "de órgão específico designado.\n\n"
            "§ 2º - A celebração do acordo de leniência não impede a responsabilização penal de pessoas "
            "físicas que tenham participado do ato ilícito."
        ),
    },
    {
        "article_number": "Art. 17",
        "title": "Acordo de Leniência - Benefícios e Requisitos",
        "content": (
            "Art. 17. A pessoa jurídica que celebrar acordo de leniência poderá ser isenta da perda de "
            "benefícios fiscais e subsídios, além de poder ter reduzidas as multas aplicáveis de 1/3 "
            "(um terço) a 2/3 (dois terços).\n\n"
            "§ 1º - A isenção ou a redução das sanções será na proporção da colaboração prestada e do "
            "resultado prático obtido em decorrência do acordo.\n\n"
            "§ 2º - O acordo de leniência deverá conter disposições que assegurem a reparação dos danos "
            "causados pela prática do ato ilícito, bem como outras obrigações que a administração pública "
            "puder impor.\n\n"
            "§ 3º - A existência de mecanismos e procedimentos internos de detecção e correção de "
            "irregularidades é considerada como circunstância que favorece a celebração do acordo e a "
            "redução das sanções."
        ),
    },
    {
        "article_number": "Art. 18",
        "title": "Acordo de Leniência - Sigilo e Proteção de Informações",
        "content": (
            "Art. 18. As informações fornecidas pela pessoa jurídica no âmbito do acordo de leniência "
            "serão mantidas sob sigilo, sem prejuízo das exigências de divulgação impostas pela "
            "administração pública.\n\n"
            "§ 1º - O acordo de leniência não implica na isenção de responsabilidade criminal de "
            "pessoas físicas, nem na de responsabilização de terceiros pela prática dos mesmos atos "
            "ilícitos.\n\n"
            "§ 2º - As informações fornecidas no âmbito do acordo de leniência não podem ser divulgadas "
            "ou utilizadas para fins de responsabilização de terceiros, sem consentimento da pessoa "
            "jurídica que as forneceu, ressalvados os casos em que a divulgação for necessária para "
            "proteger a administração pública.\n\n"
            "§ 3º - A violação do sigilo das informações pode resultar em ação de indenização por "
            "danos morais e materiais pela pessoa jurídica prejudicada."
        ),
    },
    {
        "article_number": "Art. 41",
        "title": "Programa de Integridade e Compliance",
        "content": (
            "Art. 41. A administração pública federal poderá, no processo de responsabilização, "
            "considerar a adoção e a efetividade de mecanismos e procedimentos internos de integridade, "
            "auditoria e incentivos à sua observância.\n\n"
            "§ 1º - Para fins desta Lei, entende-se por programa de integridade o conjunto de "
            "mecanismos e procedimentos internos de integridade, auditoria e incentivos instituídos, "
            "aplicados e efetivos, no âmbito da pessoa jurídica, destinado a detectar e sanar desvios, "
            "fraudes, irregularidades e atos ilícitos praticados contra a administração pública, "
            "inclusive no exterior.\n\n"
            "§ 2º - O programa de integridade deve conter, no mínimo, as dimensões previstas no artigo "
            "seguinte e ser compatível com os tamanho e complexidade da pessoa jurídica.\n\n"
            "§ 3º - A existência de programa de integridade é considerada como atenuante na aplicação "
            "das sanções previstas nesta Lei."
        ),
    },
    {
        "article_number": "Art. 42",
        "title": "Parâmetros do Programa de Integridade",
        "content": (
            "Art. 42. Para fins desta Lei, o programa de integridade deve conter, no mínimo, os "
            "seguintes parâmetros:\n\n"
            "I - comprometimento da alta administração da pessoa jurídica, incluindo conselhos, "
            "board ou órgãos equivalentes, com a adoção, aplicação e efetividade do programa;\n"
            "II - padrões de conduta, códigos ou políticas éticas, aplicáveis a todos os "
            "administradores, diretores, empregados e demais agentes da pessoa jurídica;\n"
            "III - estruturação, descrição e documentação da atividade de integridade, incluindo suas "
            "relações de subordinação e reporte;\n"
            "IV - políticas e procedimentos de recursos humanos, incluindo recrutamento, avaliação de "
            "desempenho e remuneração, compatíveis com os objetivos do programa de integridade;\n"
            "V - procedimentos de avaliação, auditoria e monitoramento, inclusive de pessoas físicas "
            "e jurídicas terceirizadas que atuem em seu nome ou interesse;\n"
            "VI - código de conduta escrito, proibindo no mínimo a realização de atos contra a "
            "administração pública, com sanções disciplinares claras e progressivas;\n"
            "VII - canais de denúncias, internos e externos, acessíveis a todos os empregados e ao "
            "público em geral, com proteção ao denunciante;\n"
            "VIII - medidas disciplinares claras e progressivas para infratores das políticas do "
            "programa;\n"
            "IX - procedimentos que assegurem a identificação e exclusão de pessoas jurídicas parceiras "
            "com antecedentes de prática de atos ilícitos;\n"
            "X - integração do programa com a alta administração da pessoa jurídica.\n\n"
            "Parágrafo único. O programa de integridade deve ser adaptado às características da pessoa "
            "jurídica, levando em consideração seu tamanho, complexidade, volume de transações e risco "
            "de envolvimento em atos ilícitos."
        ),
    },
]


# ── Seed Script ────────────────────────────────────────────────────────────────

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


def seed_anticorrupcao_articles(engine):
    """
    Seed key Lei Anticorrupção articles into legal_documents table.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in ANTICORRUPCAO_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'Lei Anticorrupção - Lei 12.846/2013'"
                ),
                {"title": f"Anticorrupção {article['article_number']} - {article['title']}"},
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
                    "title": f"Anticorrupção {article['article_number']} - {article['title']}",
                    "source": "Lei Anticorrupção - Lei 12.846/2013",
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
                      AND ld.source = 'Lei Anticorrupção - Lei 12.846/2013'
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
    print("🏛️  Lei Anticorrupção Seed Script")
    print("   Lei 12.846/2013")
    print("   Artigos: 1, 2, 3, 5, 6, 7, 16, 17, 18, 41, 42")
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
    print("📝 Inserindo artigos da Lei Anticorrupção...\n")
    success = seed_anticorrupcao_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed Anticorrupção concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()
