"""
SQLAlchemy models — matches the database schema from the system design doc.
Compatible with both PostgreSQL and SQLite.
"""
import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, ForeignKey, Enum, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSON as PG_JSON
from sqlalchemy.types import TypeDecorator, CHAR, Text as TextType
from sqlalchemy.orm import relationship
from app.core.database import Base

import json as _json


# ─── Cross-DB UUID type ───
class UUID(TypeDecorator):
    """Platform-independent UUID type. Uses PostgreSQL UUID, stores as CHAR(36) on SQLite."""
    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid=True):
        self.as_uuid = as_uuid
        super().__init__(length=36)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=self.as_uuid))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if self.as_uuid and not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value))
        return value


# ─── Cross-DB JSON type ───
class JSON(TypeDecorator):
    """Platform-independent JSON type. Uses PostgreSQL JSON natively, TEXT + json on SQLite."""
    impl = TextType
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSON())
        return dialect.type_descriptor(TextType())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return _json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if dialect.name != "postgresql" and isinstance(value, str):
            return _json.loads(value)
        return value


# ─── Vector type (optional — only with pgvector) ───
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback: store embeddings as Text (RAG search won't work, but app won't crash)
    def Vector(dim=None):
        return TextType()


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(Enum("admin", "user", name="user_role"), nullable=False, default="user")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    organization = relationship("Organization", foreign_keys=[organization_id])


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    status = Column(
        Enum("uploaded", "processing", "analyzed", "error", name="document_status"),
        nullable=False,
        default="uploaded",
    )
    uploaded_at = Column(DateTime(timezone=True), default=utcnow)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("contract_templates.id", ondelete="SET NULL"), nullable=True)
    extracted_text = Column(Text, nullable=True)  # stores the extracted text for reprocessing

    owner = relationship("User", back_populates="documents")
    analysis = relationship("Analysis", back_populates="document", uselist=False, cascade="all, delete-orphan")
    template = relationship("ContractTemplate")


class Rule(Base):
    __tablename__ = "rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    severity = Column(Enum("high", "medium", "low", name="severity_level"), nullable=False, default="medium")
    criteria = Column(Text, nullable=False)
    # Escopo da regra:
    #   organization_id e user_id nulos -> regra global (padrao do sistema, somente leitura)
    #   user_id preenchido              -> regra pessoal do usuario
    #   organization_id preenchido      -> regra da organizacao/equipe
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization = relationship("Organization", foreign_keys=[organization_id])
    owner = relationship("User", foreign_keys=[user_id])

    @property
    def scope(self) -> str:
        if self.organization_id is not None:
            return "organization"
        if self.user_id is not None:
            return "user"
        return "global"


