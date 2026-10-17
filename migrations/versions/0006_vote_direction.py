"""Votes become up/down instead of a single backing.

Existing votes were all "backs", so they become upvotes (value=1).

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("votes") as batch:
        batch.add_column(sa.Column("value", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("votes") as batch:
        batch.drop_column("value")
