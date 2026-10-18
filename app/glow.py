"""Idea brightness: every published idea glows between level 1 (barely lit) and 10 (brightest).

The level comes from where an idea's score sits among all published ideas, one level per
10% band, so the board always has a full range of light however many votes there are.
It is recalculated once a day (and when the site starts), so the board shifts gently
rather than flickering with every vote.

- Ties share a level (they are ranked by the average position of the tied group).
- An idea with no net positive score stays at level 1.
- With a single idea the level is a calm 6.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Idea, utc_now

logger = logging.getLogger("uniteideas.glow")

LEVELS = 10


def levels_for(scores: list[int]) -> list[int]:
    """Glow level (1..10) for each score, in the same order."""
    n = len(scores)
    if n == 0:
        return []
    if n == 1:
        return [LEVELS // 2 + 1 if scores[0] > 0 else 1]
    ordered = sorted(scores)
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for i, s in enumerate(ordered):
        first.setdefault(s, i)
        last[s] = i
    out = []
    for s in scores:
        if s <= 0:
            out.append(1)
            continue
        rank = (first[s] + last[s]) / 2  # average position of the tie group
        pct = rank / (n - 1)
        out.append(min(LEVELS, int(pct * LEVELS) + 1))
    return out


def recalculate(db: Session) -> int:
    """Recompute every published idea's glow. Returns how many levels changed."""
    ideas = db.scalars(select(Idea).where(Idea.status == "published")).all()
    new_levels = levels_for([i.score for i in ideas])
    changed = 0
    for idea, level in zip(ideas, new_levels):
        if idea.glow_level != level:
            idea.glow_level = level
            changed += 1
    db.commit()
    logger.info("glow recalculated for %d ideas (%d changed) at %s", len(ideas), changed, utc_now())
    return changed


def interval_hours() -> float:
    try:
        return max(0.01, float(os.getenv("GLOW_RECALC_HOURS", "24")))
    except ValueError:
        return 24.0


async def worker_loop(session_factory: Callable[[], Session]) -> None:
    """Background task started with the app: recalculate at start, then once a day."""

    def run() -> None:
        db = session_factory()
        try:
            recalculate(db)
        finally:
            db.close()

    while True:
        try:
            await asyncio.to_thread(run)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("glow recalculation failed")
        await asyncio.sleep(interval_hours() * 3600)
