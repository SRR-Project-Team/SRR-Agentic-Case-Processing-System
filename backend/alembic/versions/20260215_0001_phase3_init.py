"""phase3 init migration

Revision ID: 20260215_0001
Revises:
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa

# Import models so Base.metadata has all table definitions
from src.database.models import Base

revision = "20260215_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # On fresh database: create all tables first
    if not inspector.has_table("chat_sessions"):
        Base.metadata.create_all(bind=conn)

    # chat_sessions.session_state - add only if missing
    chat_cols = {c["name"] for c in inspector.get_columns("chat_sessions")}
    if "session_state" not in chat_cols:
        with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("session_state", sa.Text(), nullable=True))

    # knowledge_base_files.category - add only if missing
    kb_cols = {c["name"] for c in inspector.get_columns("knowledge_base_files")}
    if "category" not in kb_cols:
        with op.batch_alter_table("knowledge_base_files", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("category", sa.String(length=50), nullable=False, server_default="general")
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table("knowledge_base_files"):
        return
    kb_cols = {c["name"] for c in inspector.get_columns("knowledge_base_files")}
    if "category" in kb_cols:
        with op.batch_alter_table("knowledge_base_files", schema=None) as batch_op:
            batch_op.drop_column("category")

    if not inspector.has_table("chat_sessions"):
        return
    chat_cols = {c["name"] for c in inspector.get_columns("chat_sessions")}
    if "session_state" in chat_cols:
        with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
            batch_op.drop_column("session_state")