class RuleOverride(Base):
    """Desativa uma regra global dentro de um escopo (usuario ou organizacao).

    Regras globais sao compartilhadas e nao podem ser editadas por quem as consome,
    entao "desligar para mim" vira uma linha aqui em vez de um UPDATE na regra.
    """
    __tablename__ = "rule_overrides"
    __table_args__ = (
        sa.UniqueConstraint("rule_id", "user_id", "organization_id", name="uq_rule_override_scope"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("rules.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    risk_score = Column(Integer, CheckConstraint("risk_score >= 0 AND risk_score <= 100"))
    summary = Column(Text)
    alerts = Column(JSON, default=list)
    missing_clauses = Column(JSON, default=list)
    prompt_tokens = Column(Integer, nullable=True)  # for cost tracking
    completion_tokens = Column(Integer, nullable=True)
    # Rastreabilidade: duas analises so sao comparaveis se sairam do mesmo modelo
    # e da mesma versao do prompt. Sem isto nao ha como auditar uma mudanca.
    model = Column(String(64), nullable=True)
    prompt_version = Column(String(16), nullable=True)
    analyzed_at = Column(DateTime(timezone=True), default=utcnow)

    document = relationship("Document", back_populates="analysis")


class LegalDocument(Base):
    """Legislation texts indexed for RAG-based compliance analysis."""
    __tablename__ = "legal_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    source = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    full_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    chunks = relationship("LegalChunk", back_populates="document", cascade="all, delete-orphan")


class LegalChunk(Base):
    """Embedded chunks of legislation for semantic search."""
    __tablename__ = "legal_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("legal_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    article_ref = Column(String(100), nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)

    document = relationship("LegalDocument", back_populates="chunks")


# ─── FASE 2 — Contexto Organizacional ─────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    cnpj = Column(String(18), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    members = relationship("OrgMember", back_populates="organization", cascade="all, delete-orphan")
    templates = relationship("ContractTemplate", back_populates="organization", cascade="all, delete-orphan")


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("owner", "admin", "member", name="org_role"), nullable=False, default="member")
    joined_at = Column(DateTime(timezone=True), default=utcnow)

    organization = relationship("Organization", back_populates="members")
    user = relationship("User")


class ContractTemplate(Base):
    __tablename__ = "contract_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False, default="geral")
    rule_ids = Column(JSON, default=list)
    custom_instructions = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization = relationship("Organization", back_populates="templates")
    creator = relationship("User")


# ─── FASE 3 — Workflow e Integrações ──────────────────────────────────────────

class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        Enum("pending_review", "in_review", "approved", "rejected", "revision_requested",
             name="workflow_status"),
        nullable=False, default="pending_review",
    )
    current_step = Column(Integer, nullable=False, default=1)
    total_steps = Column(Integer, nullable=False, default=1)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    comments = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document")
    assignee = relationship("User", foreign_keys=[assigned_to])
    creator = relationship("User", foreign_keys=[created_by])


class WebhookConfig(Base):
    __tablename__ = "webhook_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    url = Column(String(2000), nullable=False)
    secret = Column(String(255), nullable=True)
    events = Column(JSON, default=list)  # e.g. ["document.analyzed", "workflow.approved"]
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    organization = relationship("Organization")
    creator = relationship("User")


# ─── FASE 4 — Inteligência e Diferenciação ────────────────────────────────────

class AnalysisFeedback(Base):
    __tablename__ = "analysis_feedback"
    __table_args__ = (
        sa.UniqueConstraint("analysis_id", "user_id", name="uq_feedback_per_user"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating"),
        sa.CheckConstraint(
            "adjusted_score IS NULL OR (adjusted_score >= 0 AND adjusted_score <= 100)",
            name="ck_feedback_score",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5
    adjusted_score = Column(Integer, nullable=True)  # user-suggested risk score 0-100
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    analysis = relationship("Analysis")
    user = relationship("User")


class AlertFeedback(Base):
    """Per-alert feedback: user marks each alert as correct/incorrect with optional comment.
    Used to build the AI learning loop — injected into future analysis prompts."""
    __tablename__ = "alert_feedback"
    __table_args__ = (
        sa.UniqueConstraint("analysis_id", "alert_index", "user_id", name="uq_alert_fb_per_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    alert_index = Column(Integer, nullable=False)       # index of the alert in analysis.alerts[]
    rule_name = Column(String(255), nullable=False)      # duplicated for easy querying
    severity = Column(String(20), nullable=True)
    # Duas coisas diferentes convivem aqui, de proposito:
    #   is_correct  a IA acertou? Alimenta o learning loop do prompt.
    #   resolution  o que o revisor decidiu fazer? E fluxo de trabalho humano.
    # Quem so quer marcar o alerta como tratado nao precisa avaliar a IA, por isso
    # is_correct e opcional.
    is_correct = Column(Boolean, nullable=True)          # True = "IA acertou", False = "falso positivo"
    resolution = Column(
        Enum("to_fix", "not_applicable", "resolved", name="alert_resolution"),
        nullable=True,
    )
    comment = Column(Text, nullable=True)                # user explanation
    created_at = Column(DateTime(timezone=True), default=utcnow)

    analysis = relationship("Analysis")
    user = relationship("User")
