"""
Step 11: Seed CDC Data
Standalone script with key CDC articles (Arts. 6, 12, 14, 18, 20, 26, 30, 31, 35, 39, 46, 47, 49, 51, 54).
Runs with sync engine. Idempotent (checks if already seeded).

Usage:
    python -m app.scripts.seed_cdc
    # or
    python app/scripts/seed_cdc.py
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


# ── CDC Articles Data ───────────────────────────────────────────────────────

CDC_ARTICLES = [
    {
        "article_number": "Art. 6",
        "title": "Direitos Básicos do Consumidor",
        "content": (
            "Art. 6º São direitos básicos do consumidor:\n\n"
            "I - a proteção da vida, saúde e segurança contra riscos causados por práticas no "
            "fornecimento de produtos e serviços considerados perigosos ou nocivos;\n"
            "II - a educação e divulgação sobre o consumo adequado dos produtos e serviços, asseguradas "
            "a liberdade de escolha e a igualdade nas contratações;\n"
            "III - a informação adequada e clara sobre os diferentes produtos e serviços, com "
            "especificação correta de quantidade, características, composição, qualidade, tributos "
            "incidentes e preço, bem como sobre os riscos que apresentam;\n"
            "IV - a proteção contra publicidade enganosa e abusiva, métodos comerciais coercitivos ou "
            "desleais, bem como contra práticas e cláusulas abusivas ou impostas no fornecimento de "
            "produtos e serviços;\n"
            "V - a proteção contratual, com exigência de consentimento expresso do consumidor na "
            "incorporação de cláusulas que modifiquem o substrato essencial do negócio, inclusive "
            "quanto ao preço;\n"
            "VI - a facilitação da defesa de seus direitos, inclusive com a inversão do ônus da prova, "
            "a seu favor, no processo civil, quando a critério do juiz for verossímil a alegação ou "
            "quando for ele hipossuficiente, segundo as regras ordinárias de experiência;\n"
            "VII - o acesso aos órgãos judiciários e administrativos com vistas à prevenção ou reparação "
            "de danos patrimoniais e morais, individual ou coletivamente;\n"
            "VIII - a facilitação da defesa de direitos difusos e coletivos;\n"
            "IX - a adequada e eficaz prestação dos serviços públicos em geral."
        ),
    },
    {
        "article_number": "Art. 12",
        "title": "Responsabilidade pelo Fato do Produto e do Serviço",
        "content": (
            "Art. 12. O fabricante, o produtor, o construtor, nacional ou estrangeiro, e o importador "
            "respondem, independentemente da existência de culpa, pela reparação dos danos causados a "
            "consumidores por defeitos decorrentes de projeto, fabricação, construção, montagem, "
            "fórmulas, manipulação, apresentação ou acondicionamento de seus produtos, bem como por "
            "informações insuficientes ou inadequadas sobre sua utilização e riscos.\n\n"
            "§ 1º O produto é considerado defeituoso quando não oferece a segurança que dele "
            "legitimamente se espera, levando-se em consideração as circunstâncias relevantes, entre "
            "as quais:\n"
            "I - sua apresentação;\n"
            "II - o uso e riscos que razoavelmente dele se esperam;\n"
            "III - o tempo em que foi colocado em circulação.\n\n"
            "§ 2º Não será considerado defeituoso o produto ou serviço que, por força de lei ou norma "
            "técnica oficial, tenha a segurança aumentada após sua colocação no mercado.\n\n"
            "§ 3º O fabricante, o construtor, o produtor ou importador só não será responsabilizado "
            "quando provar:\n"
            "I - que não colocou o produto no mercado;\n"
            "II - que, embora haja colocado o produto no mercado, o defeito não existe;\n"
            "III - que a culpa é exclusiva do consumidor ou de terceiro."
        ),
    },
    {
        "article_number": "Art. 14",
        "title": "Responsabilidade por Defeito na Prestação do Serviço",
        "content": (
            "Art. 14. O fornecedor de serviços responde, independentemente da existência de culpa, pela "
            "reparação dos danos causados aos consumidores por defeitos relativos à prestação dos serviços, "
            "bem como por informações insuficientes ou inadequadas sobre sua fruição e riscos.\n\n"
            "§ 1º O serviço é considerado defeituoso quando não fornece a segurança que o consumidor "
            "dele pode legitimamente esperar, levando-se em consideração as circunstâncias relevantes, "
            "entre as quais:\n"
            "I - o modo de seu fornecimento;\n"
            "II - o resultado que dele se espera;\n"
            "III - o tempo em que foi fornecido.\n\n"
            "§ 2º O fornecedor de serviços só não será responsabilizado quando provar:\n"
            "I - que, tendo prestado o serviço, o defeito inexiste;\n"
            "II - que a culpa é exclusiva do consumidor ou de terceiro.\n\n"
            "§ 3º O fornecedor de serviço é obrigado a reparar ou completar o serviço sem custo "
            "adicional e sem prejuízo de outras reparações cabíveis.\n\n"
            "§ 4º As disposições deste artigo aplicam-se às atividades de prestação de serviços de "
            "natureza bancária, financeira, de crédito e securitária, operadas por qualquer agente, "
            "posto em funcionamento, não cabendo a exclusão de responsabilidade."
        ),
    },
    {
        "article_number": "Art. 18",
        "title": "Responsabilidade por Vício do Produto",
        "content": (
            "Art. 18. Os fornecedores respondem solidariamente pelos vícios de qualidade ou quantidade "
            "dos produtos e serviços que ofertem ou coloquem no mercado de consumo.\n\n"
            "§ 1º O produto ou serviço é considerado viciado quando:\n"
            "I - se afastar, em qualquer aspecto, do disposto na oferta;\n"
            "II - não corresponder, em qualquer aspecto, com o que foi expressamente oferecido;\n"
            "III - não possuir as qualidades que o consumidor pode legitimamente esperar, em função "
            "de sua natureza e, em especial, em função das afirmações constantes da publicidade ou da "
            "apresentação do produto ou do serviço ao público.\n\n"
            "§ 2º Para os fins deste artigo, equiparam-se aos fornecedores todas as pessoas "
            "identificáveis, quer estejam ou não diretamente envolvidas na produção, montagem, "
            "distribuição ou comercialização do produto ou serviço viciado.\n\n"
            "§ 3º Sendo o vício de qualidade ou quantidade, o consumidor poderá, alternativamente e à "
            "sua escolha:\n"
            "I - exigir do fornecedor, imediatamente, sem prejuízo da indenização por perdas e danos, "
            "devolução do produto com restituição de quantia já paga, monetariamente atualizada, podendo "
            "o consumidor descontar, do valor a ser restituído, os gastos com o uso do produto;\n"
            "II - exigir do fornecedor, imediatamente, sem prejuízo da indenização por perdas e danos, o "
            "abatimento proporcional do preço;\n"
            "III - exigir do fornecedor, imediatamente, o reparo do produto, sem custo adicional ao "
            "consumidor, ressalvado o disposto nos incisos I e II deste parágrafo."
        ),
    },
    {
        "article_number": "Art. 20",
        "title": "Responsabilidade por Vício do Serviço",
        "content": (
            "Art. 20. O fornecedor de serviços que, por qualquer motivo não cumprir ou cumprir "
            "parcialmente a obrigação é obrigado a cumpri-la ou repeti-la, sem custo adicional para o "
            "consumidor, quando cabível, conforme se dispuser em regulamento.\n\n"
            "Parágrafo único. O consumidor poderá desistir do contrato, sem penalidade e sem direito "
            "adquirido ao crédito já despendido, quando referente a serviços prestados ou a serem "
            "prestados de forma contínua ou periódica."
        ),
    },
    {
        "article_number": "Art. 26",
        "title": "Decadência e Prescrição (Prazos de Reclamação)",
        "content": (
            "Art. 26. O direito de reclamar pelos vícios aparentes ou que se manifestem dentro de "
            "trinta dias, tratando-se de fornecimento de serviço e de produtos não duráveis, caducará "
            "em trinta dias, contados a partir de seu término.\n\n"
            "§ 1º Tratando-se de vício oculto, o prazo decadencial será de cento e oitenta dias a partir "
            "da descoberta do defeito ou de quando deveria ter sido descoberto.\n\n"
            "§ 2º Tratando-se de produto durável, o prazo decadencial será de trinta dias para "
            "reclamação pela existência de defeito, independentemente de término ou não do prazo de "
            "garantia legal, contado a partir da entrega do produto, cabendo ao estabelecimento "
            "fornecedor repará-lo ou trocar de imediato, sem ônus para o consumidor, ressalvadas as "
            "dúvidas de ordem técnica em que a prova técnica inerente à dúvida couber ao estabelecimento."
        ),
    },
    {
        "article_number": "Art. 30",
        "title": "Da Oferta (Vinculação)",
        "content": (
            "Art. 30. Toda informação ou publicidade, suficientemente precisa, veiculada por qualquer "
            "forma ou meio de comunicação com relação a produtos e serviços oferecidos ou apresentados, "
            "obriga o fornecedor que a fizer veicular ou dela se utilizar e integra o contrato que vier "
            "a ser celebrado.\n\n"
            "Parágrafo único. Os particulares equiparam-se aos fornecedores para efeitos desta proteção."
        ),
    },
    {
        "article_number": "Art. 31",
        "title": "Informações sobre Produtos e Serviços",
        "content": (
            "Art. 31. A apresentação ou publicidade de produtos ou serviços deve assegurar informações "
            "corretas, claras, precisas, ostensivas e em língua portuguesa sobre suas características, "
            "qualidades, quantidade, composição, preço, garantia, prazos de validade e origem, entre outros "
            "dados, bem como sobre os riscos que apresentam à saúde e à segurança dos consumidores.\n\n"
            "Parágrafo único. As informações de que trata este artigo não podem ser falsas, enganosas ou "
            "tendentes a induzir em erro o consumidor, ainda que por omissão de dados essenciais para a "
            "tomada de decisão de compra ou contratação do serviço."
        ),
    },
    {
        "article_number": "Art. 35",
        "title": "Descumprimento da Oferta",
        "content": (
            "Art. 35. Se o fornecedor de produtos ou serviço recusar cumprimento à oferta, apresentação, "
            "publicidade ou descrição facilitada pela sua própria divulgação, poderá o consumidor, conforme "
            "preferir, exigir o cumprimento forçado da obrigação, nos termos da oferta, apresentação ou "
            "publicidade; aceitar outro produto ou prestação de serviço equivalente; ou rescindir o contrato "
            "com restitução de quantia eventualmente adiantada, monetariamente atualizada, e indenização por "
            "eventuais perdas e danos."
        ),
    },
    {
        "article_number": "Art. 39",
        "title": "Práticas Abusivas",
        "content": (
            "Art. 39. É vedado ao fornecedor de produtos ou serviços, dentre outras práticas abusivas:\n\n"
            "I - condicionar o fornecimento de produto ou de serviço ao fornecimento de outro produto ou "
            "serviço, bem como, sem justa causa, a limites quantitativos;\n"
            "II - recusar atendimento às demandas dos consumidores, na exata medida de suas disponibilidades "
            "e da natureza do produto ou serviço;\n"
            "III - enviar ou entregar ao consumidor, sem solicitação prévia, qualquer produto ou efetuar "
            "pagamento, quando este não resultar de transação anterior ou de solicitação manifesta;\n"
            "IV - prevalecer-se da fraqueza ou ignorância do consumidor, tendo em vista sua idade, saúde, "
            "conhecimento ou condição social, para impingir-lhe seus produtos ou serviços;\n"
            "V - exigir do consumidor vantagem manifestamente excessiva;\n"
            "VI - executar serviços sem a prévia elaboração de orçamento e autorização expressa do consumidor, "
            "ressalvadas as decorrências previstas em lei;\n"
            "VII - cobrar valores ou aumentos sem autorização prévia, expressa e clara do consumidor de forma "
            "que dê, ao fornecedor, a possibilidade de, imediatamente, avaliá-lo e se recusar;\n"
            "VIII - inverter a ordem lógica, temporal ou de apresentação dos dados ou eventos constantes de "
            "publicidade."
        ),
    },
    {
        "article_number": "Art. 46",
        "title": "Proteção Contratual (Conhecimento Prévio)",
        "content": (
            "Art. 46. Os contratos que regulam as relações de consumo não obrigarão o consumidor se não lhe "
            "for dado conhecimento prévio, de forma clara e ostensiva, de seu conteúdo, em especial sobre os "
            "direitos e obrigações, ou se os respectivos instrumentos forem redigidos de modo a dificultar, "
            "de forma fraudulenta ou abusiva, a imediata e eficaz compreensão de seu sentido e alcance.\n\n"
            "Parágrafo único. Incluem-se entre os direitos e obrigações referidos no caput deste artigo aqueles "
            "decorrentes de modificações introduzidas nos contratos mediante cláusulas que alterem o substrato "
            "essencial do negócio, inclusive quanto ao preço."
        ),
    },
    {
        "article_number": "Art. 47",
        "title": "Interpretação Favorável ao Consumidor",
        "content": (
            "Art. 47. As cláusulas contratuais serão interpretadas de maneira mais favorável ao consumidor, em "
            "caso de dúvida."
        ),
    },
    {
        "article_number": "Art. 49",
        "title": "Direito de Arrependimento",
        "content": (
            "Art. 49. O consumidor pode desistir do contrato, no prazo de sete dias a contar de sua assinatura "
            "ou do ato de recebimento do produto ou serviço, sempre que a contratação de fornecimento de "
            "produtos ou serviços ocorrer fora do estabelecimento comercial, especialmente por telefone ou a "
            "domicílio.\n\n"
            "Parágrafo único. Se o consumidor exercitar o direito de arrependimento previsto neste artigo, "
            "os valores eventualmente pagos, a qualquer título, durante o prazo de reflexão, serão devolvidos, "
            "imediatamente, sem prejuízo de eventual compensação por utilização de bem ou serviço fornecido."
        ),
    },
    {
        "article_number": "Art. 51",
        "title": "Cláusulas Abusivas",
        "content": (
            "Art. 51. São nulas de pleno direito, entre outras, as cláusulas contratuais relativas ao "
            "fornecimento de produtos e serviços que:\n\n"
            "I - impossibilitem, exonerem ou atenuem a responsabilidade do fornecedor por vícios de qualidade "
            "ou quantidade, ou por fato do produto ou serviço, ou, ainda, por disparates, inclusive a indicação "
            "de falhas e dificuldades em seu funcionamento e manutenção;\n"
            "II - estabeleçam obrigações consideradas iníquas, abusivas, que coloquem o consumidor em desvantagem "
            "exagerada, ou seja, incompatível com a boa-fé ou a eqüidade;\n"
            "III - determinem a utilização compulsória de arbitragem;\n"
            "IV - imponham representante para concluir ou realizar transação relativa ao contrato;\n"
            "V - deixem ao fornecedor a opção de cancelar o contrato unilateralmente, sem que igual direito seja "
            "conferido ao consumidor;\n"
            "VI - permitam ao fornecedor transferir responsabilidade a terceiro;\n"
            "VII - permitam ao fornecedor cancelar unilateralmente o contrato, salvo por desídia do consumidor;\n"
            "VIII - obriguem o consumidor a ressarcir despesas ou perdas causadas pela ineficiência de serviço "
            "ou produto;\n"
            "IX - ressalvado o disposto em lei específica, prevejam obrigações ou previsões de forma que "
            "impossibilite ou dificulte substancialmente a caracterização do inadimplemento do fornecedor;\n"
            "X - quando da celebração de contrato de adesão, não mencione claramente, em caracteres ostensivos e "
            "de fácil leitura, informações essenciais assim consideradas pela regulamentação, como preço na "
            "moeda nacional, número de parcelas e respectivos vencimentos e taxas de juros de mora;\n"
            "XI - tratando-se de fornecimento de produto ou serviço por preço pré-fixado e em prestações, "
            "sujeitam-se ao cumprimento dos objetivos fixados em regulamento administrativo a partir do segundo "
            "mês, resguardados os direitos do fornecedor a perdas e danos.\n\n"
            "§ 1º Presume-se exagerada, entre outros casos, a vantagem que se aufira:\n"
            "a) principal ou acessoriamente, da perda ou restrição de direitos ou garantias que a lei concede ao "
            "consumidor;\n"
            "b) da falta de informações significativas sobre o produto ou serviço.\n\n"
            "§ 2º A nulidade parcial de uma cláusula abusiva não invalida o contrato, exceto quando de sua "
            "anulação decorrer ônus excessivo para qualquer das partes contratantes.\n\n"
            "§ 3º As cláusulas abusivas serão interpretadas de forma mais benéfica ao consumidor, e qualquer "
            "dúvida será resolvida em favor dele."
        ),
    },
    {
        "article_number": "Art. 54",
        "title": "Contrato de Adesão",
        "content": (
            "Art. 54. Contrato de adesão é aquele cujas cláusulas tenham sido aprovadas pela autoridade "
            "competente ou estabelecidas unilateralmente pelo fornecedor, sem que o consumidor possa discutir ou "
            "modificar substancialmente seu conteúdo.\n\n"
            "§ 1º A inserção de cláusula leonina não desfigura a natureza de contrato de adesão.\n\n"
            "§ 2º Quando o fornecedor de produtos ou serviços recorrer a contrato de adesão ou normas gerais de "
            "contratação poderá o consumidor exigir, alternativamente e à sua escolha:\n"
            "a) a imediata modificação do conteúdo que se mostre excessivamente oneroso, respeitando-se o "
            "ventilado nas demais cláusulas;\n"
            "b) a restituição imediata da quantia paga, monetariamente atualizada, sem prejuízo de perdas e danos.\n\n"
            "§ 3º Os contratos de adesão regulados por órgãos governamentais e seus efeitos serão também "
            "disciplinados pelas normas deste Código."
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


def seed_cdc_articles(engine):
    """
    Seed key CDC articles into legal_documents table.
    Idempotent: checks if each article already exists before inserting.
    """
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Table 'legal_documents' does not exist.")
        print("   Run the migration first: alembic upgrade head")
        return False

    seeded_count = 0
    skipped_count = 0

    with Session(engine) as session:
        for article in CDC_ARTICLES:
            # Check if already seeded (by title or article number in metadata)
            existing = session.execute(
                text(
                    "SELECT id FROM legal_documents "
                    "WHERE title = :title AND source = 'CDC - Lei 8.078/1990'"
                ),
                {"title": f"CDC {article['article_number']} - {article['title']}"},
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
                    "title": f"CDC {article['article_number']} - {article['title']}",
                    "source": "CDC - Lei 8.078/1990",
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
                      AND ld.source = 'CDC - Lei 8.078/1990'
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
    print("🏛️  CDC Seed Script")
    print("   Artigos: 6, 12, 14, 18, 20, 26, 30, 31, 35, 39, 46, 47, 49, 51, 54")
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
    print("📝 Inserindo artigos da CDC...\n")
    success = seed_cdc_articles(engine)

    if not success:
        sys.exit(1)

    # Try to generate embeddings
    trigger_embedding_generation(engine)

    print("\n" + "=" * 60)
    print("✅ Seed CDC concluído com sucesso!")
    print("=" * 60)

    engine.dispose()


if __name__ == "__main__":
    main()
