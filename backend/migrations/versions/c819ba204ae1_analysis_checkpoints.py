"""Durable bounded analysis request checkpoints. No existing records are changed."""

import sqlalchemy as sa
from alembic import op

revision = "c819ba204ae1"
down_revision = "b730a1410f91"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analysis_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_checkpoints_job_id", "analysis_checkpoints", ["job_id"])
    op.create_index("ix_analysis_checkpoints_request_hash", "analysis_checkpoints", ["request_hash"])


def downgrade():
    op.drop_table("analysis_checkpoints")
