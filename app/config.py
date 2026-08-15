"""Environment-backed settings for UniteIdeas."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ALLOWED_UPLOAD_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    public_base_url: str
    secret_key: str
    db_path: Path
    upload_dir: Path
    outbox_dir: Path
    agent_api_token: str | None
    dev_show_magic_link: bool
    magic_link_ttl_minutes: int
    max_pledge_hours_per_week: int
    soft_pledge_hours_per_week: int

    @property
    def agent_api_configured(self) -> bool:
        return bool(self.agent_api_token)


@lru_cache
def get_settings() -> Settings:
    db_path = ROOT / os.getenv("DB_PATH", "data/uniteideas.db")
    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8100")),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://10.0.0.5:8100").rstrip("/"),
        secret_key=os.getenv("SECRET_KEY", "dev-only-change-me"),
        db_path=db_path,
        upload_dir=ROOT / os.getenv("UPLOAD_DIR", "data/uploads"),
        outbox_dir=ROOT / os.getenv("OUTBOX_DIR", "data/outbox"),
        agent_api_token=os.getenv("AGENT_API_TOKEN") or None,
        dev_show_magic_link=_flag("DEV_SHOW_MAGIC_LINK", "true"),
        magic_link_ttl_minutes=int(os.getenv("MAGIC_LINK_TTL_MINUTES", "30")),
        max_pledge_hours_per_week=int(os.getenv("MAX_PLEDGE_HOURS_PER_WEEK", "40")),
        soft_pledge_hours_per_week=int(os.getenv("SOFT_PLEDGE_HOURS_PER_WEEK", "20")),
    )
