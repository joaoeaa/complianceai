"""
Step 12: Seed Marco Civil da Internet Data
Standalone script with key articles from Lei 12.965/2014 (Arts. 3, 7, 8, 9, 10, 11, 12, 13, 15, 18, 19, 21).
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_marco_civil
    # or
    python app/scripts/seed_marco_civil.py
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


# ── Marco Civil Articles Data ──────────────────────────────────────────────────

MARCO_CIVIL_ARTICLES = [
    {
        "article_number": "Art. 3",
        "title": "Princípios - Disciplina do Uso da Internet",
        "content": (
            "Art. 3º A disciplina do uso da internet no Brasil tem como fundamentos o respeito "
            "à liberdade de expressão, à privacidade, à segurança do usuário e ao desenvolvimento "
            "tecnológico e econômico do país.\n\n"
            "Parágrafo único. Na aplicação das normas desta Lei, serão levados em conta, além dos "
            "fundamentos, os seguintes princípios:\n"
            "I - garantia da liberdade de expressão, comunicação e manifestação de pensamento, nos "
            "termos da Constituição Federal;\n"
            "II - proteção da privacidade;\n"
            "III - proteção dos dados pessoais, na forma da lei;\n"
            "IV - preservação e garantia da neutralidade de rede;\n"
            "V - preservação da estabilidade, segurança e funcionalidade da rede;\n"
            "VI - responsabilização dos agentes de acordo com suas atividades, nos termos da lei;\n"
            "VII - preservação, em caráter permanente, de registros de conexão e de acesso a "
            "aplicações de internet, sob sigilo, na forma da lei;\n"
            "VIII - computação em ambiente de nuvem dentro do território nacional, nos termos "
            "regulamentados pelo Poder Executivo;\n"
            "IX - respeito à liberdade contratual entre os usuários de internet e os provedores "
            "de conexão e de aplicações."
        ),
    },
    {
        "article_number": "Art. 7",
        "title": "Direitos dos Usuários na Internet",
        "content": (
            "Art. 7º O acesso à internet é essencial para o exercício da cidadania, e ao usuário "
            "são assegurados, conforme este Marco Civil, os seguintes direitos:\n\n"
            "I - inviolabilidade da intimidade e da vida privada, sua proteção e indenização pelo "
            "dano material ou moral decorrente de sua violação;\n"
            "II - inviolabilidade e sigilo do fluxo de suas comunicações pela internet, salvo por "
            "ordem judicial, na forma da lei;\n"
            "III - inviolabilidade e sigilo de suas escolhas de conteúdo, resguardado o direito "
            "de acesso à informação e ao conhecimento coletivo;\n"
            "IV - não fornecimento a terceiros de seus dados pessoais, inclusive registros de "
            "conexão, e de acesso a aplicações de internet, salvo mediante consentimento livre, "
            "expresso e informado ou nas hipóteses previstas em lei;\n"
            "V - informações claras e completas nos contratos de prestação de serviços com "
            "disposições sobre privacidade, segurança de seus dados pessoais, período de guarda, "
            "acesso, alteração e exclusão de informações;\n"
            "VI - não serem submetidos a análises, avaliações ou decisões automatizadas que afetem "
            "seus interesses, que não sejam permitidas pela legislação de proteção de dados pessoais;\n"
            "VII - livre escolha dos programas de computador instalados em seus terminais, conforme "
            "permitido em lei;\n"
            "VIII - não serem discriminados por suas escolhas de conteúdo."
        ),
    },
    {
        "article_number": "Art. 8",
        "title": "Garantia do Direito à Privacidade",
        "content": (
            "Art. 8º A garantia do direito à privacidade na utilização da internet constitui direito "
            "fundamental do usuário, devendo o Estado, os provedores de conexão, os provedores de "
            "aplicações de internet e outros agentes envolvidos na cadeia de transmissão, coleta, "
            "guarda e tratamento de dados pessoais implementar medidas técnicas compatíveis com os "
            "padrões internacionais e legais de segurança.\n\n"
            "§ 1º - O armazenamento de registros de conexão e de acesso a aplicações de internet é "
            "disciplinado nesta Lei. A divulgação ou compartilhamento de dados pessoais do usuário "
            "dependerá de consentimento, ressalvadas as hipóteses previstas em lei.\n\n"
            "§ 2º - A coleta, uso, armazenamento, tratamento, processamento, compartilhamento e "
            "demais operações de dados pessoais devem ser realizados de forma transparente e "
            "segura, em conformidade com a legislação de proteção de dados pessoais.\n\n"
            "§ 3º - As comunicações pela internet, salvo por consentimento livre, expresso e "
            "informado ou ordem judicial, são invioláveis e garantidas sob sigilo."
        ),
    },
    {
        "article_number": "Art. 9",
        "title": "Neutralidade de Rede",
        "content": (
            "Art. 9º O responsável pela transmissão, comutação ou roteamento tem o dever de tratar "
            "de forma isonômica quaisquer pacotes de dados, sem distinção por conteúdo, origem, "
            "destino, serviço, terminal, aplicação, protocolo ou método de encapsulamento.\n\n"
            "§ 1º - Não se considera discriminação ou degradação de tráfego a priorização de serviços "
            "de emergência ou a realização de atividades de administração da rede e da segurança.\n\n"
            "§ 2º - A degradação de tráfego por congestionamento de rede é permitida, desde que "
            "aplicada de forma isonômica a todos os usuários de um mesmo serviço.\n\n"
            "§ 3º - Na provisão de serviço de acesso à internet, é vedado bloquear, monitorar, "
            "filtrar, analisar ou examinar o conteúdo, os pacotes de dados ou as comunicações dos "
            "usuários, ressalvadas as hipóteses previstas na legislação.\n\n"
            "§ 4º - É permitido o gerenciamento de tráfego e a priorização de serviços de interesse "
            "público, devendo a Agência Nacional de Telecomunicações regulamentar o tema."
        ),
    },
    {
        "article_number": "Art. 10",
        "title": "Guarda e Disponibilização de Registros de Conexão",
        "content": (
            "Art. 10. O provedor de conexão à internet é obrigado a guardar os registros de conexão "
            "de seus usuários, sob sigilo, em local seguro, pelo prazo mínimo de seis meses, nos "
            "termos regulamentados pelo Decreto nº 8.771, de 11 de maio de 2016.\n\n"
            "§ 1º - Os registros de conexão devem conter minimamente o endereço IP utilizado para "
            "conexão, data, hora, duração e volume de dados da conexão realizada pelo usuário.\n\n"
            "§ 2º - Os provedores não poderão divulgar esses registros senão em resposta a ordem "
            "judicial ou, nos termos da Lei nº 12.850, de 2 de agosto de 2013, a requisição dos "
            "órgãos enumerados no art. 13 dessa Lei.\n\n"
            "§ 3º - A venda ou cessão de registros de conexão a terceiros viola direitos fundamentais "
            "do usuário e é expressamente proibida.\n\n"
            "§ 4º - A obrigação de guarda de registros é sem prejuízo da possibilidade de guarda "
            "adicional de registros por decisão judicial, para fins de investigação criminal."
        ),
    },
    {
        "article_number": "Art. 11",
        "title": "Tratamento de Dados de Conexão e Aplicação",
        "content": (
            "Art. 11. O provedor de aplicações de internet será responsável pelo armazenamento dos "
            "registros de acesso a aplicações de internet, sob sigilo, em ambiente controlado e de "
            "segurança equivalente àquelas empregadas para o armazenamento dos próprios dados "
            "pessoais do usuário.\n\n"
            "§ 1º - Esse armazenamento deverá seguir os padrões técnicos e de segurança da legislação "
            "de proteção de dados pessoais, sendo vedada qualquer divulgação, compartilhamento ou "
            "cessão sem consentimento do usuário ou ordem judicial.\n\n"
            "§ 2º - Os registros de acesso a aplicações podem incluir navegação, acesso a conteúdos "
            "e comunicações realizadas pelo usuário.\n\n"
            "§ 3º - O tempo de retenção dos registros será o mínimo necessário para fins de "
            "segurança, identificação ou investigação, conforme determinado em lei e regulamentos.\n\n"
            "§ 4º - A venda, compartilhamento ou cessão de dados de acesso a aplicações de internet "
            "sem consentimento livre, expresso e informado do usuário é vedada."
        ),
    },
    {
        "article_number": "Art. 12",
        "title": "Sanções por Violação da Proteção de Dados",
        "content": (
            "Art. 12. Quem violar direitos relativos à privacidade, proteção de dados pessoais, "
            "garantia de privacidade na internet ou outros previstos nesta Lei fica sujeito às "
            "seguintes sanções administrativas, sem prejuízo de outras sanções cíveis, criminais e "
            "de indenizações por danos morais ou materiais:\n\n"
            "I - advertência com indicação de prazo para adoção de medidas corretivas;\n"
            "II - multa simples de até R$ 10.000.000,00 (dez milhões de reais) por violação;\n"
            "III - multa diária no mesmo valor, enquanto persistir a violação;\n"
            "IV - publicização da infração após devidamente apurada;\n"
            "V - bloqueio dos dados pessoais relacionados à infração até sua regularização;\n"
            "VI - eliminação dos dados pessoais indevidamente armazenados ou tratados;\n"
            "VII - suspensão da atividade de coleta de dados pelo responsável da infração, pelo "
            "período máximo de seis meses."
        ),
    },
    {
        "article_number": "Art. 13",
        "title": "Guarda de Registros de Conexão",
        "content": (
            "Art. 13. Na hipótese do artigo anterior, o provedor de conexão à internet somente "
            "entregará os registros de conexão a: (Vide Lei nº 13.709, de 2018)\n\n"
            "I - autoridades administrativas, no exercício de atribuições legais;\n"
            "II - autoridades policiais, para fins de investigação criminal, por iniciativa própria;\n"
            "III - autoridades judiciárias, por requerimento ou determinação legal;\n"
            "IV - Ministério Público, para fins de investigação de ilícitos penais ou civis.\n\n"
            "§ 1º - Para os fins do inciso II deste artigo, a autoridade policial poderá requerer "
            "ao provedor a conservação de registros já existentes ou futuros, pelo prazo máximo de "
            "sessenta dias, quando há indícios de prática de crime.\n\n"
            "§ 2º - A requisição de registros de conexão por autoridades policial ou ministério "
            "público deverá ser acompanhada de fundamentação sobre a existência de indícios de "
            "prática de crime, a fim de preservar direitos fundamentais.\n\n"
            "§ 3º - Os provedores, ao disponibilizarem os registros, deverão observar direitos dos "
            "usuários quanto à privacidade e sigilo de suas comunicações."
        ),
    },
    {
        "article_number": "Art. 15",
        "title": "Guarda de Registros de Acesso a Aplicações",
        "content": (
            "Art. 15. O provedor de aplicações de internet somente disponibilizará registros de "
            "acesso a aplicações de internet mediante ordem judicial, nas hipóteses e sob as "
            "condições previstas nesta Lei e na legislação de proteção de dados pessoais.\n\n"
            "§ 1º - A ordem judicial deve ser específica e fundamentada, indicando claramente quais "
            "registros são solicitados, em qual período temporal e para qual finalidade.\n\n"
            "§ 2º - Os provedores de aplicações devem manter os registros sob sigilo absoluto, "
            "em ambiente de segurança equivalente ao utilizado para proteção de dados pessoais.\n\n"
            "§ 3º - A divulgação de registros de acesso a aplicações sem ordem judicial constitui "
            "violação de direitos fundamentais do usuário.\n\n"
            "§ 4º - Os registros de acesso a aplicações também podem ser entregues ao Ministério "
            "Público ou autoridades policiais, mediante decisão judicial ou em casos de crime "
            "flagrante, observadas as mesmas proteções de privacidade."
        ),
    },
    {
        "article_number": "Art. 18",
        "title": "Responsabilidade por Conteúdo de Terceiros",
        "content": (
            "Art. 18. O provedor de aplicações de internet não será responsabilizado civilmente por "
            "danos decorrentes de conteúdo gerado por terceiros, exceto nos casos em que:\n\n"
            "I - a vítima requerer ao provedor, por notificação extrajudicial ou judicial, que remova "
            "ou bloqueie o conteúdo apontado como ofensivo, e o provedor, após notificação, deixar "
            "de agir no prazo de vinte e quatro horas, nos termos da legislação de proteção de dados "
            "pessoais;\n"
            "II - o provedor tiver ciência inequívoca de que o conteúdo viola lei, norma ou direito "
            "fundamental e deixar de agir, quando a remoção puder ser feita de forma segura e "
            "eficiente;\n"
            "III - o provedor, mediante instrumentos automatizados ou não, violar direitos "
            "fundamentais do usuário, como privacidade ou liberdade de expressão.\n\n"
            "§ 1º - A notificação deverá conter informações suficientes para identificação do "
            "conteúdo apontado como ofensivo e seus localizadores (URLs), bem como justificativa "
            "sucinta da alegada ofensa.\n\n"
            "§ 2º - Ficam isentos de responsabilidade o provedor que atua de boa-fé na remoção ou "
            "bloqueio de conteúdo, mesmo que equivocadamente."
        ),
    },
    {
        "article_number": "Art. 19",
        "title": "Responsabilidade por Danos - Ordem Judicial",
        "content": (
            "Art. 19. Com o intuito de assegurar a liberdade de expressão e impedir a censura, o "
            "provedor de aplicações de internet somente poderá ser responsabilizado civilmente por "
            "danos decorrentes de conteúdo gerado por terceiros se, após ordem judicial específica, "
            "não tiver removido ou desabilitado o acesso ao conteúdo apontado pela vítima como "
            "ofensivo no prazo de vinte e quatro horas.\n\n"
            "§ 1º - A ordem judicial deve ser proferida por juiz competente ou tribunal, que "
            "determine especificamente qual conteúdo deve ser removido, bloqueado ou desabilitado, "
            "sob pena de responsabilidade do provedor.\n\n"
            "§ 2º - A ordem judicial deve conter fundamentação clara sobre a ofensa alegada, "
            "indicando qual direito foi violado e qual é a medida cabível.\n\n"
            "§ 3º - A remoção ou bloqueio do conteúdo não prejudica outros direitos do usuário, como "
            "direito de defesa ou de recurso, conforme a legislação processual civil.\n\n"
            "§ 4º - Após a remoção, o provedor deverá informar ao usuário responsável pelo conteúdo "
            "sobre a ordem judicial e oportunidade de defesa."
        ),
    },
    {
        "article_number": "Art. 21",
        "title": "Proteção do Conteúdo Íntimo - Revenge Porn",
        "content": (
            "Art. 21. A divulgação de fotografia, vídeo ou áudio contendo cena de nudez ou ato sexual "
            "de conteúdo íntimo de menor de dezoito anos é crime inafiançável, nos termos da legislação "
            "penal pertinente.\n\n"
            "§ 1º - As plataformas digitais e provedores de aplicações devem implementar mecanismos "
            "técnicos de detecção, bloqueio e remoção de conteúdo que viole essa disposição, em "
            "conformidade com a legislação de proteção de dados pessoais e direitos fundamentais.\n\n"
            "§ 2º - A divulgação, sem consentimento, de imagem ou vídeo contendo cena de nudez ou "
            "ato sexual de conteúdo íntimo de maior de dezoito anos também é vedada e constitui "
            "ofensa à privacidade e dignidade pessoal, sujeitando o responsável a sanções civis e "
            "criminais.\n\n"
            "§ 3º - Os provedores de aplicações serão responsabilizados civil e administrativamente "
            "caso, ciente de publicação de conteúdo íntimo não consensual, deixem de remover ou "
            "bloquear tal conteúdo no prazo de vinte e quatro horas.\n\n"
            "§ 4º - A vítima de divulgação não consensual de conteúdo íntimo tem direito a indenização "
            "por danos materiais e morais."
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


def seed_marco_civil_articles(engine):
    """
    Seed key Marco Civil da Internet articles into legal_documents table.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in MARCO_CIVIL_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'Marco Civil da Internet - Lei 12.965/2014'"
                ),
                {"title": f"Marco Civil {article['article_number']} - {article['title']}"},
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
                    "title": f"Marco Civil {article['article_number']} - {article['title']}",
                    "source": "Marco Civil da Internet - Lei 12.965/2014",
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
                      AND ld.source = 'Marco Civil da Internet - Lei 12.965/2014'
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
    print("🏛️  Marco Civil da Internet Seed Script")
    print("   Lei 12.965/2014")
    print("   Artigos: 3, 7, 8, 9, 10, 11, 12, 13, 15, 18, 19, 21")
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
    print("📝 Inserindo artigos da Marco Civil da Internet...\n")
    success = seed_marco_civil_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed Marco Civil concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()
