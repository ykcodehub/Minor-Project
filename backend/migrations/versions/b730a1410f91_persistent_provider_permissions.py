"""Explicit persistent provider permissions; NULL preserves legacy per-analysis consent."""

import sqlalchemy as sa
from alembic import op

revision = "b730a1410f91"
down_revision = "0f439d83280f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("authorized_providers", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("users", "authorized_providers")
