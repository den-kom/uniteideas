"""Screening queue for ideas and custom skills; skills gain a status.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_skills") as batch:
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="approved"))
    op.create_table(
        "screen_items",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("ref", sa.String(80), nullable=False),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(40), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_screen_items_kind", "screen_items", ["kind"])
    op.create_index("ix_screen_items_ref", "screen_items", ["ref"])
    op.create_index("ix_screen_items_user_id", "screen_items", ["user_id"])
    op.create_index("ix_screen_items_status", "screen_items", ["status"])


def downgrade() -> None:
    op.drop_table("screen_items")
    with op.batch_alter_table("user_skills") as batch:
        batch.drop_column("status")
