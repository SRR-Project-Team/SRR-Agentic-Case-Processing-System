"""Add slope maintenance fields for routing fallback.

Revision ID: 20260314_0003
Revises: 20260314_0002
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0003"
down_revision = "20260314_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("slopes"):
        return
    cols = {c["name"] for c in inspector.get_columns("slopes")}

    if "maintenance_responsible" not in cols:
        op.add_column("slopes", sa.Column("maintenance_responsible", sa.Text(), nullable=True))
    if "maintenance_source" not in cols:
        op.add_column("slopes", sa.Column("maintenance_source", sa.String(length=32), nullable=True))
    if "last_verified_at" not in cols:
        op.add_column("slopes", sa.Column("last_verified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("slopes")}

    if "last_verified_at" in cols:
        op.drop_column("slopes", "last_verified_at")
    if "maintenance_source" in cols:
        op.drop_column("slopes", "maintenance_source")
    if "maintenance_responsible" in cols:
        op.drop_column("slopes", "maintenance_responsible")
