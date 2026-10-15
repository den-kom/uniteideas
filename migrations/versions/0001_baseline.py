"""Baseline: the schema as it was before migrations existed.

Databases created before Alembic are stamped at this revision by init_db().
New databases are created from the current models and stamped at head.

Revision ID: 0001
Revises:
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
