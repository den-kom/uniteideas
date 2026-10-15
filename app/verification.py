"""Checking an idea's proof: what UniteIdeas can confirm, and what the public timestamp says."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Idea, IdeaProof
from app.proof import compute_content_hash
from app.sealing import unseal

IDEA_ID_RE = re.compile(r"idea-[0-9a-f]{8}")
HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")


@dataclass
class Check:
    label: str
    state: str  # pass | fail | wait | info
    detail: str = ""


@dataclass
class Verification:
    ok: bool
    checks: list[Check] = field(default_factory=list)
    proof: IdeaProof | None = None
    idea: Idea | None = None  # set only when the idea is public


def canonical_for(idea: Idea) -> tuple[str, str]:
    """(hash, canonical JSON) recomputed from what is stored now."""
    sealed = unseal(idea.sealed_blob) if idea.sealed_blob else ""
    return compute_content_hash(
        title=idea.title,
        summary=idea.summary,
        category=idea.category,
        idea_type=idea.idea_type,
        public_body=idea.public_body,
        sealed_detail=sealed,
        attachment_hashes=[a.sha256 for a in idea.attachments],
    )


def find_proof(db: Session, query: str) -> IdeaProof | None:
    """Accepts an idea link, an idea id, or a 64-character fingerprint."""
    text = query.strip().lower()
    match = IDEA_ID_RE.search(text)
    if match:
        return db.scalar(select(IdeaProof).where(IdeaProof.idea_id == match.group(0)))
    match = HASH_RE.search(text)
    if match:
        return db.scalar(select(IdeaProof).where(IdeaProof.content_hash == match.group(0)))
    return None


def verify(db: Session, proof: IdeaProof) -> Verification:
    idea = db.get(Idea, proof.idea_id)
    public = idea if idea is not None and idea.status == "published" else None
    result = Verification(ok=True, proof=proof, idea=public)
    add = result.checks.append

    add(Check("Fingerprint is on record", "pass", proof.content_hash))
    add(
        Check(
            "Recorded by UniteIdeas",
            "pass",
            proof.created_at.replace(microsecond=0).isoformat(sep=" ") + " UTC",
        )
    )
    if idea is not None:
        unchanged = canonical_for(idea)[0] == proof.content_hash
        add(
            Check(
                "Idea is unchanged since it was timestamped",
                "pass" if unchanged else "fail",
                "The stored text still produces the same fingerprint."
                if unchanged
                else "The stored text no longer matches the fingerprint.",
            )
        )
        if not unchanged:
            result.ok = False

    status = proof.anchor_status
    if status == "confirmed":
        add(
            Check(
                "Public timestamp",
                "pass",
                f"Confirmed in the Bitcoin chain ({proof.anchor_reference}).",
            )
        )
    elif status in {"pending_submit", "pending_confirm"}:
        add(
            Check(
                "Public timestamp",
                "wait",
                "Sent for public timestamping. Bitcoin confirmation usually takes a few hours.",
            )
        )
    elif status == "failed":
        add(Check("Public timestamp", "fail", "Could not be obtained. An admin has been notified."))
        result.ok = False
    else:
        add(Check("Public timestamp", "info", "Not requested for this idea."))
    return result
