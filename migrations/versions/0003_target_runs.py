"""Index target executions and correlate them with Langfuse traces."""

import sqlalchemy as sa
from alembic import op

revision = "0003_target_runs"
down_revision = "0002_target_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "target_runs",
        sa.Column("run_id", sa.String(32), primary_key=True),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=True, unique=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("agent_version_id", sa.String(128), nullable=False),
        sa.Column("benchmark_version", sa.String(128), nullable=True),
        sa.Column("dataset_version", sa.String(128), nullable=False),
        sa.Column("split", sa.String(32), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("terminal_reason", sa.String(64), nullable=False),
        sa.Column("telemetry_status", sa.String(32), nullable=False),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_target_runs_target_id", "target_runs", ["target_id"])
    op.create_index("ix_target_runs_task_id", "target_runs", ["task_id"])
    op.create_index("ix_target_runs_agent_version_id", "target_runs", ["agent_version_id"])


def downgrade():
    op.drop_index("ix_target_runs_agent_version_id", table_name="target_runs")
    op.drop_index("ix_target_runs_task_id", table_name="target_runs")
    op.drop_index("ix_target_runs_target_id", table_name="target_runs")
    op.drop_table("target_runs")
