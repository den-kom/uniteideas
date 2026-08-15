"""Data model for UniteIdeas: users, ideas, proofs, teams, moderation, POC builds."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ROLE_USER = "user"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"
STAFF_ROLES = {ROLE_MODERATOR, ROLE_ADMIN}

IDEA_TYPES = ("digital", "physical")
STATUS_PENDING = "pending_review"
STATUS_PUBLISHED = "published"
STATUS_REMOVED = "removed"
IDEA_STATUS = (STATUS_PENDING, STATUS_PUBLISHED, STATUS_REMOVED)

BUILD_QUEUED = "queued"
BUILD_PLANNING = "planning"
BUILD_BUILDING = "building"
BUILD_TESTING = "testing"
BUILD_DEMO_READY = "demo_ready"
BUILD_FAILED = "failed"
BUILD_ESCALATED = "escalated"
BUILD_STATUSES = (
    BUILD_QUEUED,
    BUILD_PLANNING,
    BUILD_BUILDING,
    BUILD_TESTING,
    BUILD_DEMO_READY,
    BUILD_FAILED,
    BUILD_ESCALATED,
)
# Ordered stages shown on the public one-pager progress bar.
PROGRESS_STAGES = ("submitted", "planning", "building", "testing", "demo_ready")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("user"))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    ideas: Mapped[list["Idea"]] = relationship(back_populates="owner")

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class LoginToken(Base):
    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("idea"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(80), default="general")
    idea_type: Mapped[str] = mapped_column(String(20), default="digital")
    public_body: Mapped[str] = mapped_column(Text, default="")
    sealed_blob: Mapped[str] = mapped_column(Text, default="")
    sealed_revealed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PUBLISHED, index=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    owner: Mapped[User] = relationship(back_populates="ideas")
    proof: Mapped["IdeaProof"] = relationship(back_populates="idea", uselist=False)
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="idea")
    builds: Mapped[list["PocBuild"]] = relationship(back_populates="idea")
    members: Mapped[list["TeamMember"]] = relationship(back_populates="idea")

    @property
    def has_sealed_detail(self) -> bool:
        return bool(self.sealed_blob)

    @property
    def sealed_is_public(self) -> bool:
        return self.sealed_revealed_at is not None

    @property
    def latest_build(self) -> "PocBuild | None":
        if not self.builds:
            return None
        return sorted(self.builds, key=lambda b: b.created_at)[-1]

    @property
    def stage(self) -> str:
        build = self.latest_build
        if build is None:
            return "submitted"
        if build.status in {BUILD_FAILED, BUILD_ESCALATED}:
            return "needs_attention"
        if build.status == BUILD_QUEUED:
            return "submitted"
        return build.status


class IdeaProof(Base):
    __tablename__ = "idea_proofs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("proof"))
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), unique=True, index=True)
    algorithm: Mapped[str] = mapped_column(String(30), default="sha256")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    canonical_version: Mapped[str] = mapped_column(String(40), default="uniteideas-proof-v1")
    author_email_hash: Mapped[str] = mapped_column(String(64))
    anchor_provider: Mapped[str] = mapped_column(String(30), default="local")
    anchor_reference: Mapped[str] = mapped_column(String(200), default="")
    anchored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    idea: Mapped[Idea] = relationship(back_populates="proof")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("file"))
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    idea: Mapped[Idea] = relationship(back_populates="attachments")


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("idea_id", "user_id", name="uq_vote_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class JoinRequest(Base):
    __tablename__ = "join_requests"
    __table_args__ = (UniqueConstraint("idea_id", "user_id", name="uq_join_once"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("join"))
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    pledged_hours_per_week: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("idea_id", "user_id", name="uq_member_once"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("member"))
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role_in_team: Mapped[str] = mapped_column(String(40), default="contributor")
    pledged_hours_per_week: Mapped[int] = mapped_column(Integer, default=1)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    idea: Mapped[Idea] = relationship(back_populates="members")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("report"))
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PocBuild(Base):
    """A POC job owned by UniteIdeas; the Agent System pulls and reports back."""

    __tablename__ = "poc_builds"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: short_id("build"))
    idea_id: Mapped[str] = mapped_column(ForeignKey("ideas.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=BUILD_QUEUED, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    preview_url: Mapped[str] = mapped_column(String(300), default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    idea: Mapped[Idea] = relationship(back_populates="builds")
