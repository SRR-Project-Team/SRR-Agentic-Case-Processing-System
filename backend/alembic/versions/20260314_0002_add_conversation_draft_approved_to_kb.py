"""Add draft_approved_to_kb to conversation_history.

Revision ID: 20260314_0002
Revises: 20260314_0001
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0002"
down_revision = "20260314_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("conversation_history"):
        return
    cols = {c["name"] for c in inspector.get_columns("conversation_history")}
    if "draft_approved_to_kb" in cols:
        return
    op.add_column(
        "conversation_history",
        sa.Column("draft_approved_to_kb", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("conversation_history", "draft_approved_to_kb")
