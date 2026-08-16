"""Environment-backed settings for UniteIdeas."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Request

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


# Loopback, RFC1918 and the .local/VPN range. Deliberately narrow: see base_url_for.
PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$"
)


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    # The canonical address of the site. Used for durable artefacts such as the
    # verify URL printed into a proof bundle, which must not vary by whichever
    # host happened to serve the download.
    public_base_url: str
    # False when PUBLIC_BASE_URL was left unset, which is how a branch preview
    # running on its own port tells itself apart from the real deployment.
    public_base_url_pinned: bool
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
    pinned = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8100")),
        public_base_url=pinned or "http://10.0.0.5:8100",
        public_base_url_pinned=bool(pinned),
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


def base_url_for(request: Request) -> str:
    """The address to put in a sign-in link.

    Prefers PUBLIC_BASE_URL when it is set. When it is not — which is how an
    AgentBob branch preview runs, since a worktree has no .env — the address is
    taken from the request, so a preview on port 8101 mints links that come back
    to port 8101 instead of sending you to the live site with a token it has
    never heard of.

    Falling back to the request is only safe on a private address. The Host
    header is client-controlled, so on a public deployment an attacker could
    request a link for someone else's account and have the victim emailed a URL
    pointing at a host of the attacker's choosing. Rather than quietly accept
    that, this refuses: pin PUBLIC_BASE_URL in production.
    """
    settings = get_settings()
    if settings.public_base_url_pinned:
        return settings.public_base_url

    host = request.url.hostname or ""
    if PRIVATE_HOST_RE.match(host):
        return str(request.base_url).rstrip("/")

    raise RuntimeError(
        f"PUBLIC_BASE_URL is not set and {host!r} is not a private address, so there "
        "is no trustworthy way to build a sign-in link. Set PUBLIC_BASE_URL to this "
        "site's canonical address."
    )
