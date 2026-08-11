"""
ComplianceAI — Main FastAPI Application

This is the entry point that wires together all routes, middleware, and startup events.
"""
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.core.limiter import limiter

from app.core.config import get_settings
from app.core.database import engine, Base
from app.core.logging import setup_logging, get_logger
from app.api import auth, documents, rules, legislation, organizations, templates, workflows, webhooks, dashboard
from app.core.limiter import limiter
settings = get_settings()

# ─── Structured Logging ───
setup_logging()
logger = get_logger("compliance")


# ─── Lifespan (startup/shutdown) ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(f"🚀 Starting {settings.APP_NAME} ({settings.APP_ENV})")

    # Create upload and storage directories
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path("storage").mkdir(parents=True, exist_ok=True)

    # In development, auto-create tables for convenience.
    # In production, use: alembic upgrade head
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            # Enable pgvector extension (only applies to PostgreSQL, ignored on SQLite)
            if "postgresql" in settings.DATABASE_URL:
                await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Database tables created/verified (dev mode — use Alembic in prod)")

        # Seed default admin user and rules
        await _seed_defaults()

        # Seed legal database (all legislation — idempotent)
        await _seed_legal_database()

    yield

    logger.info("🛑 Shutting down...")
    await engine.dispose()


async def _seed_defaults():
    """Create default admin user and rules if they don't exist."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.core.security import hash_password
    from app.models import User, Rule

    async with AsyncSessionLocal() as db:
        # Seed admin user
        result = await db.execute(select(User).where(User.email == "admin@complianceai.com.br"))
        if not result.scalar_one_or_none():
            admin = User(
                email="admin@complianceai.com.br",
                password_hash=hash_password("senha123"),
                full_name="Administrador",
                role="admin",
            )
            db.add(admin)
            logger.info("👤 Admin user created: admin@complianceai.com.br")

        # Seed default rules
        result = await db.execute(select(Rule))
        if not result.scalars().first():
            default_rules = [
                # ── Regras Gerais de Contratos ──
                Rule(name="Foro Competente", description="Verificar se o foro está adequado à jurisdição contratual", severity="high", criteria="Verificar se a cláusula de foro/jurisdição está presente e se é compatível com a sede das partes ou local de execução do contrato. Gerar alerta se o foro for em jurisdição incompatível ou ausente.", is_active=True),
                Rule(name="Prazo de Pagamento", description="Prazo de pagamento não pode exceder 60 dias", severity="medium", criteria="Verificar todos os prazos de pagamento mencionados. Se algum prazo exceder 60 dias corridos ou úteis, gerar alerta. Prazos entre 45-60 dias devem gerar observação.", is_active=True),
                Rule(name="Confidencialidade", description="Deve conter cláusula de confidencialidade/NDA", severity="high", criteria="Verificar presença de cláusula de confidencialidade, sigilo, NDA ou non-disclosure. Ausência completa gera alerta de alta severidade.", is_active=True),
                Rule(name="Multa de Rescisão", description="Multa de rescisão não pode exceder 10% do valor total", severity="medium", criteria="Verificar se há cláusula de multa rescisória. Se o percentual exceder 10% do valor total do contrato, gerar alerta.", is_active=True),
                Rule(name="Vigência Definida", description="O contrato deve ter prazo de vigência claramente definido", severity="low", criteria="Verificar se há cláusula de vigência com datas claras (início e fim) ou período definido. Contratos por prazo indeterminado sem justificativa geram alerta.", is_active=True),
                # ── LGPD (Lei 13.709/2018) ──
                Rule(name="Conformidade LGPD", description="Contratos com tratamento de dados pessoais devem referenciar a LGPD", severity="high", criteria="Se o contrato envolve coleta, armazenamento, compartilhamento ou tratamento de dados pessoais, verificar menção à LGPD (Lei 13.709/2018), bases legais (Art. 7º), direitos do titular (Art. 18) e medidas de segurança (Art. 46). Ausência gera alerta.", is_active=True),
                # ── Código de Defesa do Consumidor (Lei 8.078/1990) ──
                Rule(name="Conformidade CDC", description="Contratos com consumidores devem respeitar o CDC", severity="high", criteria="Se o contrato é de consumo (B2C), verificar: cláusulas abusivas (Art. 51 do CDC), direito de arrependimento em compras fora do estabelecimento (Art. 49), transparência nas informações (Art. 6º), garantia legal (Art. 26). Cláusulas que limitem direitos do consumidor geram alerta.", is_active=True),
                # ── Código Civil (Lei 10.406/2002) ──
                Rule(name="Conformidade Código Civil", description="Verificar aderência às normas gerais de contratos do Código Civil", severity="medium", criteria="Verificar: função social do contrato (Art. 421), boa-fé objetiva (Art. 422), vícios de consentimento, onerosidade excessiva (Art. 478-480), e se as cláusulas respeitam os requisitos de validade do negócio jurídico (Art. 104). Cláusulas leoninas ou que violem equilíbrio contratual geram alerta.", is_active=True),
                # ── CLT / Legislação Trabalhista ──
                Rule(name="Conformidade Trabalhista", description="Contratos de trabalho/prestação de serviço devem observar a legislação trabalhista", severity="high", criteria="Se o contrato envolve prestação de serviço ou relação de trabalho, verificar: descaracterização de vínculo empregatício (Art. 3º CLT), observância de direitos irrenunciáveis, conformidade com reforma trabalhista (Lei 13.467/2017), e se terceirização segue a Lei 13.429/2017. Indícios de pejotização geram alerta.", is_active=False),
                # ── Marco Civil da Internet (Lei 12.965/2014) ──
                Rule(name="Conformidade Marco Civil", description="Contratos digitais devem observar o Marco Civil da Internet", severity="medium", criteria="Se o contrato envolve serviços digitais, aplicações de internet ou armazenamento de dados online, verificar menção ao Marco Civil (Lei 12.965/2014): neutralidade de rede (Art. 9º), proteção de registros e dados pessoais (Art. 10-12), responsabilidade de provedores (Art. 18-21). Ausência gera alerta.", is_active=False),
                # ── Lei Anticorrupção (Lei 12.846/2013) ──
                Rule(name="Cláusula Anticorrupção", description="Contratos corporativos devem conter cláusula anticorrupção", severity="medium", criteria="Verificar presença de cláusula anticorrupção referenciando a Lei 12.846/2013 e/ou FCPA/UK Bribery Act. Deve incluir compromisso das partes com práticas éticas, vedação a suborno e corrupção, e previsão de rescisão em caso de violação. Ausência em contratos B2B gera alerta.", is_active=True),
            ]
            db.add_all(default_rules)
            logger.info(f"📋 {len(default_rules)} default rules created")

        await db.commit()


async def _seed_legal_database():
    """Seed the legal documents database with consolidated structure:
    1 legal_document per law + N legal_chunks per law (one per article).
    Idempotent — skips laws that already have chunks."""
    import asyncio

    def _run_seed():
        from app.scripts.seed_legal_base import seed_legal_base, get_sync_engine

        try:
            sync_engine = get_sync_engine()
        except Exception as e:
            return f"Erro ao conectar: {e}"

        try:
            seed_legal_base(sync_engine)
            return "OK"
        except Exception as e:
            return f"Erro: {e}"
        finally:
            sync_engine.dispose()

    try:
        result = await asyncio.to_thread(_run_seed)
        if result == "OK":
            logger.info("📚 Base legal seed concluído com sucesso")
        else:
            logger.warning(f"⚠️ Legal database seed: {result}")
    except Exception as e:
        logger.warning(f"⚠️ Legal database seed skipped: {e}")


# ─── App ───
app = FastAPI(
    title=settings.APP_NAME,
    description="Plataforma de IA para Compliance Contratual Multi-legislação (LGPD, CDC, CC, CLT, Marco Civil e mais)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rate Limiting ───
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── Routes ───
app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")
app.include_router(legislation.router, prefix="/api/v1")
app.include_router(organizations.router, prefix="/api/v1")
app.include_router(templates.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


# ─── Health Check ───
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }


@app.get("/", tags=["Health"])
async def root():
    return {
        "app": settings.APP_NAME,
        "docs": "/docs",
        "health": "/health",
    }


# ─── Global Error Handler (com headers CORS) ───
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)

    # Incluir headers CORS para que o browser não bloqueie a resposta de erro
    origin = request.headers.get("origin", "")
    headers = {}
    if origin and (origin in settings.CORS_ORIGINS or "*" in settings.CORS_ORIGINS):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(
        status_code=500,
        content={"detail": f"Erro interno do servidor: {str(exc)}"},
        headers=headers,
    )