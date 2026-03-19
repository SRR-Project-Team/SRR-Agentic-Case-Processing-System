"""Add chat_quality_metrics table for RAG/CoT observability.

Revision ID: 20260221_0001
Revises: 20260220_0001
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0001"
down_revision = "20260220_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("chat_quality_metrics"):
        return

    op.create_table(
        "chat_quality_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=50), nullable=False),
        sa.Column("user_phone", sa.String(length=20), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=20), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("response_length", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("stream_error", sa.Text(), nullable=True),
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("generation_latency_ms", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("context_relevance", sa.Float(), nullable=True),
        sa.Column("answer_faithfulness", sa.Float(), nullable=True),
        sa.Column("answer_coverage", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("total_docs_retrieved", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("total_docs_used", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("retrieval_metrics", sa.Text(), nullable=True, server_default="[]"),
        sa.Column("thinking_steps", sa.Text(), nullable=True, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("timezone('Asia/Shanghai', now())"),
        ),
        sa.ForeignKeyConstraint(["user_phone"], ["users.phone_number"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_quality_metrics_session", "chat_quality_metrics", ["session_id"])
    op.create_index("idx_chat_quality_metrics_user", "chat_quality_metrics", ["user_phone"])
    op.create_index("idx_chat_quality_metrics_created_at", "chat_quality_metrics", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_chat_quality_metrics_created_at", table_name="chat_quality_metrics")
    op.drop_index("idx_chat_quality_metrics_user", table_name="chat_quality_metrics")
    op.drop_index("idx_chat_quality_metrics_session", table_name="chat_quality_metrics")
    op.drop_table("chat_quality_metrics")
