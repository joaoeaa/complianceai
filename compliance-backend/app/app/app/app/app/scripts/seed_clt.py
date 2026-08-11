"""
Step 11: Seed CLT Data
Standalone script with key CLT articles (Arts. 2, 3, 4-A, 58, 59, 62, 71, 130, 442, 443, 444, 457, 468, 477, 611-A).
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_clt
    # or
    python app/scripts/seed_clt.py
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


# ── CLT Articles Data ──────────────────────────────────────────────────────

CLT_ARTICLES = [
    {
        "article_number": "Art. 2",
        "title": "Conceito de Empregador",
        "content": (
            "Art. 2º Considera-se empregador a empresa, individual ou coletiva, que, "
            "assumindo os riscos da atividade econômica, admite, assalaria e dirige a prestação "
            "pessoal de serviço.\n\n"
            "§ 1º Equipara-se ao empregador, para os efeitos exclusivos da relação de emprego, "
            "a profissional ou instituição sem fins lucrativos que se dedique à educação, "
            "assistência social ou hospital de caridade.\n\n"
            "§ 2º Sempre que uma ou mais empresas, tendo, embora, cada uma delas, "
            "personalidade jurídica própria, estiverem sob a direção, controle ou administração "
            "de outra, constituindo grupo industrial, comercial ou de qualquer outra atividade "
            "econômica, serão, para os efeitos da relação de emprego, solidariamente responsáveis "
            "a empresa principal e as subordinadas."
        ),
    },
    {
        "article_number": "Art. 3",
        "title": "Conceito de Empregado (Vínculo Empregatício)",
        "content": (
            "Art. 3º Considera-se empregado toda pessoa física que prestar serviços de natureza "
            "não eventual a empregador, sob a dependência deste e mediante salário.\n\n"
            "§ 1º Não haverá distinções relativas à espécie de emprego e à condição de trabalhador, "
            "nem entre o trabalho intelectual, técnico e manual.\n\n"
            "§ 2º (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "§ 3º (Revogado pela Lei nº 13.467, de 2017)"
        ),
    },
    {
        "article_number": "Art. 4-A",
        "title": "Prestação de Serviços a Terceiros (Terceirização)",
        "content": (
            "Art. 4º-A Considera-se como de terceiros a prestação de serviços em que o trabalhador, "
            "com ou sem exclusividade, serve ao tomador do serviço, sob a gestão, organização e "
            "controle de outra empresa, sendo as atividades-meio ou -fim exploradas por pessoa "
            "jurídica de direito privado.\n\n"
            "Parágrafo único. A contratação de trabalhadores por empresa prestadora de serviço "
            "a terceiros é lícita quando não viola nenhuma disposição de proteção ao trabalhador "
            "insculpida nesta Consolidação.\n\n"
            "Lei nº 13.429/2017 - Lei que regulamenta o trabalho temporário e a terceirização."
        ),
    },
    {
        "article_number": "Art. 58",
        "title": "Jornada de Trabalho",
        "content": (
            "Art. 58. A duração normal do trabalho, para os empregados em qualquer atividade "
            "privada, não excederá de 8 (oito) horas diárias e 44 (quarenta e quatro) horas "
            "semanais, observados os limites máximos de oito horas diárias e quarenta e quatro "
            "horas semanais.\n\n"
            "§ 1º A duração normal do trabalho dos empregados em qualquer atividade será de oito "
            "horas diárias e quarenta e quatro horas semanais, observados os limites máximos acima "
            "estipulados.\n\n"
            "§ 2º Poderão ser acordadas ou contratuadas horas de trabalho no período noturno, "
            "observado o disposto neste artigo e ressalvadas as atividades para as quais a lei "
            "fixa expressamente a duração do trabalho.\n\n"
            "§ 3º (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "§ 4º (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "§ 5º A duração normal do trabalho realizado por empregado em regime de tempo parcial "
            "poderá ser de até trinta horas semanais."
        ),
    },
    {
        "article_number": "Art. 59",
        "title": "Horas Extras",
        "content": (
            "Art. 59. A duração normal do trabalho poderá ser acrescida de horas extras, em número "
            "não excedente de 2 (duas), mediante acordo escrito entre empregador e empregado, ou "
            "contrato coletivo de trabalho.\n\n"
            "§ 1º Do acordo ou do contrato coletivo deverá constar, expressamente, o valor da hora "
            "extra, que será, pelo menos, 50% (cinquenta por cento) superior ao da hora normal.\n\n"
            "§ 2º Poderá ser dispensado o acréscimo de salário se, por força de acordo ou convenção "
            "coletiva de trabalho, o excesso de horas em um dia for compensado pela correspondente "
            "diminuição em outro dia, semana ou mês, de modo que não exceda a duração normal da "
            "jornada semanal, mensal ou anual.\n\n"
            "§ 3º Na hipótese de compensação, deverá ser respeitado o intervalo mínimo de onze "
            "horas entre o término de um dia de trabalho e o início do dia seguinte.\n\n"
            "§ 4º (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "§ 5º O banco de horas será considerado como um mecanismo de compensação de jornada "
            "e deverá estar previsto em acordo individual, convenção coletiva ou acordo coletivo "
            "de trabalho.\n\n"
            "§ 6º (Revogado pela Lei nº 13.467, de 2017)"
        ),
    },
    {
        "article_number": "Art. 62",
        "title": "Exclusões do Controle de Jornada",
        "content": (
            "Art. 62. Não são abrangidos pelo regime previsto neste capítulo:\n\n"
            "I - os empregados que exercem atividade externa incompatível com a fixação de horário "
            "de trabalho, devendo tal condição ser anotada na Carteira de Trabalho e Previdência "
            "Social e na folha de pagamento;\n\n"
            "II - os gerentes, assim considerados os ocupantes de cargo de confiança em que "
            "haja predominância de trabalho intelectual, não caracterizando trabalho manual. "
            "(Redação dada pela Lei nº 13.467, de 2017)\n\n"
            "III - os diretores e chefes de departamento ou filial. (Incluído pela Lei nº 13.467, "
            "de 2017)\n\n"
            "IV - os empregados em regime de teletrabalho. (Incluído pela Lei nº 13.467, de 2017)\n\n"
            "Parágrafo único. O trabalho externo e o regime de teletrabalho dependem de anotação "
            "expressa em anotação na Carteira de Trabalho e Previdência Social e no contrato "
            "individual de trabalho, especificando as atividades que serão por ele executadas. "
            "(Incluído pela Lei nº 13.467, de 2017)"
        ),
    },
    {
        "article_number": "Art. 71",
        "title": "Intervalo para Repouso e Alimentação",
        "content": (
            "Art. 71. Em qualquer trabalho contínuo, cuja duração exceda de 6 (seis) horas, é obrigatório "
            "um intervalo de no mínimo 1 (uma) hora e no máximo 2 (duas) horas para repouso ou alimentação, "
            "conforme dispuser o regulamento ou contrato coletivo de trabalho.\n\n"
            "§ 1º Este intervalo não será computado na duração do trabalho.\n\n"
            "§ 2º Os horários de início e término desse intervalo serão fixados por acordo coletivo ou "
            "contrato individual, respeitado o limite legal.\n\n"
            "§ 3º Se o trabalho for realizado em turnos contínuos, poderão ser atribuídos horários "
            "diferenciados para o intervalo de repouso ou alimentação, desde que isso não prejudique "
            "a saúde do trabalhador.\n\n"
            "§ 4º Quando a natureza do trabalho exigir que o trabalhador permaneça no estabelecimento "
            "durante o intervalo, o tempo correspondente será remunerado como tempo de efetivo trabalho."
        ),
    },
    {
        "article_number": "Art. 130",
        "title": "Férias",
        "content": (
            "Art. 130. Os empregados farão jus a férias, sem prejuízo da remuneração que lhes é devida.\n\n"
            "§ 1º A duração das férias será determinada de acordo com o regulamento ou contrato coletivo "
            "de trabalho e não será inferior a trinta dias.\n\n"
            "§ 2º As férias devem ser proporcionais ao tempo de serviço prestado durante o ano.\n\n"
            "§ 3º As férias serão pagas e gozadas conforme acordado entre empregado e empregador, "
            "podendo a primeira metade ser usufruída em conjunto, e a segunda metade em até um ano "
            "após o término da primeira metade.\n\n"
            "§ 4º O fracionamento de férias além do previsto neste artigo dependerá de acordos "
            "individuais ou coletivos.\n\n"
            "§ 5º (Incluído pela Lei nº 13.467, de 2017) As férias poderão ser usufruídas em até "
            "três períodos, sendo que um deles não poderá ser inferior a quatorze dias corridos, "
            "e os demais não poderão ser inferiores a cinco dias corridos, cada um, quando assim "
            "acordar entre empregador e empregado.\n\n"
            "§ 6º (Incluído pela Lei nº 13.467, de 2017) Até cinco dias do período de férias poderão "
            "ser convertidos em abono pecuniário, mediante acordo entre empregador e empregado."
        ),
    },
    {
        "article_number": "Art. 442",
        "title": "Contrato Individual de Trabalho",
        "content": (
            "Art. 442. O contrato individual de trabalho poderá ser acordado tácita ou expressamente, "
            "verbalmente ou por escrito, por prazo determinado ou indeterminado, ou para obra certa.\n\n"
            "Parágrafo único. (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "Observação: O contrato de trabalho é o acordo entre empregador e empregado, estabelecendo "
            "as condições sob as quais o serviço será prestado, incluindo remuneração, jornada, "
            "responsabilidades e outros direitos e deveres."
        ),
    },
    {
        "article_number": "Art. 443",
        "title": "Contrato por Prazo Determinado/Indeterminado",
        "content": (
            "Art. 443. O contrato individual de trabalho poderá ser acordado tácita ou expressamente, "
            "verbalmente ou por escrito, por prazo determinado ou indeterminado, ou para obra certa.\n\n"
            "§ 1º O contrato por prazo determinado somente será válido em se tratando:\n"
            "a) de serviço cuja natureza ou transitoriedade justifique a predeterminação do término;\n"
            "b) de atividades empresariais de caráter transitório;\n"
            "c) de contrato de experiência.\n\n"
            "§ 2º O contrato de experiência não poderá exceder de 90 (noventa) dias.\n\n"
            "§ 3º (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "§ 4º O contrato por prazo indeterminado é aquele em que não se estabelece termo para "
            "o seu encerramento, salvo por rescisão justificada ou sem justa causa."
        ),
    },
    {
        "article_number": "Art. 444",
        "title": "Livre Estipulação (Autonomia Negocial)",
        "content": (
            "Art. 444. As relações contratuais de trabalho reguladas nesta Consolidação são baseadas "
            "no consenso, salvo disposições de proteção ao trabalhador previstas em lei.\n\n"
            "Caput reformado pela Lei nº 13.467, de 2017:\n"
            "Art. 444. Os direitos e obrigações emergentes do contrato de trabalho que vigoram na "
            "empresa coincidem com os direitos e obrigações do trabalhador perante a empresa, assim "
            "definindo as respectivas compensações e condições de trabalho.\n\n"
            "Parágrafo único. (Incluído pela Lei nº 13.467, de 2017) Nada impede que as partes "
            "acordem livremente quanto às condições do contrato de trabalho, desde que não contrariem "
            "as disposições de proteção ao trabalhador previstas em lei.\n\n"
            "Observação: A autonomia contratual permite flexibilidade nas negociações, respeitando "
            "o piso mínimo de direitos trabalhistas garantidos pela lei."
        ),
    },
    {
        "article_number": "Art. 457",
        "title": "Remuneração",
        "content": (
            "Art. 457. Na fixação da remuneração, a empresa considerará, para efeito de maior proteção "
            "ao trabalhador, a importância fixa estipulada, as gratificações, diárias, percentagens, "
            "comissões, prêmios e outras parcelas constantes de acordo coletivo ou convenção coletiva "
            "de trabalho.\n\n"
            "§ 1º Integram o salário não só a importância fixa estipulada, como também as comissões, "
            "percentagens, gratificações, diárias, abonos padrão, prêmios e outras parcelas "
            "frequentemente pagas ao empregado.\n\n"
            "§ 2º Não se incluem nos salários as ajudas de custo, nem as diárias para viagem, "
            "nem adiantamentos, nem abonos para faltas, nem prêmios ou gratificações ocasionais.\n\n"
            "§ 3º (Incluído pela Lei nº 13.467, de 2017) O direito do trabalho não admitirá "
            "importância fixa inferior ao salário mínimo legal ou normativo da categoria profissional."
        ),
    },
    {
        "article_number": "Art. 468",
        "title": "Alteração do Contrato de Trabalho",
        "content": (
            "Art. 468. Nos contratos individuais de trabalho só é lícito alterar situações pelo "
            "consentimento das duas partes, quando não acarretarem, direta ou indiretamente, "
            "diminuição da remuneração ou dos direitos do trabalhador.\n\n"
            "§ 1º Não se considera diminuição de direitos a eliminação, de comum acordo, de alguns "
            "dos favores pessoais ou regalias conquanto a compensação em importância não seja "
            "afastada.\n\n"
            "Parágrafo único: (Incluído pela Lei nº 13.467, de 2017) O consenso das partes para "
            "alteração do contrato individual de trabalho poderá ser revisto a qualquer tempo pela "
            "autoridade administrativa ou judiciária competente, desde que provado que ocasionou "
            "prejuízo ao trabalhador ou ao empregador."
        ),
    },
    {
        "article_number": "Art. 477",
        "title": "Rescisão do Contrato de Trabalho",
        "content": (
            "Art. 477. É assegurado ao empregado que for despedido, sem justa causa, o direito de "
            "receber, na época do aviso prévio, a indenização a que tiver direito.\n\n"
            "§ 1º (Revogado pela Lei nº 13.467, de 2017)\n\n"
            "§ 2º Na despedida sem justa causa, o empregador pagará ao empregado uma indenização "
            "equivalente ao valor de um mês de salário, na forma e condições estabelecidas nesta "
            "Consolidação.\n\n"
            "§ 3º Nas rescisões de contrato de trabalho, deverão constar da respectiva notificação, "
            "quando aplicável:\n"
            "I - aviso prévio, verbal ou escrito;\n"
            "II - a data do término do contrato;\n"
            "III - a causa ou motivo da rescisão;\n"
            "IV - o valor das verbas rescisórias devidas.\n\n"
            "§ 4º (Incluído pela Lei nº 13.467, de 2017) Na rescisão contratual, independente da "
            "forma, havendo saldo de salário não pago, férias não gozadas ou proporcionais, décimo "
            "terceiro salário proporcional, além de outras verbas rescisórias, estas deverão ser "
            "pagas conforme acordado ou estabelecido em lei.\n\n"
            "§ 6º (Incluído pela Lei nº 13.467, de 2017) O instrumento de rescisão será obrigatoriamente "
            "assinado por ambas as partes."
        ),
    },
    {
        "article_number": "Art. 611-A",
        "title": "Prevalência de Acordo/Convenção Coletiva",
        "content": (
            "Art. 611-A. A convenção coletiva e o acordo coletivo de trabalho têm prevalência sobre "
            "a lei quando, entre outras disposições, versarem sobre:\n\n"
            "I - pacto quanto à jornada de trabalho, observados os limites legais;\n"
            "II - banco de horas anual;\n"
            "III - intervalo intrajornada, respeitado o limite mínimo de trinta minutos para "
            "jornadas superiores a seis horas;\n"
            "IV - modalidade de registro de jornada de trabalho;\n"
            "V - teletrabalho, regime de sobreaviso, e trabalho intermitente;\n"
            "VI - enquadramento do grau de insalubridade;\n"
            "VII - prorrogação de jornada em atividades insalubres, respeitados os limites legais "
            "e a revisão das condições que ensejam a insalubridade;\n"
            "VIII - antecipação e fruição de férias fracionadas;\n"
            "IX - abono pecuniário da licença-maternidade nos termos da lei;\n"
            "X - prêmios de produtividade, assiduidade, pontualidade e outros incentivos em espécie "
            "que substituam ou se façam cumulativos com os registrados em lei;\n"
            "XI - participação nos lucros ou resultados da empresa.\n\n"
            "§ 1º No exame da convenção coletiva ou acordo coletivo de trabalho, a Justiça do Trabalho "
            "observará o disposto no art. 8º da Constituição Federal, sendo vedada a substituição da "
            "negociação coletiva pela sentença normativa, respeitado o disposto no art. 614 desta "
            "Consolidação.\n\n"
            "§ 2º Regras sobre duração do trabalho e intervalos não são passíveis de negociação coletiva "
            "se isso resultar em prejuízo à saúde do trabalhador.\n\n"
            "§ 3º Na negociação coletiva de trabalho, a condição mais benéfica ao trabalhador prevista "
            "em lei ou em norma coletiva prevalece sobre o acordo individual, salvo disposição em contrário "
            "na convenção ou acordo coletivo de trabalho."
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


def seed_clt_articles(engine):
    """
    Seed key CLT articles into legal_documents table.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in CLT_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'CLT - Decreto-Lei 5.452/1943'"
                ),
                {"title": f"CLT {article['article_number']} - {article['title']}"},
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
                    "title": f"CLT {article['article_number']} - {article['title']}",
                    "source": "CLT - Decreto-Lei 5.452/1943",
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
                      AND ld.source = 'CLT - Decreto-Lei 5.452/1943'
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
    print("🏛️  CLT Seed Script")
    print("   Artigos: 2, 3, 4-A, 58, 59, 62, 71, 130, 442, 443, 444, 457, 468, 477, 611-A")
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
    print("📝 Inserindo artigos da CLT...\n")
    success = seed_clt_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed CLT concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()
