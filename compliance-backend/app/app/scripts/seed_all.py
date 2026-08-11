"""
Master Seed Script - Runs all individual seed scripts in sequence
Seeds all compliance-related articles from multiple laws into the legal_documents table.

Laws included:
- LGPD (Lei 13.709/2018) - 8 articles
- CDC (Lei 8.078/1990) - 15 articles
- Código Civil (Lei 10.406/2002) - 20 articles
- CLT (Consolidação das Leis do Trabalho) - 15 articles
- Marco Civil da Internet (Lei 12.965/2014) - 12 articles
- Lei Anticorrupção (Lei 12.846/2013) - 11 articles
- Lei de Licitações (Lei 14.133/2021) - 12 articles

Total: 93 articles

Runs with sync engine. Idempotent (checks if already seeded).
Handles errors gracefully - if one law fails, continues with others.

Usage:
    python -m app.scripts.seed_all
    # or
    python app/scripts/seed_all.py
"""

import sys
import os
from datetime import datetime
# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import create_engine, text, inspect

from app.core.config import Settings
from app.scripts.seed_lgpd import seed_lgpd_articles, LGPD_ARTICLES
from app.scripts.seed_cdc import seed_cdc_articles, CDC_ARTICLES
from app.scripts.seed_codigo_civil import seed_codigo_civil_articles, CODIGO_CIVIL_ARTICLES
from app.scripts.seed_clt import seed_clt_articles, CLT_ARTICLES
from app.scripts.seed_marco_civil import seed_marco_civil_articles, MARCO_CIVIL_ARTICLES
from app.scripts.seed_anticorrupcao import seed_anticorrupcao_articles, ANTICORRUPCAO_ARTICLES
from app.scripts.seed_licitacoes import seed_licitacoes_articles, LICITACOES_ARTICLES

settings = Settings()


# ── Configuration ────────────────────────────────────────────────────────────

SEEDING_JOBS = [
    {
        "name": "LGPD - Lei 13.709/2018",
        "function": seed_lgpd_articles,
        "articles_count": len(LGPD_ARTICLES),
    },
    {
        "name": "CDC - Lei 8.078/1990",
        "function": seed_cdc_articles,
        "articles_count": len(CDC_ARTICLES),
    },
    {
        "name": "Código Civil - Lei 10.406/2002",
        "function": seed_codigo_civil_articles,
        "articles_count": len(CODIGO_CIVIL_ARTICLES),
    },
    {
        "name": "CLT - Consolidação das Leis do Trabalho",
        "function": seed_clt_articles,
        "articles_count": len(CLT_ARTICLES),
    },
    {
        "name": "Marco Civil da Internet - Lei 12.965/2014",
        "function": seed_marco_civil_articles,
        "articles_count": len(MARCO_CIVIL_ARTICLES),
    },
    {
        "name": "Lei Anticorrupção - Lei 12.846/2013",
        "function": seed_anticorrupcao_articles,
        "articles_count": len(ANTICORRUPCAO_ARTICLES),
    },
    {
        "name": "Lei de Licitações - Lei 14.133/2021",
        "function": seed_licitacoes_articles,
        "articles_count": len(LICITACOES_ARTICLES),
    },
]


# ── Helper Functions ─────────────────────────────────────────────────────────

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


def print_header(title: str, width: int = 70):
    """Print a formatted header."""
    print("=" * width)
    print(title.center(width))
    print("=" * width)


def print_subheader(title: str, width: int = 70):
    """Print a formatted subheader."""
    print("\n" + "-" * width)
    print(title)
    print("-" * width)


# ── Main Seed Function ───────────────────────────────────────────────────────

def seed_all_articles(engine):
    """
    Run all seeding functions in sequence.
    Errors in one function do not stop the process.
    """
    results = {
        "success": [],
        "failed": [],
        "total_seeded": 0,
    }

    print_subheader("🚀 Iniciando seeding de todos os artigos")

    for idx, job in enumerate(SEEDING_JOBS, 1):
        job_name = job["name"]
        job_func = job["function"]
        expected_count = job["articles_count"]

        print(f"\n[{idx}/{len(SEEDING_JOBS)}] 📚 {job_name}")
        print(f"     Esperado: {expected_count} artigos")
        print(f"     Executando...")

        try:
            success = job_func(engine)
            if success:
                results["success"].append({
                    "name": job_name,
                    "articles": expected_count,
                })
                results["total_seeded"] += expected_count
                print(f"     ✅ Concluído com sucesso")
            else:
                results["failed"].append({
                    "name": job_name,
                    "reason": "Seed function returned False",
                })
                print(f"     ❌ Falha na execução")
        except Exception as e:
            results["failed"].append({
                "name": job_name,
                "reason": str(e),
            })
            print(f"     ❌ Erro: {e}")


    return results


def print_summary(results):
    """Print a summary of seeding results."""
    print_subheader("📊 Resumo do Seeding")

    print("\n✅ SUCESSO:")
    if results["success"]:
        for item in results["success"]:
            print(f"   • {item['name']}: {item['articles']} artigos")
    else:
        print("   (nenhum)")

    print("\n❌ FALHAS:")
    if results["failed"]:
        for item in results["failed"]:
            print(f"   • {item['name']}")
            print(f"     Motivo: {item['reason']}")
    else:
        print("   (nenhum)")

    print(f"\n📈 TOTAL:")
    print(f"   • Artigos seeded: {results['total_seeded']}")
    print(f"   • Leis processadas com sucesso: {len(results['success'])}/{len(SEEDING_JOBS)}")

    if results["failed"]:
        print(f"   • Leis com falha: {len(results['failed'])}")

    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print_header("🏛️  MASTER SEEDING SCRIPT - Compliance Project", width=70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total de leis: {len(SEEDING_JOBS)}")
    print(f"Total esperado de artigos: {sum(job['articles_count'] for job in SEEDING_JOBS)}")
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

    # Check if table exists
    if not check_table_exists(engine, "legal_documents"):
        print("❌ Tabela 'legal_documents' não existe.")
        print("   Execute a migration primeiro: alembic upgrade head")
        sys.exit(1)

    # Run all seed functions
    results = seed_all_articles(engine)

    # Print summary
    print_summary(results)

    # Print final message
    print_header("✅ MASTER SEEDING CONCLUÍDO!", width=70)

    engine.dispose()

    # Exit with appropriate code
    if results["failed"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
