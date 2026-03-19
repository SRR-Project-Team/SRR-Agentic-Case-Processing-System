"""Replace file_hash full unique with partial unique (is_active=true only).

Allows re-uploading the same file after soft-delete: soft-deleted records
no longer block INSERT due to file_hash uniqueness.

Revision ID: 20260319_0001
Revises: 20260316_0001
Create Date: 2026-03-19

"""

from alembic import op
import sqlalchemy as sa


revision = "20260319_0001"
down_revision = "20260316_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Drop existing full unique constraint on file_hash
        op.execute(
            "ALTER TABLE knowledge_base_files "
            "DROP CONSTRAINT IF EXISTS knowledge_base_files_file_hash_key"
        )
        # Create partial unique index: only active records must have unique file_hash
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS knowledge_base_files_file_hash_active_key
            ON knowledge_base_files (file_hash)
            WHERE is_active = true AND file_hash IS NOT NULL
            """
        )
    # SQLite: skip - production uses PostgreSQL; local SQLite keeps original behavior


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "DROP INDEX IF EXISTS knowledge_base_files_file_hash_active_key"
        )
        # Restore full unique constraint (may fail if soft-deleted duplicates exist)
        op.execute(
            """
            ALTER TABLE knowledge_base_files
            ADD CONSTRAINT knowledge_base_files_file_hash_key UNIQUE (file_hash)
            """
        )
    # SQLite: no-op
