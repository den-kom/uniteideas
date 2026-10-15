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
        "TIMESTAMP_PROVIDER": "none",
    }
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from starlette.datastructures import URL  # noqa: E402

from app.main import app  # noqa: E402
from app.proof import sha256_text  # noqa: E402

PASSED: list[str] = []
LINK_RE = re.compile(r'href="([^"]*/auth/verify\?token=[^"]+)"')


class FakeRequest:
    """Carries only the two attributes base_url_for reads off a real request."""

    def __init__(self, url: str) -> None:
        self.url = URL(url)
        self.base_url = self.url.replace(path="/", query="", fragment="")


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
        check("verification page reports success", "This idea checks out" in verified.text)
        check("registry check passed", verified.text.count("passed.") >= 3, verified.text[:400])
        anon_lookup = TestClient(app)
        by_id = anon_lookup.get(f"/verify?q={idea_id}")
        check("anyone can look up an idea by id", "This idea checks out" in by_id.text)
        check("lookup shows the public idea title", "Pet guard for office chair wheels" in by_id.text)
        by_link = anon_lookup.get(f"/verify?q=http://10.0.0.5:8100/ideas/{idea_id}")
        check("lookup accepts a pasted link", "This idea checks out" in by_link.text)
        by_hash = anon_lookup.get(f"/verify?q={bundle['receipt']['content_hash']}")
        check("lookup accepts a fingerprint", "This idea checks out" in by_hash.text)
        check(
            "unchanged content is checked server-side",
            "unchanged since it was timestamped" in by_id.text,
        )
        missing = anon_lookup.get("/verify?q=idea-00000000")
        check("unknown idea says no record found", "No record found" in missing.text)
        canonical_file = anon_lookup.get(f"/ideas/{idea_id}/canonical.json")
        check(
            "canonical file hashes to the fingerprint",
            sha256_text(canonical_file.text) == bundle["receipt"]["content_hash"],
        )
        check(
            "no timestamp file when none was requested",
            anon_lookup.get(f"/ideas/{idea_id}/proof.ots").status_code == 404,
        )
        check("public timestamp shown as not requested", "Not requested" in page.text)

        tampered = json.loads(json.dumps(bundle))
        tampered["canonical_payload"] = tampered["canonical_payload"].replace(
            "Pet guard", "Stolen guard"
        )
        rejected = owner.post(
            "/verify",
            files={"bundle": ("bundle.json", json.dumps(tampered).encode(), "application/json")},
        )
        check("tampered bundle is rejected", "Something does not check out" in rejected.text)

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
        page_after = helper.get(f"/ideas/{idea_id}")
        check("backed state shows on the idea page", "is-on" in page_after.text)
        again = helper.post(
            f"/ideas/{idea_id}/vote", headers={"Accept": "application/json"}
        )
        check(
            "voting again takes the backing away",
            again.json() == {"score": 0, "backed": False},
            again.text,
        )
        back = helper.post(f"/ideas/{idea_id}/vote", headers={"Accept": "application/json"})
        check("backing again restores it", back.json() == {"score": 1, "backed": True}, back.text)
        offsite = helper.post(
            f"/ideas/{idea_id}/vote",
            data={"next": "https://evil.example/x"},
            follow_redirects=False,
        )
        check(
            "vote redirect never leaves the site",
            offsite.headers["location"].startswith(f"/ideas/{idea_id}"),
            offsite.headers["location"],
        )
        helper.post(f"/ideas/{idea_id}/vote")  # back to a backed state for later checks
        check(
            "score is exactly one",
            'data-count>1</span>' in helper.get(idea_url).text,
        )

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

        # --- profiles --------------------------------------------------------
        check("new account is nudged to fill in a profile", "Tell us what you can help with" in helper.get("/").text)
        saved = helper.post(
            "/profile/edit",
            data={
                "display_name": "Willing Helper",
                "headline": "Maker of things",
                "hours_per_week": "6",
                "goals": ["join", "bogus-goal"],
                "skills": ["web-dev", "3d-modelling", "not-a-skill"],
                "other_skills": "Beekeeping",
                "profile_public": "1",
            },
            follow_redirects=True,
        )
        check("profile saved", "Profile saved" in saved.text)
        helper_id = helper.get("/profile").text.split("/u/")[1].split('"')[0]
        public = anon.get(f"/u/{helper_id}")
        check("public profile shows skills", "3D modelling" in public.text and "Web development" in public.text)
        check("unknown skills are dropped", "not-a-skill" not in public.text and "bogus" not in public.text)
        check("email is not shown on the profile", "helper@example.com" not in public.text)
        check("banner stops nagging once profiled", "Tell us what you can help with" not in helper.get("/").text)
        helper.post(
            "/profile/edit",
            data={"display_name": "Willing Helper", "skills": ["web-dev"]},
        )
        check("a private profile is hidden from visitors", anon.get(f"/u/{helper_id}").status_code == 404)
        check("a private profile is visible to its owner", helper.get(f"/u/{helper_id}").status_code == 200)
        check(
            "skills can be removed",
            "3D modelling" not in helper.get(f"/u/{helper_id}").text,
        )
        bot = anon.get("/u/user-agentbob")
        check("AgentBob has a public profile marked as a robot", bot.status_code == 200 and "robot" in bot.text)
        refused = anon.post("/login", data={"email": "agentbob@system.invalid"}, follow_redirects=False)
        check("AgentBob cannot sign in", "cannot+sign+in" in refused.headers.get("location", ""))

        # --- legal pages -----------------------------------------------------
        for path, needle in (("/terms", "Terms of use"), ("/privacy", "Privacy policy"), ("/community-rules", "Community rules")):
            page_text = anon.get(path)
            check(f"{path} renders", page_text.status_code == 200 and needle in page_text.text)
            check(f"{path} is marked as a draft", "not legal advice" in page_text.text)
        check("sign-up links to the terms", "/terms" in anon.get("/login").text)
        from app.db import SessionLocal  # noqa: E402
        from app.models import User as UserRow  # noqa: E402

        with SessionLocal() as _db:
            _owner = _db.query(UserRow).filter_by(email="owner@example.com").one()
            check(
                "acceptance of the terms is recorded at sign-up",
                _owner.terms_version.startswith("draft-") and _owner.terms_accepted_at is not None,
            )
        check("footer links to the legal pages", "/privacy" in anon.get("/").text)

        # --- roles, audit, suspension ----------------------------------------
        def status(client, path):
            return client.get(path, follow_redirects=False).status_code

        check("a member cannot open the moderation queue", status(helper, "/moderation") == 403)
        check("a member cannot open the admin area", status(helper, "/admin") == 403)

        with TestClient(app) as mod:
            sign_in(mod, "mod@example.com", "Mo Derator")
            mod_id = mod.get("/profile").text.split("/u/")[1].split('"')[0]
            check("a new account starts as a plain member", status(mod, "/moderation") == 403)
            promoted = owner.post(
                f"/admin/users/{mod_id}/role", data={"role": "moderator"}, follow_redirects=True
            )
            check("admin can promote a moderator", "Role updated" in promoted.text)
            check("moderator can open the queue", status(mod, "/moderation") == 200)
            check("moderator cannot open the admin home", status(mod, "/admin") == 403)
            check("moderator cannot list accounts", status(mod, "/admin/users") == 403)
            check("moderator cannot read the audit log", status(mod, "/admin/audit") == 403)
            check("moderator cannot change roles", mod.post(f"/admin/users/{mod_id}/role", data={"role": "admin"}).status_code == 403)
            check("moderator cannot suspend accounts", mod.post(f"/admin/users/{mod_id}/status", data={"action": "suspend", "reason": "x"}).status_code == 403)

            check("sealed text is not shown to staff just by browsing", "Injection-moulded TPU" not in mod.get(idea_url).text)
            review = mod.get(f"/moderation/ideas/{idea_id}/sealed")
            check("staff can open the logged sealed review", review.status_code == 200 and "Injection-moulded TPU" in review.text)
            check("a member cannot use the sealed review", status(helper, f"/moderation/ideas/{idea_id}/sealed") == 403)
            attachment_id = re.search(r"/files/(file-[0-9a-f]+)", mod.get(idea_url).text).group(1)
            check("staff can open a private attachment", mod.get(f"/files/{attachment_id}").status_code == 200)

            audit_page = owner.get("/admin/audit").text
            check("role change is in the audit log", "user.role_change" in audit_page and "user to moderator" in audit_page)
            check("sealed view is in the audit log", "sealed.viewed" in audit_page)
            check("attachment view is in the audit log", "attachment.viewed" in audit_page)
            check("audit log can be filtered", "sealed.viewed" in owner.get("/admin/audit?action=sealed.viewed").text and "user.role_change" not in owner.get("/admin/audit?action=sealed.viewed").text.split("<tbody>")[1])

            check("admin home loads", status(owner, "/admin") == 200)
            check("timestamp page loads", status(owner, "/admin/timestamps") == 200)
            check("user search works", "Mo Derator" in owner.get("/admin/users?q=mo+der").text and "Willing Helper" not in owner.get("/admin/users?q=mo+der").text)

            blank = owner.post(f"/admin/users/{mod_id}/status", data={"action": "suspend", "reason": " "}, follow_redirects=True)
            check("suspension needs a reason", "Give a reason" in blank.text)
            owner.post(f"/admin/users/{mod_id}/status", data={"action": "suspend", "reason": "Spam in comments"})
            check("a suspended moderator loses access", status(mod, "/moderation") in {303, 401})
            link_page = TestClient(app).post("/login", data={"email": "mod@example.com"})
            relink = html.unescape(LINK_RE.search(link_page.text).group(1)).replace("http://testserver", "")
            back = TestClient(app).get(relink, follow_redirects=False)
            check("a suspended account cannot sign back in", "suspended" in back.headers.get("location", ""))
            check("suspension is in the audit log with its reason", "Spam in comments" in owner.get("/admin/audit").text)
            owner.post(f"/admin/users/{mod_id}/status", data={"action": "reactivate"})
            check("a reactivated moderator works again", status(mod, "/moderation") == 200)

        me = owner.get("/profile").text.split("/u/")[1].split('"')[0]
        own = owner.post(f"/admin/users/{me}/role", data={"role": "user"}, follow_redirects=True)
        check("an admin cannot demote themselves", "cannot remove your own admin role" in own.text)
        check("an admin cannot suspend themselves", "cannot suspend yourself" in owner.post(f"/admin/users/{me}/status", data={"action": "suspend", "reason": "x"}, follow_redirects=True).text)
        bot_role = owner.post("/admin/users/user-agentbob/role", data={"role": "admin"}, follow_redirects=True)
        check("robot accounts cannot be edited", "Robot accounts cannot be changed" in bot_role.text)

    check_base_url_resolution()
    print(f"\n{len(PASSED)} checks passed")


