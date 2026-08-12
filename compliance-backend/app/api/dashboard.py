"""
Dashboard & Analytics API — aggregated metrics and feedback.

FASE 4: Provides overview metrics, alert frequency analysis,
risk trends over time, and user feedback on analysis quality.
"""
from uuid import UUID
from typing import Optional
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, extract

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas import (
    DashboardOverview,
    DashboardResponse,
    AlertFrequency,
    RiskTrend,
    FeedbackCreate,
    FeedbackResponse,
    AlertFeedbackCreate,
    AlertFeedbackResponse,
    AlertFeedbackBatchCreate,
    FeedbackSummary,
)

from app.services.scope import document_scope_filter, require_org_membership

router = APIRouter(prefix="/dashboard", tags=["Dashboard & Analytics"])

_SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}


# ─── Dashboard Overview ──────────────────────────────────────────────────────

@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    organization_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get aggregated dashboard metrics."""
    from app import Document, Analysis

    # ── Base query filters ──
    # O escopo manda: no pessoal contam os documentos proprios, no de equipe contam
    # os da equipe inteira — as metricas precisam bater com o que o Historico lista.
    if organization_id:
        await require_org_membership(organization_id, current_user, db)

    doc_filter = [await document_scope_filter(current_user, organization_id, db)]
    analysis_filter = []

    # ── Overview metrics ──
    total_q = select(func.count(Document.id)).where(*doc_filter) if doc_filter else select(func.count(Document.id))
    total_documents = (await db.execute(total_q)).scalar() or 0

    analyzed_q = select(func.count(Document.id)).where(Document.status == "analyzed", *doc_filter) if doc_filter else select(func.count(Document.id)).where(Document.status == "analyzed")
    total_analyzed = (await db.execute(analyzed_q)).scalar() or 0

    pending_q_conditions = [Document.status.in_(["uploaded", "processing"])] + doc_filter
    pending_q = select(func.count(Document.id)).where(*pending_q_conditions)
    total_pending = (await db.execute(pending_q)).scalar() or 0

    # Risk score aggregates from analyses
    if doc_filter:
        score_q = (
            select(
                func.avg(Analysis.risk_score),
                func.sum(case((Analysis.risk_score >= 61, 1), else_=0)),
                func.sum(case((Analysis.risk_score.between(31, 60), 1), else_=0)),
                func.sum(case((Analysis.risk_score <= 30, 1), else_=0)),
            )
            .join(Document, Analysis.document_id == Document.id)
            .where(*doc_filter)
        )
    else:
        score_q = select(
            func.avg(Analysis.risk_score),
            func.sum(case((Analysis.risk_score >= 61, 1), else_=0)),
            func.sum(case((Analysis.risk_score.between(31, 60), 1), else_=0)),
            func.sum(case((Analysis.risk_score <= 30, 1), else_=0)),
        )

    score_result = (await db.execute(score_q)).one()
    avg_risk = round(float(score_result[0]), 1) if score_result[0] is not None else None

    overview = DashboardOverview(
        total_documents=total_documents,
        total_analyzed=total_analyzed,
        total_pending=total_pending,
        avg_risk_score=avg_risk,
        high_risk_count=int(score_result[1] or 0),
        medium_risk_count=int(score_result[2] or 0),
        low_risk_count=int(score_result[3] or 0),
    )

    # ── Top alerts (most frequent rule violations) ──
    if doc_filter:
        alerts_q = (
            select(Analysis.alerts)
            .join(Document, Analysis.document_id == Document.id)
            .where(*doc_filter)
        )
    else:
        alerts_q = select(Analysis.alerts)

    alerts_result = (await db.execute(alerts_q)).scalars().all()

    rule_counter: Counter = Counter()
    severity_acc: dict[str, list[float]] = {}

    for alerts_list in alerts_result:
        if not isinstance(alerts_list, list):
            continue
        for alert in alerts_list:
            if not isinstance(alert, dict):
                continue
            name = alert.get("rule_name", "Desconhecida")
            severity = alert.get("severity", "medium")
            rule_counter[name] += 1
            severity_acc.setdefault(name, []).append(_SEVERITY_WEIGHT.get(severity, 2.0))

    top_alerts = [
        AlertFrequency(
            rule_name=name,
            count=count,
            avg_severity_weight=round(sum(severity_acc.get(name, [2.0])) / max(len(severity_acc.get(name, [1])), 1), 2),
        )
        for name, count in rule_counter.most_common(10)
    ]

    # ── Risk trend (monthly) ──
    # Agrupa por ano e mes com `extract`, que existe em qualquer dialeto. A versao
    # anterior usava func.to_char, exclusiva do Postgres, e quebrava nos testes.
    ano = func.extract("year", Analysis.analyzed_at)
    mes = func.extract("month", Analysis.analyzed_at)

    trend_q = (
        select(
            ano.label("ano"),
            mes.label("mes"),
            func.avg(Analysis.risk_score).label("avg_score"),
            func.count(Analysis.id).label("doc_count"),
        )
        .join(Document, Analysis.document_id == Document.id)
        .where(*doc_filter)
        .group_by(ano, mes)
        .order_by(ano, mes)
        .limit(12)
    )

    trend_result = (await db.execute(trend_q)).all()
    risk_trend = [
        RiskTrend(
            period=f"{int(row.ano):04d}-{int(row.mes):02d}" if row.ano and row.mes else "unknown",
            avg_risk_score=round(float(row.avg_score), 1) if row.avg_score else 0.0,
            document_count=row.doc_count,
        )
        for row in trend_result
    ]

    return DashboardResponse(
        overview=overview,
        top_alerts=top_alerts,
        risk_trend=risk_trend,
    )


# ─── Feedback ─────────────────────────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit feedback on an analysis result (for scoring calibration)."""
    from app import Analysis, AnalysisFeedback

    # Verify analysis exists
    result = await db.execute(select(Analysis).where(Analysis.id == body.analysis_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Check for existing feedback
    existing = await db.execute(
        select(AnalysisFeedback).where(
            AnalysisFeedback.analysis_id == body.analysis_id,
            AnalysisFeedback.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Você já enviou feedback para esta análise")

    feedback = AnalysisFeedback(
        analysis_id=body.analysis_id,
        user_id=current_user.id,
        rating=body.rating,
        adjusted_score=body.adjusted_score,
        comment=body.comment,
    )
    db.add(feedback)
    await db.flush()

    return FeedbackResponse(
        id=feedback.id,
        analysis_id=feedback.analysis_id,
        user_id=feedback.user_id,
        rating=feedback.rating,
        adjusted_score=feedback.adjusted_score,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


@router.get("/feedback/{analysis_id}", response_model=list[FeedbackResponse])
async def list_feedback(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all feedback for a specific analysis."""
    from app import AnalysisFeedback

    result = await db.execute(
        select(AnalysisFeedback)
        .where(AnalysisFeedback.analysis_id == analysis_id)
        .order_by(AnalysisFeedback.created_at.desc())
    )
    feedbacks = result.scalars().all()

    return [
        FeedbackResponse(
            id=f.id, analysis_id=f.analysis_id, user_id=f.user_id,
            rating=f.rating, adjusted_score=f.adjusted_score,
            comment=f.comment, created_at=f.created_at,
        )
        for f in feedbacks
    ]


# ─── Alert-level Feedback (learning loop) ────────────────────────────────────

@router.post("/feedback/batch", response_model=FeedbackSummary, status_code=201)
async def submit_batch_feedback(
    body: AlertFeedbackBatchCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit overall analysis feedback + per-alert correctness feedback.
    This powers the AI learning loop."""
    from app import Analysis, AnalysisFeedback, AlertFeedback

    # Verify analysis exists
    result = await db.execute(select(Analysis).where(Analysis.id == body.analysis_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    # Create/update overall analysis feedback
    existing_fb = await db.execute(
        select(AnalysisFeedback).where(
            AnalysisFeedback.analysis_id == body.analysis_id,
            AnalysisFeedback.user_id == current_user.id,
        )
    )
    existing = existing_fb.scalar_one_or_none()
    if existing:
        existing.rating = body.rating
        existing.adjusted_score = body.adjusted_score
        existing.comment = body.comment
        analysis_fb = existing
    else:
        analysis_fb = AnalysisFeedback(
            analysis_id=body.analysis_id,
            user_id=current_user.id,
            rating=body.rating,
            adjusted_score=body.adjusted_score,
            comment=body.comment,
        )
        db.add(analysis_fb)
    await db.flush()

    # Save per-alert feedback
    correct_count = 0
    incorrect_count = 0
    for af in body.alerts:
        # upsert: delete existing then insert
        existing_af = await db.execute(
            select(AlertFeedback).where(
                AlertFeedback.analysis_id == body.analysis_id,
                AlertFeedback.alert_index == af.alert_index,
                AlertFeedback.user_id == current_user.id,
            )
        )
        old = existing_af.scalar_one_or_none()
        if old:
            await db.delete(old)
            await db.flush()

        alert_fb = AlertFeedback(
            analysis_id=body.analysis_id,
            user_id=current_user.id,
            alert_index=af.alert_index,
            rule_name=af.rule_name,
            severity=af.severity,
            is_correct=af.is_correct,
            comment=af.comment,
        )
        db.add(alert_fb)
        if af.is_correct:
            correct_count += 1
        else:
            incorrect_count += 1

    await db.flush()

    return FeedbackSummary(
        analysis_feedback_id=analysis_fb.id,
        alert_feedbacks_count=len(body.alerts),
        correct_count=correct_count,
        incorrect_count=incorrect_count,
    )


@router.get("/feedback/alerts/{analysis_id}", response_model=list[AlertFeedbackResponse])
async def list_alert_feedback(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List per-alert feedback for a specific analysis."""
    from app import AlertFeedback

    result = await db.execute(
        select(AlertFeedback)
        .where(AlertFeedback.analysis_id == analysis_id)
        .order_by(AlertFeedback.alert_index)
    )
    feedbacks = result.scalars().all()

    return [
        AlertFeedbackResponse(
            id=f.id, analysis_id=f.analysis_id, user_id=f.user_id,
            alert_index=f.alert_index, rule_name=f.rule_name, severity=f.severity,
            is_correct=f.is_correct, comment=f.comment, created_at=f.created_at,
        )
        for f in feedbacks
    ]
