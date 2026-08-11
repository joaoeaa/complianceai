"""
Step 11: Seed LGPD Data
Standalone script with key LGPD articles (Arts. 1, 2, 5, 7, 18, 46, 48, 52).
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_lgpd
    # or
    python app/scripts/seed_lgpd.py
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


# ── LGPD Articles Data ──────────────────────────────────────────────────────

LGPD_ARTICLES = [
    {
        "article_number": "Art. 1",
        "title": "Disposições Preliminares – Objeto da Lei",
        "content": (
            "Art. 1º Esta Lei dispõe sobre o tratamento de dados pessoais, inclusive nos meios "
            "digitais, por pessoa natural ou por pessoa jurídica de direito público ou privado, "
            "com o objetivo de proteger os direitos fundamentais de liberdade e de privacidade e "
            "o livre desenvolvimento da personalidade da pessoa natural.\n\n"
            "Parágrafo único. As normas gerais contidas nesta Lei são de interesse nacional e "
            "devem ser observadas pela União, Estados, Distrito Federal e Municípios."
        ),
    },
    {
        "article_number": "Art. 2",
        "title": "Fundamentos da Proteção de Dados",
        "content": (
            "Art. 2º A disciplina da proteção de dados pessoais tem como fundamentos:\n\n"
            "I - o respeito à privacidade;\n"
            "II - a autodeterminação informativa;\n"
            "III - a liberdade de expressão, de informação, de comunicação e de opinião;\n"
            "IV - a inviolabilidade da intimidade, da honra e da imagem;\n"
            "V - o desenvolvimento econômico e tecnológico e a inovação;\n"
            "VI - a livre iniciativa, a livre concorrência e a defesa do consumidor; e\n"
            "VII - os direitos humanos, o livre desenvolvimento da personalidade, a dignidade "
            "e o exercício da cidadania pelas pessoas naturais."
        ),
    },
    {
        "article_number": "Art. 5",
        "title": "Definições",
        "content": (
            "Art. 5º Para os fins desta Lei, considera-se:\n\n"
            "I - dado pessoal: informação relacionada a pessoa natural identificada ou identificável;\n"
            "II - dado pessoal sensível: dado pessoal sobre origem racial ou étnica, convicção "
            "religiosa, opinião política, filiação a sindicato ou a organização de caráter religioso, "
            "filosófico ou político, dado referente à saúde ou à vida sexual, dado genético ou "
            "biométrico, quando vinculado a uma pessoa natural;\n"
            "III - dado anonimizado: dado relativo a titular que não possa ser identificado, "
            "considerando a utilização de meios técnicos razoáveis e disponíveis na ocasião de "
            "seu tratamento;\n"
            "IV - banco de dados: conjunto estruturado de dados pessoais, estabelecido em um ou "
            "em vários locais, em suporte eletrônico ou físico;\n"
            "V - titular: pessoa natural a quem se referem os dados pessoais que são objeto de "
            "tratamento;\n"
            "VI - controlador: pessoa natural ou jurídica, de direito público ou privado, a quem "
            "competem as decisões referentes ao tratamento de dados pessoais;\n"
            "VII - operador: pessoa natural ou jurídica, de direito público ou privado, que "
            "realiza o tratamento de dados pessoais em nome do controlador;\n"
            "VIII - encarregado: pessoa indicada pelo controlador e operador para atuar como "
            "canal de comunicação entre o controlador, os titulares dos dados e a Autoridade "
            "Nacional de Proteção de Dados (ANPD);\n"
            "IX - agentes de tratamento: o controlador e o operador;\n"
            "X - tratamento: toda operação realizada com dados pessoais, como as que se referem "
            "a coleta, produção, recepção, classificação, utilização, acesso, reprodução, "
            "transmissão, distribuição, processamento, arquivamento, armazenamento, eliminação, "
            "avaliação ou controle da informação, modificação, comunicação, transferência, difusão "
            "ou extração;\n"
            "XI - anonimização: utilização de meios técnicos razoáveis e disponíveis no momento "
            "do tratamento, por meio dos quais um dado perde a possibilidade de associação, "
            "direta ou indireta, a um indivíduo;\n"
            "XII - consentimento: manifestação livre, informada e inequívoca pela qual o titular "
            "concorda com o tratamento de seus dados pessoais para uma finalidade determinada;\n"
            "XIII - bloqueio: suspensão temporária de qualquer operação de tratamento;\n"
            "XIV - eliminação: exclusão de dado ou de conjunto de dados armazenados em banco "
            "de dados;\n"
            "XV - transferência internacional de dados: transferência de dados pessoais para "
            "país estrangeiro ou organismo internacional do qual o país seja membro;\n"
            "XVI - uso compartilhado de dados: comunicação, difusão, transferência internacional, "
            "interconexão de dados pessoais ou tratamento compartilhado de bancos de dados "
            "pessoais por órgãos e entidades públicos;\n"
            "XVII - relatório de impacto à proteção de dados pessoais: documentação do "
            "controlador que contém a descrição dos processos de tratamento de dados pessoais "
            "que podem gerar riscos às liberdades civis e aos direitos fundamentais;\n"
            "XVIII - órgão de pesquisa: órgão ou entidade da administração pública direta ou "
            "indireta ou pessoa jurídica de direito privado sem fins lucrativos;\n"
            "XIX - autoridade nacional: órgão da administração pública responsável por zelar, "
            "implementar e fiscalizar o cumprimento desta Lei em todo o território nacional."
        ),
    },
    {
        "article_number": "Art. 7",
        "title": "Bases Legais para o Tratamento de Dados Pessoais",
        "content": (
            "Art. 7º O tratamento de dados pessoais somente poderá ser realizado nas seguintes "
            "hipóteses:\n\n"
            "I - mediante o fornecimento de consentimento pelo titular;\n"
            "II - para o cumprimento de obrigação legal ou regulatória pelo controlador;\n"
            "III - pela administração pública, para o tratamento e uso compartilhado de dados "
            "necessários à execução de políticas públicas;\n"
            "IV - para a realização de estudos por órgão de pesquisa, garantida, sempre que "
            "possível, a anonimização dos dados pessoais;\n"
            "V - quando necessário para a execução de contrato ou de procedimentos preliminares "
            "relacionados a contrato do qual seja parte o titular, a pedido do titular dos dados;\n"
            "VI - para o exercício regular de direitos em processo judicial, administrativo ou "
            "arbitral;\n"
            "VII - para a proteção da vida ou da incolumidade física do titular ou de terceiro;\n"
            "VIII - para a tutela da saúde, exclusivamente, em procedimento realizado por "
            "profissionais de saúde, serviços de saúde ou autoridade sanitária;\n"
            "IX - quando necessário para atender aos interesses legítimos do controlador ou de "
            "terceiro, exceto no caso de prevalecerem direitos e liberdades fundamentais do "
            "titular que exijam a proteção dos dados pessoais; ou\n"
            "X - para a proteção do crédito, inclusive quanto ao disposto na legislação pertinente."
        ),
    },
    {
        "article_number": "Art. 18",
        "title": "Direitos do Titular dos Dados",
        "content": (
            "Art. 18. O titular dos dados pessoais tem direito a obter do controlador, em "
            "relação aos dados do titular por ele tratados, a qualquer momento e mediante "
            "requisição:\n\n"
            "I - confirmação da existência de tratamento;\n"
            "II - acesso aos dados;\n"
            "III - correção de dados incompletos, inexatos ou desatualizados;\n"
            "IV - anonimização, bloqueio ou eliminação de dados desnecessários, excessivos ou "
            "tratados em desconformidade com o disposto nesta Lei;\n"
            "V - portabilidade dos dados a outro fornecedor de serviço ou produto, mediante "
            "requisição expressa, de acordo com a regulamentação da autoridade nacional;\n"
            "VI - eliminação dos dados pessoais tratados com o consentimento do titular, exceto "
            "nas hipóteses previstas no art. 16 desta Lei;\n"
            "VII - informação das entidades públicas e privadas com as quais o controlador "
            "realizou uso compartilhado de dados;\n"
            "VIII - informação sobre a possibilidade de não fornecer consentimento e sobre as "
            "consequências da negativa;\n"
            "IX - revogação do consentimento, nos termos do § 5º do art. 8º desta Lei.\n\n"
            "§ 1º O titular dos dados pessoais tem o direito de peticionar em relação aos seus "
            "dados contra o controlador perante a autoridade nacional.\n\n"
            "§ 2º O titular pode opor-se a tratamento realizado com fundamento em uma das "
            "hipóteses de dispensa de consentimento, em caso de descumprimento ao disposto "
            "nesta Lei."
        ),
    },
    {
        "article_number": "Art. 46",
        "title": "Segurança e Sigilo dos Dados",
        "content": (
            "Art. 46. Os agentes de tratamento devem adotar medidas de segurança, técnicas e "
            "administrativas aptas a proteger os dados pessoais de acessos não autorizados e de "
            "situações acidentais ou ilícitas de destruição, perda, alteração, comunicação ou "
            "qualquer forma de tratamento inadequado ou ilícito.\n\n"
            "§ 1º A autoridade nacional poderá dispor sobre padrões técnicos mínimos para "
            "tornar aplicável o disposto no caput deste artigo, considerados a natureza das "
            "informações tratadas, as características específicas do tratamento e o estado atual "
            "da tecnologia, especialmente no caso de dados pessoais sensíveis, assim como os "
            "princípios previstos no caput do art. 6º desta Lei.\n\n"
            "§ 2º As medidas de que trata o caput deste artigo deverão ser observadas desde a "
            "fase de concepção do produto ou do serviço até a sua execução."
        ),
    },
    {
        "article_number": "Art. 48",
        "title": "Comunicação de Incidentes de Segurança",
        "content": (
            "Art. 48. O controlador deverá comunicar à autoridade nacional e ao titular a "
            "ocorrência de incidente de segurança que possa acarretar risco ou dano relevante "
            "aos titulares.\n\n"
            "§ 1º A comunicação será feita em prazo razoável, conforme definido pela autoridade "
            "nacional, e deverá mencionar, no mínimo:\n"
            "I - a descrição da natureza dos dados pessoais afetados;\n"
            "II - as informações sobre os titulares envolvidos;\n"
            "III - a indicação das medidas técnicas e de segurança utilizadas para a proteção "
            "dos dados, observados os segredos comercial e industrial;\n"
            "IV - os riscos relacionados ao incidente;\n"
            "V - os motivos da demora, no caso de a comunicação não ter sido imediata; e\n"
            "VI - as medidas que foram ou que serão adotadas para reverter ou mitigar os "
            "efeitos do prejuízo.\n\n"
            "§ 2º A autoridade nacional verificará a gravidade do incidente e poderá, caso "
            "necessário para a salvaguarda dos direitos dos titulares, determinar ao controlador "
            "a adoção de providências, tais como:\n"
            "I - ampla divulgação do fato em meios de comunicação; e\n"
            "II - medidas para reverter ou mitigar os efeitos do incidente.\n\n"
            "§ 3º No juízo de gravidade do incidente, será avaliada eventual comprovação de "
            "que foram adotadas medidas técnicas adequadas que tornem os dados pessoais "
            "afetados ininteligíveis, no âmbito e nos limites técnicos de seus serviços, para "
            "terceiros não autorizados a acessá-los."
        ),
    },
    {
        "article_number": "Art. 52",
        "title": "Sanções Administrativas",
        "content": (
            "Art. 52. Os agentes de tratamento de dados, em razão das infrações cometidas às "
            "normas previstas nesta Lei, ficam sujeitos às seguintes sanções administrativas "
            "aplicáveis pela autoridade nacional:\n\n"
            "I - advertência, com indicação de prazo para adoção de medidas corretivas;\n"
            "II - multa simples, de até 2% (dois por cento) do faturamento da pessoa jurídica "
            "de direito privado, grupo ou conglomerado no Brasil no seu último exercício, "
            "excluídos os tributos, limitada, no total, a R$ 50.000.000,00 (cinquenta milhões "
            "de reais) por infração;\n"
            "III - multa diária, observado o limite total a que se refere o inciso II;\n"
            "IV - publicização da infração após devidamente apurada e confirmada a sua "
            "ocorrência;\n"
            "V - bloqueio dos dados pessoais a que se refere a infração até a sua regularização;\n"
            "VI - eliminação dos dados pessoais a que se refere a infração;\n"
            "X - suspensão parcial do funcionamento do banco de dados a que se refere a "
            "infração pelo período máximo de 6 (seis) meses, prorrogável por igual período, "
            "até a regularização da atividade de tratamento pelo controlador;\n"
            "XI - suspensão do exercício da atividade de tratamento dos dados pessoais a que "
            "se refere a infração pelo período máximo de 6 (seis) meses, prorrogável por "
            "igual período;\n"
            "XII - proibição parcial ou total do exercício de atividades relacionadas a "
            "tratamento de dados.\n\n"
            "§ 1º As sanções serão aplicadas após procedimento administrativo que possibilite "
            "a oportunidade da ampla defesa, de forma gradativa, isolada ou cumulativa, de "
            "acordo com as peculiaridades do caso concreto e considerados os seguintes "
            "parâmetros e critérios:\n"
            "I - a gravidade e a natureza das infrações e dos direitos pessoais afetados;\n"
            "II - a boa-fé do infrator;\n"
            "III - a vantagem auferida ou pretendida pelo infrator;\n"
            "IV - a condição econômica do infrator;\n"
            "V - a reincidência;\n"
            "VI - o grau do dano;\n"
            "VII - a cooperação do infrator;\n"
            "VIII - a adoção reiterada e demonstrada de mecanismos e procedimentos internos "
            "capazes de minimizar o dano;\n"
            "IX - a adoção de política de boas práticas e governança;\n"
            "X - a pronta adoção de medidas corretivas; e\n"
            "XI - a proporcionalidade entre a gravidade da falta e a intensidade da sanção."
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


def seed_lgpd_articles(engine):
    """
    Seed key LGPD articles into legal_documents table.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in LGPD_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'LGPD - Lei 13.709/2018'"
                ),
                {"title": f"LGPD {article['article_number']} - {article['title']}"},
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
                    "title": f"LGPD {article['article_number']} - {article['title']}",
                    "source": "LGPD - Lei 13.709/2018",
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
                      AND ld.source = 'LGPD - Lei 13.709/2018'
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
    print("🏛️  LGPD Seed Script")
    print("   Artigos: 1, 2, 5, 7, 18, 46, 48, 52")
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
    print("📝 Inserindo artigos da LGPD...\n")
    success = seed_lgpd_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed LGPD concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()