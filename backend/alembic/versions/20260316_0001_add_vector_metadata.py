"""Add metadata JSONB to vector tables for knowledge_type and entity_id filtering.

Revision ID: 20260316_0001
Revises: 20260314_0003
Create Date: 2026-03-16

"""

from alembic import op
import sqlalchemy as sa


revision = "20260316_0001"
down_revision = "20260314_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)

    for table in ("knowledge_docs_vectors", "historical_cases_vectors", "tree_inventory_vectors"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "metadata" in cols:
            continue
        if dialect == "postgresql":
            op.add_column(
                table,
                sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=True),
            )
        else:
            op.add_column(
                table,
                sa.Column("metadata", sa.Text(), nullable=True),
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in ("knowledge_docs_vectors", "historical_cases_vectors", "tree_inventory_vectors"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "metadata" in cols:
            op.drop_column(table, "metadata")
