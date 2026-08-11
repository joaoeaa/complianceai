"""resolucao do alerta pelo revisor

Revision ID: 009
Revises: 008
Create Date: 2026-08-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RESOLUTION = sa.Enum("to_fix", "not_applicable", "resolved", name="alert_resolution")


def upgrade() -> None:
    RESOLUTION.create(op.get_bind(), checkfirst=True)
    op.add_column("alert_feedback", sa.Column("resolution", RESOLUTION, nullable=True))
    # Marcar um alerta como tratado nao exige opinar se a IA acertou.
    op.alter_column("alert_feedback", "is_correct", existing_type=sa.Boolean(), nullable=True)


def downgrade() -> None:
    op.alter_column("alert_feedback", "is_correct", existing_type=sa.Boolean(), nullable=False)
    op.drop_column("alert_feedback", "resolution")
    RESOLUTION.drop(op.get_bind(), checkfirst=True)
