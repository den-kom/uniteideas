"""Proof of authorship: deterministic content hashing plus timestamp receipts.

A proof shows that specific content existed at a specific time, bound to a
verified account. It is evidence, not a patent. The anchor provider is
pluggable so an RFC-3161 timestamping authority can be added without changing
stored records (anchor_provider stays 'local' until then).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable

CANONICAL_VERSION = "uniteideas-proof-v1"
ALGORITHM = "sha256"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_payload(
    *,
    title: str,
    summary: str,
    category: str,
    idea_type: str,
    public_body: str,
    sealed_detail: str,
    attachment_hashes: Iterable[str],
) -> str:
    payload = {
        "version": CANONICAL_VERSION,
        "title": title.strip(),
        "summary": summary.strip(),
        "category": category.strip().lower(),
        "idea_type": idea_type.strip().lower(),
        "public_body": public_body.strip(),
        "sealed_detail_sha256": sha256_text(sealed_detail.strip()) if sealed_detail.strip() else "",
        "attachments_sha256": sorted(attachment_hashes),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_content_hash(**kwargs: Any) -> tuple[str, str]:
    """Return (content_hash, canonical_json)."""
    canonical = canonical_payload(**kwargs)
    return sha256_text(canonical), canonical


def build_receipt(
    *,
    idea_id: str,
    content_hash: str,
    author_display: str,
    author_email_hash: str,
    created_at: datetime,
    anchor_provider: str,
    anchor_reference: str,
    verify_url: str,
) -> dict[str, Any]:
    return {
        "version": CANONICAL_VERSION,
        "algorithm": ALGORITHM,
        "idea_id": idea_id,
        "content_hash": content_hash,
        "author_display": author_display,
        "author_email_sha256": author_email_hash,
        "submitted_at_utc": created_at.replace(microsecond=0).isoformat(),
        "anchor_provider": anchor_provider,
        "anchor_reference": anchor_reference,
        "verify_url": verify_url,
        "disclaimer": (
            "This receipt is evidence that the hashed content existed at the stated "
            "time and was submitted by the named account. It is not a patent, and it "
            "is not legal advice."
        ),
    }
