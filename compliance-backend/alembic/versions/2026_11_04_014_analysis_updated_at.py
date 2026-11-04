"""ultimo sinal de vida da analise, para detectar analise orfa

A deteccao usava uploaded_at, que nao diz nada sobre uma analise que ainda
roda: uma etapa longa ou uma espera entre tentativas parecia orfa. Esta coluna
muda a cada etapa, tentativa e batimento.

Revision ID: 014
Revises: 013
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("analysis_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "analysis_updated_at")
