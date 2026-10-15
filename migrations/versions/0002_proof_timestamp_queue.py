"""Idea proofs: track the external timestamp (queue state, proof file, errors).

Existing proofs are queued so they get an external timestamp too.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idea_proofs") as batch:
        batch.add_column(sa.Column("anchor_status", sa.String(20), nullable=False, server_default="pending_submit"))
        batch.add_column(sa.Column("anchor_proof", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("anchor_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("anchor_next_try_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("anchor_error", sa.String(300), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("idea_proofs") as batch:
        for name in ("anchor_error", "anchor_next_try_at", "anchor_attempts", "anchor_proof", "anchor_status"):
            batch.drop_column(name)
