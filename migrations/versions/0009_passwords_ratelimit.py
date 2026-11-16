"""Optional passwords and the rate-limit event table.

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("password_hash", sa.String(255), nullable=True))
    op.create_table(
        "rate_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bucket", sa.String(40), nullable=False),
        sa.Column("key", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_rate_events_bucket", "rate_events", ["bucket"])
    op.create_index("ix_rate_events_key", "rate_events", ["key"])
    op.create_index("ix_rate_events_created_at", "rate_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("rate_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_hash")
