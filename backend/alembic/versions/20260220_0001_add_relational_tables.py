"""Add relational tables: slopes, tree_inventory, historical_cases.
Also alters tree_inventory_vectors (add tree_no, slope_id, source_row_index;
swap unique index from content_hash to slope+tree+row).

Revision ID: 20260220_0001
Revises: 20260215_0001
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260220_0001"
down_revision = "20260215_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # ------------------------------------------------------------------
    # slopes
    # ------------------------------------------------------------------
    if not inspector.has_table("slopes"):
        op.create_table(
            "slopes",
            sa.Column("slope_no", sa.Text(), nullable=False),
            sa.Column("slope_id", sa.String(16), nullable=False),
            sa.Column("tree_count", sa.Integer(), nullable=True, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("timezone('Asia/Shanghai', now())"),
            ),
            sa.PrimaryKeyConstraint("slope_no"),
            sa.UniqueConstraint("slope_id"),
        )

    # ------------------------------------------------------------------
    # tree_inventory
    # ------------------------------------------------------------------
    if not inspector.has_table("tree_inventory"):
        op.create_table(
            "tree_inventory",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("slope_no", sa.Text(), nullable=False),
            sa.Column("slope_id", sa.String(16), nullable=False),
            sa.Column("tree_no", sa.String(16), nullable=True),
            sa.Column("x", sa.Float(), nullable=True),
            sa.Column("y", sa.Float(), nullable=True),
            sa.Column("scientific_name", sa.Text(), nullable=True),
            sa.Column("chinese_name", sa.Text(), nullable=True),
            sa.Column("height_m", sa.Float(), nullable=True),
            sa.Column("avg_crown_spread_m", sa.Float(), nullable=True),
            sa.Column("dbh_mm", sa.Float(), nullable=True),
            sa.Column("form", sa.Text(), nullable=True),
            sa.Column("triage_color", sa.Text(), nullable=True),
            sa.Column("health", sa.Text(), nullable=True),
            sa.Column("leaning", sa.Text(), nullable=True),
            sa.Column("pest_fungal", sa.Text(), nullable=True),
            sa.Column("defect_trunk", sa.Text(), nullable=True),
            sa.Column("defect_branch_crown", sa.Text(), nullable=True),
            sa.Column("defect_root", sa.Text(), nullable=True),
            sa.Column("classification", sa.Text(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column("mitigation_measures", sa.Text(), nullable=True),
            sa.Column("tree_removed", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("priority_zone", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("large_tree", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("ovt", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("swt", sa.Boolean(), nullable=True, server_default="false"),
            sa.Column("source_row_index", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("timezone('Asia/Shanghai', now())"),
            ),
            sa.ForeignKeyConstraint(["slope_no"], ["slopes.slope_no"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_tree_inv_slope_no", "tree_inventory", ["slope_no"]
        )
        op.create_index(
            "idx_tree_inv_tree_no", "tree_inventory", ["tree_no"]
        )
        op.create_index(
            "idx_tree_inv_slope_id", "tree_inventory", ["slope_id"]
        )
        op.create_index(
            "uq_tree_inv_slope_treeno_row",
            "tree_inventory",
            ["slope_no", sa.text("COALESCE(tree_no, '_NULL_')"), "source_row_index"],
            unique=True,
            postgresql_where=sa.text("TRUE"),
        )

    # ------------------------------------------------------------------
    # historical_cases
    # ------------------------------------------------------------------
    if not inspector.has_table("historical_cases"):
        op.create_table(
            "historical_cases",
            sa.Column("case_id", sa.String(64), nullable=False),
            sa.Column("source", sa.String(32), nullable=False),
            sa.Column("case_number", sa.String(64), nullable=True),
            sa.Column("date_received", sa.Text(), nullable=True),
            sa.Column("venue", sa.Text(), nullable=True),
            sa.Column("district", sa.Text(), nullable=True),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("slope_no", sa.Text(), nullable=True),
            sa.Column("caller_name", sa.Text(), nullable=True),
            sa.Column("contact_no", sa.Text(), nullable=True),
            sa.Column("case_type", sa.Text(), nullable=True),
            sa.Column("nature", sa.Text(), nullable=True),
            sa.Column("subject", sa.Text(), nullable=True),
            sa.Column("inquiry", sa.Text(), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("timezone('Asia/Shanghai', now())"),
            ),
            sa.PrimaryKeyConstraint("case_id"),
        )
        op.create_index(
            "idx_hist_cases_slope_no", "historical_cases", ["slope_no"]
        )
        op.create_index(
            "idx_hist_cases_source", "historical_cases", ["source"]
        )

    # ------------------------------------------------------------------
    # Alter tree_inventory_vectors
    # ------------------------------------------------------------------
    if inspector.has_table("tree_inventory_vectors"):
        vec_cols = {c["name"] for c in inspector.get_columns("tree_inventory_vectors")}
        if "tree_no" not in vec_cols:
            op.add_column(
                "tree_inventory_vectors",
                sa.Column("tree_no", sa.String(16), nullable=True),
            )
        if "slope_id" not in vec_cols:
            op.add_column(
                "tree_inventory_vectors",
                sa.Column("slope_id", sa.String(16), nullable=True),
            )
        if "source_row_index" not in vec_cols:
            op.add_column(
                "tree_inventory_vectors",
                sa.Column("source_row_index", sa.Integer(), nullable=True),
            )

        # Drop old content_hash-based unique index, create new one
        vec_indexes = {idx["name"] for idx in inspector.get_indexes("tree_inventory_vectors")}
        op.drop_index("uq_tree_content_model", table_name="tree_inventory_vectors", if_exists=True)
        if "uq_tree_vec_model_slope_tree_row" not in vec_indexes:
            op.create_index(
                "uq_tree_vec_model_slope_tree_row",
                "tree_inventory_vectors",
                [
                    "embedding_model",
                    "slope_no",
                    sa.text("COALESCE(tree_no, '_NULL_')"),
                    "source_row_index",
                ],
                unique=True,
                postgresql_where=sa.text("TRUE"),
            )
        if "idx_tree_inventory_vec_slope_no" not in vec_indexes:
            op.create_index(
                "idx_tree_inventory_vec_slope_no", "tree_inventory_vectors", ["slope_no"]
            )


def downgrade() -> None:
    # Revert tree_inventory_vectors changes
    op.drop_index("idx_tree_inventory_vec_slope_no", table_name="tree_inventory_vectors")
    op.drop_index("uq_tree_vec_model_slope_tree_row", table_name="tree_inventory_vectors")
    op.create_index(
        "uq_tree_content_model",
        "tree_inventory_vectors",
        ["embedding_model", "content_hash"],
        unique=True,
    )
    op.drop_column("tree_inventory_vectors", "source_row_index")
    op.drop_column("tree_inventory_vectors", "slope_id")
    op.drop_column("tree_inventory_vectors", "tree_no")

    # Drop new tables (order matters for FK)
    op.drop_index("idx_hist_cases_source", table_name="historical_cases")
    op.drop_index("idx_hist_cases_slope_no", table_name="historical_cases")
    op.drop_table("historical_cases")

    op.drop_index("uq_tree_inv_slope_treeno_row", table_name="tree_inventory")
    op.drop_index("idx_tree_inv_slope_id", table_name="tree_inventory")
    op.drop_index("idx_tree_inv_tree_no", table_name="tree_inventory")
    op.drop_index("idx_tree_inv_slope_no", table_name="tree_inventory")
    op.drop_table("tree_inventory")

    op.drop_table("slopes")
