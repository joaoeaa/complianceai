"""add analysis feedback table

Revision ID: 005
Revises: 004
Create Date: 2026-02-24

FASE 4 — Inteligência e Diferenciação:
- analysis_feedback: user feedback on analysis results for scoring calibration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_feedback",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),  # 1-5
        sa.Column("adjusted_score", sa.Integer(), nullable=True),  # user-suggested risk score
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "user_id", name="uq_feedback_per_user"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating"),
        sa.CheckConstraint(
            "adjusted_score IS NULL OR (adjusted_score >= 0 AND adjusted_score <= 100)",
            name="ck_feedback_score",
        ),
    )
    op.create_index("ix_feedback_analysis", "analysis_feedback", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("analysis_feedback")
