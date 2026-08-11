"""add alert_feedback table

The AlertFeedback model shipped without a matching migration. In development the
tables come from Base.metadata.create_all, so the gap only surfaces in production,
where the missing table aborts the worker's transaction mid-analysis.

Revision ID: 006
Revises: 005
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_index", sa.Integer(), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "alert_index", "user_id", name="uq_alert_fb_per_user"),
    )
    op.create_index("ix_alert_feedback_analysis_id", "alert_feedback", ["analysis_id"])
    op.create_index("ix_alert_feedback_rule_name", "alert_feedback", ["rule_name"])


def downgrade() -> None:
    op.drop_index("ix_alert_feedback_rule_name", table_name="alert_feedback")
    op.drop_index("ix_alert_feedback_analysis_id", table_name="alert_feedback")
    op.drop_table("alert_feedback")
