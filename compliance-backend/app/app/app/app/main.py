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

        # Seed default rules (canonical list lives in app/scripts/seed_rules.py,
        # which is also runnable standalone for production databases)
        result = await db.execute(select(Rule))
        if not result.scalars().first():
            from app.scripts.seed_rules import DEFAULT_RULES
            db.add_all([Rule(**spec) for spec in DEFAULT_RULES])
            logger.info(f"📋 {len(DEFAULT_RULES)} default rules created")

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