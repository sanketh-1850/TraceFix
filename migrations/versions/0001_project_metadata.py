"""Create the initial project metadata table only."""

import sqlalchemy as sa
from alembic import op

revision = "0001_project_metadata"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_metadata",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()
        ),
        mysql_charset="utf8mb4",
    )


def downgrade():
    op.drop_table("project_metadata")
