"""Requests to join (the "ask for an invite" form).

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(80), nullable=False, server_default=""),
        sa.Column("about", sa.String(1000), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_invite_requests_email", "invite_requests", ["email"])
    op.create_index("ix_invite_requests_status", "invite_requests", ["status"])


def downgrade() -> None:
    op.drop_table("invite_requests")
