"""
Pydantic schemas for request validation and response serialization.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


# --- Enums ---

class UserRole(str, Enum):
    admin = "admin"
    user = "user"

class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"

class DocumentStatus(str, Enum):
    uploaded = "uploaded"
    processing = "processing"
    analyzed = "analyzed"
    error = "error"


# --- Auth ---

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6)

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class UserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    # `role` nao entra aqui de proposito. Aceitar o papel vindo do cliente permitia
    # que qualquer visitante se cadastrasse como admin pelo /docs, que e publico.
    # Promocao a admin passa pelo banco.

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    full_name: Optional[str]
    role: str
    created_at: datetime


# --- Rules ---

class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    severity: Severity = Severity.medium
    criteria: str = Field(..., min_length=1)
    # Preenchido para criar uma regra de equipe; omitido cria uma regra pessoal.
    organization_id: Optional[UUID] = None

class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[Severity] = None
    criteria: Optional[str] = None
    is_active: Optional[bool] = None

class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: Optional[str]
    severity: str
    criteria: str
    is_active: bool
    created_at: datetime
    scope: str = "global"       # global | user | organization
    editable: bool = True       # regras globais nao podem ser editadas por quem as consome


# --- Documents ---

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    file_size: Optional[int]
    mime_type: Optional[str]
    status: str
    uploaded_at: datetime
    risk_score: Optional[int] = None
    summary: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


# --- Analysis / Alerts ---

class AlertResolution(str, Enum):
    """O que o revisor decidiu sobre o alerta."""
    to_fix = "to_fix"                  # precisa ser corrigido no contrato
    not_applicable = "not_applicable"  # nao se aplica a este caso
    resolved = "resolved"              # ja tratado


class AlertResolutionUpdate(BaseModel):
    resolution: Optional[AlertResolution] = None  # null limpa a marcacao
    comment: Optional[str] = None


class LegalSourceSchema(BaseModel):
    """Dispositivo legal citado, com o texto da lei, quando o RAG o recuperou."""
    source: str
    article_ref: str
    content: str


class AlertSchema(BaseModel):
    rule_name: str
    severity: str
    excerpt: str
    issue: str
    suggestion: str
    legal_basis: Optional[str] = None
    # Resultado da conferência feita em código. Análises antigas não têm estes
    # campos e simplesmente não exibem selo.
    excerpt_check: Optional[str] = None       # exact | approximate | not_found | empty
    excerpt_page: Optional[int] = None        # pagina onde o trecho foi localizado
    legal_basis_check: Optional[str] = None   # grounded | in_base | law_only | ungrounded | empty | no_context
    legal_source: Optional[LegalSourceSchema] = None
    # Preenchido pelo endpoint de relatorio a partir do feedback do revisor.
    resolution: Optional[str] = None
    resolution_comment: Optional[str] = None

class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    risk_score: int
    summary: str
    alerts: List[AlertSchema]
    missing_clauses: List[str] = []
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    analyzed_at: datetime

class ReportResponse(BaseModel):
    """Full report combining document info + analysis."""
    document: DocumentResponse
    analysis: AnalysisResponse
    rules_checked: List[RuleResponse]


# --- Analysis Task ---

class AnalysisStatusResponse(BaseModel):
    document_id: UUID
    status: str
    task_id: Optional[str] = None
    risk_score: Optional[int] = None
    message: str = ""


# --- Legislation (RAG) ---

class LegislationIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    full_text: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1, max_length=255, description="e.g. 'Lei 13.709/2018 (LGPD)'")
    category: str = Field(..., min_length=1, max_length=100, description="e.g. 'proteção_de_dados'")
    chunk_size: int = Field(800, ge=200, le=4000)
    overlap: int = Field(100, ge=0, le=500)


class LegalChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    chunk_index: int
    content: str
    article_ref: Optional[str] = None


class LegislationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    source: str
    category: str
    created_at: datetime
    chunk_count: int = 0


class LegislationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    source: str
    category: str
    full_text: str
    created_at: datetime
    chunks: List[LegalChunkResponse] = []


class LegislationSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)
    category: Optional[str] = None


class LegislationSearchResult(BaseModel):
    id: str
    content: str
    article_ref: Optional[str] = None
    document_title: str
    document_source: str
    similarity: float


class LegislationSearchResponse(BaseModel):
    results: List[LegislationSearchResult]
    total: int


# --- Organizations (FASE 2) ---

class OrgRole(str, Enum):
    owner = "owner"
    admin = "admin"
    member = "member"

class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")
    cnpj: Optional[str] = Field(None, max_length=18)

class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    cnpj: Optional[str] = Field(None, max_length=18)
    is_active: Optional[bool] = None

class OrgMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    role: str
    joined_at: datetime
    user_email: Optional[str] = None
    user_name: Optional[str] = None

class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    cnpj: Optional[str]
    is_active: bool
    created_at: datetime
    member_count: int = 0

class OrganizationDetailResponse(OrganizationResponse):
    members: List[OrgMemberResponse] = []

class AddMemberRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    role: OrgRole = OrgRole.member

class UpdateMemberRoleRequest(BaseModel):
    role: OrgRole


# --- Contract Templates (FASE 2) ---

class ContractTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field("geral", max_length=100)
    rule_ids: List[UUID] = []
    custom_instructions: Optional[str] = None

class ContractTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    rule_ids: Optional[List[UUID]] = None
    custom_instructions: Optional[str] = None
    is_active: Optional[bool] = None

class ContractTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    name: str
    description: Optional[str]
    category: str
    rule_ids: List[UUID] = []
    custom_instructions: Optional[str]
    is_active: bool
    created_by: Optional[UUID]
    created_at: datetime

class ContractTemplateListResponse(BaseModel):
    templates: List[ContractTemplateResponse]
    total: int


# --- Approval Workflows (FASE 3) ---

class WorkflowStatus(str, Enum):
    pending_review = "pending_review"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"
    revision_requested = "revision_requested"

class WorkflowCreate(BaseModel):
    document_id: UUID
    total_steps: int = Field(1, ge=1, le=10)
    assigned_to: Optional[UUID] = None

class WorkflowTransition(BaseModel):
    action: str = Field(..., description="approve | reject | request_revision | advance")
    comment: Optional[str] = None
    assigned_to: Optional[UUID] = None

class WorkflowCommentSchema(BaseModel):
    user_id: str
    user_name: Optional[str] = None
    action: str
    comment: Optional[str] = None
    timestamp: str

class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    organization_id: Optional[UUID]
    status: str
    current_step: int
    total_steps: int
    assigned_to: Optional[UUID]
    created_by: UUID
    comments: List[WorkflowCommentSchema] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class WorkflowListResponse(BaseModel):
    workflows: List[WorkflowResponse]
    total: int


# --- Webhook Configs (FASE 3) ---

class WebhookEvent(str, Enum):
    document_uploaded = "document.uploaded"
    document_analyzed = "document.analyzed"
    workflow_created = "workflow.created"
    workflow_approved = "workflow.approved"
    workflow_rejected = "workflow.rejected"

class WebhookConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1, max_length=2000)
    secret: Optional[str] = Field(None, max_length=255)
    events: List[str] = []
    organization_id: Optional[UUID] = None

class WebhookConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    url: Optional[str] = Field(None, max_length=2000)
    secret: Optional[str] = Field(None, max_length=255)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None

class WebhookConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: Optional[UUID]
    name: str
    url: str
    events: List[str] = []
    is_active: bool
    created_by: Optional[UUID]
    created_at: datetime

class WebhookConfigListResponse(BaseModel):
    webhooks: List[WebhookConfigResponse]
    total: int


# --- Analysis Feedback (FASE 4) ---

class FeedbackCreate(BaseModel):
    analysis_id: UUID
    rating: int = Field(..., ge=1, le=5)
    adjusted_score: Optional[int] = Field(None, ge=0, le=100)
    comment: Optional[str] = None

class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    analysis_id: UUID
    user_id: UUID
    rating: int
    adjusted_score: Optional[int]
    comment: Optional[str]
    created_at: datetime


# --- Alert-level Feedback (learning loop) ---

class AlertFeedbackCreate(BaseModel):
    analysis_id: UUID
    alert_index: int = Field(..., ge=0)
    rule_name: str
    severity: Optional[str] = None
    is_correct: bool
    comment: Optional[str] = None

class AlertFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    analysis_id: UUID
    user_id: UUID
    alert_index: int
    rule_name: str
    severity: Optional[str]
    is_correct: bool
    comment: Optional[str]
    created_at: datetime

class AlertFeedbackBatchCreate(BaseModel):
    """Submit feedback for multiple alerts at once."""
    analysis_id: UUID
    rating: int = Field(..., ge=1, le=5)           # overall analysis rating
    comment: Optional[str] = None                   # overall comment
    adjusted_score: Optional[int] = Field(None, ge=0, le=100)
    alerts: List[AlertFeedbackCreate] = []          # per-alert feedback

class FeedbackSummary(BaseModel):
    """Summary returned after submitting batch feedback."""
    analysis_feedback_id: UUID
    alert_feedbacks_count: int
    correct_count: int
    incorrect_count: int


# --- Dashboard / Analytics (FASE 4) ---

class DashboardOverview(BaseModel):
    total_documents: int
    total_analyzed: int
    total_pending: int
    avg_risk_score: Optional[float]
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int

class AlertFrequency(BaseModel):
    rule_name: str
    count: int
    avg_severity_weight: float

class RiskTrend(BaseModel):
    period: str  # e.g. "2026-02" or "2026-02-24"
    avg_risk_score: float
    document_count: int

class DashboardResponse(BaseModel):
    overview: DashboardOverview
    top_alerts: List[AlertFrequency]
    risk_trend: List[RiskTrend]
