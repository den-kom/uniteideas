#!/usr/bin/env python
"""End-to-end smoke test for the UniteIdeas milestone-1 flow.

Runs against a throwaway SQLite database so it never touches real data.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="uniteideas-smoke-"))
os.environ.update(
    {
        "DB_PATH": str(TMP / "smoke.db"),
        "UPLOAD_DIR": str(TMP / "uploads"),
        "OUTBOX_DIR": str(TMP / "outbox"),
        "SECRET_KEY": "smoke-test-secret",
        "AGENT_API_TOKEN": "smoke-agent-token",
        "PUBLIC_BASE_URL": "http://testserver",
        "DEV_SHOW_MAGIC_LINK": "true",
        "MAX_PLEDGE_HOURS_PER_WEEK": "40",
    }
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.proof import sha256_text  # noqa: E402

PASSED: list[str] = []
LINK_RE = re.compile(r'href="([^"]*/auth/verify\?token=[^"]+)"')


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        print(f"FAIL  {label}" + (f" — {detail}" if detail else ""))
        raise SystemExit(1)
    PASSED.append(label)
    print(f"ok    {label}")


def sign_in(client: TestClient, email: str, display_name: str) -> None:
    response = client.post("/login", data={"email": email, "display_name": display_name})
    check(f"login link issued for {email}", response.status_code == 200)
    match = LINK_RE.search(response.text)
    check("dev magic link present", match is not None)
    link = html.unescape(match.group(1)).replace("http://testserver", "")
    verified = client.get(link)
    check(f"magic link signs in {email}", verified.status_code == 200)


def main() -> None:
    with TestClient(app) as owner, TestClient(app) as helper:
        check("home page renders", owner.get("/").status_code == 200)
        check("health endpoint", owner.get("/api/health").json()["status"] == "ok")
        check(
            "submitting requires sign-in",
            owner.get("/submit", follow_redirects=False).status_code in {303, 401},
        )

        sign_in(owner, "owner@example.com", "Idea Owner")
        owner.post("/onboarding/complete")

        png = b"\x89PNG\r\n\x1a\n" + b"smoke-test-image"
        created = owner.post(
            "/submit",
            data={
                "title": "Pet guard for office chair wheels",
                "summary": "A clip-on guard that stops pets' tails getting caught in chair castors.",
                "category": "Pets",
                "idea_type": "physical",
                "public_body": "My dog's tail got caught in a castor. A ring guard would prevent it.",
                "sealed_detail": "Injection-moulded TPU, 62mm inner diameter, snap-fit over the stem.",
            },
            files={"attachment": ("sketch.png", png, "image/png")},
            follow_redirects=False,
        )
        check("idea submitted", created.status_code == 303, created.text[:200])
        idea_url = created.headers["location"].split("?")[0]
        idea_id = idea_url.rsplit("/", 1)[-1]

        page = owner.get(idea_url)
        check("one-pager renders", page.status_code == 200)
        check("sealed detail visible to owner", "Injection-moulded TPU" in page.text)
        check(
            "first submission is held for review",
            "awaiting a moderator review" in page.text,
        )
        check(
            "held idea is hidden from the public",
            TestClient(app).get(idea_url).status_code == 404,
        )
        check(
            "held idea is absent from the feed",
            "Pet guard" not in TestClient(app).get("/ideas").text,
        )
        published = owner.post(
            f"/moderation/ideas/{idea_id}/approve", follow_redirects=True
        )
        check("moderator approved the first submission", "Idea approved" in published.text)

        bundle = owner.get(f"/ideas/{idea_id}/proof-bundle.json").json()
        recomputed = sha256_text(bundle["canonical_payload"])
        check(
            "proof bundle hash is self-consistent",
            recomputed == bundle["receipt"]["content_hash"],
            f"{recomputed} != {bundle['receipt']['content_hash']}",
        )
        canonical = json.loads(bundle["canonical_payload"])
        check(
            "sealed text is not leaked in the bundle",
            "Injection-moulded" not in bundle["canonical_payload"]
            and len(canonical["sealed_detail_sha256"]) == 64,
        )
        check(
            "attachment hash is bound into the proof",
            canonical["attachments_sha256"] == [hashlib.sha256(png).hexdigest()],
        )

        verified = owner.post(
            "/verify",
            files={"bundle": ("bundle.json", json.dumps(bundle).encode(), "application/json")},
        )
        check("verification page reports success", "Verified" in verified.text)
        check("registry check passed", verified.text.count("PASS") >= 3, verified.text[:400])

        tampered = json.loads(json.dumps(bundle))
        tampered["canonical_payload"] = tampered["canonical_payload"].replace(
            "Pet guard", "Stolen guard"
        )
        rejected = owner.post(
            "/verify",
            files={"bundle": ("bundle.json", json.dumps(tampered).encode(), "application/json")},
        )
        check("tampered bundle is rejected", "Could not verify" in rejected.text)

        anon = TestClient(app)
        public_page = anon.get(idea_url)
        check("one-pager is public", public_page.status_code == 200)
        check(
            "sealed detail hidden from the public",
            "Injection-moulded TPU" not in public_page.text,
        )

        sign_in(helper, "helper@example.com", "Willing Helper")
        helper.post("/onboarding/complete")

        voted = helper.post(f"/ideas/{idea_id}/vote", follow_redirects=False)
        check("upvote accepted", voted.status_code == 303)
        again = helper.post(f"/ideas/{idea_id}/vote", follow_redirects=True)
        check("second upvote refused", "already backed" in again.text)
        check("score is exactly one", "Back this idea (1)" in helper.get(idea_url).text)

        joined = helper.post(
            f"/ideas/{idea_id}/join",
            data={"message": "I can 3D print prototypes.", "pledged_hours_per_week": "6"},
            follow_redirects=True,
        )
        check("join request created", "Request sent" in joined.text)
        duplicate = helper.post(
            f"/ideas/{idea_id}/join",
            data={"message": "again", "pledged_hours_per_week": "6"},
            follow_redirects=True,
        )
        check("duplicate join refused", "already asked to join" in duplicate.text)

        owner_view = owner.get(idea_url)
        join_id = re.search(r'/joins/(join-[0-9a-f]+)/approve', owner_view.text)
        check("owner sees the pending request", join_id is not None)
        approved = owner.post(f"/joins/{join_id.group(1)}/approve", follow_redirects=True)
        check("owner approved the contributor", "Request approved" in approved.text)
        check("roster shows the pledge", "6h/week pledged" in owner.get(idea_url).text)

        reported = helper.post(
            f"/ideas/{idea_id}/report",
            data={"reason": "Testing the moderation queue."},
            follow_redirects=True,
        )
        check("report submitted", "Reported to moderators" in reported.text)
        queue = owner.get("/moderation")
        check("first account is admin and sees the queue", queue.status_code == 200)
        check("report appears in queue", "Testing the moderation queue." in queue.text)
        check("helper cannot see the queue", helper.get("/moderation").status_code == 403)
        check("admin user list renders", owner.get("/admin/users").status_code == 200)

        requested = owner.post(f"/ideas/{idea_id}/request-poc", follow_redirects=True)
        check("POC queued", "POC queued" in requested.text)

        headers = {"Authorization": "Bearer smoke-agent-token"}
        check(
            "agent API rejects a bad token",
            owner.get("/api/agent/queue", headers={"Authorization": "Bearer nope"}).status_code
            == 403,
        )
        jobs = owner.get("/api/agent/queue", headers=headers).json()
        check("agent sees one queued job", jobs["count"] == 1, str(jobs))
        job = jobs["jobs"][0]
        check(
            "agent receives the sealed detail it needs to build",
            "Injection-moulded TPU" in job["sealed_detail"],
        )

        updated = owner.post(
            f"/api/agent/builds/{job['build_id']}",
            headers=headers,
            json={
                "status": "demo_ready",
                "notes": "Static one-pager built and tested.",
                "preview_url": "http://10.0.0.5:8410/",
                "claim": True,
            },
        ).json()
        check("agent reported the demo", updated["status"] == "demo_ready")
        check("demo private by default", updated["is_public"] is False)
        check("owner can see their private demo", "Open the demo" in owner.get(idea_url).text)
        check("public cannot see it yet", "Open the demo" not in anon.get(idea_url).text)

        owner.post(f"/ideas/{idea_id}/demo-visibility", data={"make_public": "1"})
        check("published demo is public", "Open the demo" in anon.get(idea_url).text)

        second = owner.post(
            "/submit",
            data={
                "title": "Shared tool library for apartment blocks",
                "summary": "A booking board so neighbours can lend each other drills and ladders.",
                "category": "home",
                "idea_type": "digital",
                "public_body": "Most drills are used twice a year. Share them per building.",
                "sealed_detail": "",
            },
            files={"attachment": ("none.png", png, "image/png")},
            follow_redirects=False,
        )
        check("second idea accepted", second.status_code == 303)
        second_id = second.headers["location"].split("?")[0].rsplit("/", 1)[-1]
        check(
            "trusted account publishes without review",
            anon.get(f"/ideas/{second_id}").status_code == 200,
        )

        over_cap = helper.post(
            f"/ideas/{second_id}/join",
            data={"message": "I have spare time", "pledged_hours_per_week": "36"},
            follow_redirects=True,
        )
        check("weekly pledge cap enforced", "weekly pledge cap" in over_cap.text)

        check("feed lists the idea", "Pet guard" in anon.get("/ideas?sort=new").text)
        check("type filter works", "Pet guard" in anon.get("/ideas?type=physical").text)
        check("type filter excludes", "Pet guard" not in anon.get("/ideas?type=digital").text)

    print(f"\n{len(PASSED)} checks passed")


if __name__ == "__main__":
    main()