def check_base_url_resolution() -> None:
    """Sign-in links must come back to whichever host you are actually using.

    A branch preview runs on its own port with no .env, so a link built from a
    hard-coded base URL would send you to the live site with a token only the
    preview knows about. These checks pin that behaviour down, including the
    refusal that stops a public deployment trusting a client-supplied Host.
    """
    from app import config

    def resolve(url: str) -> str:
        config.get_settings.cache_clear()
        try:
            return config.base_url_for(FakeRequest(url))
        finally:
            config.get_settings.cache_clear()

    check("a pinned base url wins over the request", resolve("http://10.0.0.5:9999/login") == "http://testserver")

    pinned, os.environ["PUBLIC_BASE_URL"] = os.environ["PUBLIC_BASE_URL"], ""
    try:
        check(
            "an unpinned preview builds links on its own port",
            resolve("http://10.0.0.5:8101/login") == "http://10.0.0.5:8101",
        )
        check(
            "an unpinned localhost preview works too",
            resolve("http://127.0.0.1:8102/login") == "http://127.0.0.1:8102",
        )
        try:
            resolve("http://uniteideas.org/login")
            check("an unpinned public host is refused", False, "it built a link anyway")
        except RuntimeError as exc:
            check("an unpinned public host is refused", "PUBLIC_BASE_URL is not set" in str(exc))
    finally:
        os.environ["PUBLIC_BASE_URL"] = pinned
        config.get_settings.cache_clear()


if __name__ == "__main__":
    main()
