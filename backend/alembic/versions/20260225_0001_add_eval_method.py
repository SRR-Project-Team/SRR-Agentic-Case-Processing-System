"""Add eval_method column to chat_quality_metrics.

Revision ID: 20260225_0001
Revises: 20260221_0001
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260225_0001"
down_revision = "20260221_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("chat_quality_metrics"):
        return
    cols = {c["name"] for c in inspector.get_columns("chat_quality_metrics")}
    if "eval_method" in cols:
        return

    op.add_column(
        "chat_quality_metrics",
        sa.Column(
            "eval_method",
            sa.String(length=20),
            nullable=True,
            server_default="keyword_overlap",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_quality_metrics", "eval_method")
