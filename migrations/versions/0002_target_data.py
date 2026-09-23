"""Add synthetic order-support tables without changing optimizer metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0002_target_data"
down_revision = "0001_project_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "target_customers",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
    )
    op.create_table(
        "target_products",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
    )
    op.create_table(
        "target_orders",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column(
            "customer_id", sa.String(16), sa.ForeignKey("target_customers.id"), nullable=False
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("ordered_on", sa.Date(), nullable=False),
        sa.Column("delivered_on", sa.Date(), nullable=True),
        sa.Column("condition", sa.String(24), nullable=False),
    )
    op.create_table(
        "target_order_items",
        sa.Column("order_id", sa.String(16), sa.ForeignKey("target_orders.id"), primary_key=True),
        sa.Column(
            "product_id", sa.String(16), sa.ForeignKey("target_products.id"), primary_key=True
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
    )


def downgrade():
    for table in ("target_order_items", "target_orders", "target_products", "target_customers"):
        op.drop_table(table)
