"""Each idea gets a glow level (1 dimmest to 10 brightest), recalculated daily.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ideas") as batch:
        batch.add_column(sa.Column("glow_level", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("ideas") as batch:
        batch.drop_column("glow_level")
