"""SQLAlchemy engine/session. SQLite now, Postgres later via DATABASE_URL."""

from __future__ import annotations

import os
from typing import Iterator

from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

_settings = get_settings()


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit
    _settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{_settings.db_path}"


_url = _database_url()
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
engine = create_engine(_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


ROOT = Path(__file__).resolve().parents[1]
BASELINE_REVISION = "0001"


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return cfg


def init_db() -> None:
    """Create the schema on a new database, or migrate an existing one to the latest.

    - Brand new database: create every table from the current models, mark it up to date.
    - Database from before migrations existed: mark it as the baseline, then upgrade.
    - Otherwise: apply any migrations it has not seen yet.
    """
    from alembic import command

    from app import models  # noqa: F401 — register mappers

    tables = set(inspect(engine).get_table_names())
    cfg = _alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        if "alembic_version" not in tables:
            if "users" not in tables:
                Base.metadata.create_all(conn)
                command.stamp(cfg, "head")
            else:
                command.stamp(cfg, BASELINE_REVISION)
                command.upgrade(cfg, "head")
        else:
            command.upgrade(cfg, "head")

    from app.system_users import ensure_system_users

    with SessionLocal() as db:
        ensure_system_users(db)
