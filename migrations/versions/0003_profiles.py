"""Profiles: questionnaire answers on users, and a skills table.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("headline", sa.String(120), nullable=False, server_default=""))
        batch.add_column(sa.Column("bio", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("location", sa.String(80), nullable=False, server_default=""))
        batch.add_column(sa.Column("goals", sa.String(200), nullable=False, server_default=""))
        batch.add_column(sa.Column("other_skills", sa.String(300), nullable=False, server_default=""))
        batch.add_column(sa.Column("hours_per_week", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("profile_public", sa.Boolean(), nullable=False, server_default=sa.true()))
        # People who signed up before profiles existed count as "not yet done".
        batch.add_column(sa.Column("profile_done", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "user_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("skill", sa.String(60), nullable=False),
        sa.UniqueConstraint("user_id", "skill", name="uq_user_skill"),
    )
    op.create_index("ix_user_skills_user_id", "user_skills", ["user_id"])
    op.create_index("ix_user_skills_skill", "user_skills", ["skill"])


def downgrade() -> None:
    op.drop_table("user_skills")
    with op.batch_alter_table("users") as batch:
        for name in ("profile_done", "profile_public", "hours_per_week", "other_skills", "goals", "location", "bio", "headline"):
            batch.drop_column(name)
