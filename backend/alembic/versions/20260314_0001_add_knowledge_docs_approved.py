"""Add approved column to knowledge_docs_vectors.

Revision ID: 20260314_0001
Revises: 20260225_0001
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0001"
down_revision = "20260225_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "knowledge_docs_vectors" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("knowledge_docs_vectors")]
        if "approved" not in cols:
            op.add_column(
                "knowledge_docs_vectors",
                sa.Column("approved", sa.Boolean(), nullable=True, server_default=sa.true()),
            )
            op.execute("UPDATE knowledge_docs_vectors SET approved = TRUE WHERE approved IS NULL")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "knowledge_docs_vectors" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("knowledge_docs_vectors")]
        if "approved" in cols:
            op.drop_column("knowledge_docs_vectors", "approved")
