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
            "a first idea goes live straight away",
            TestClient(app).get(idea_url).status_code == 200,
        )
        check(
            "the live idea is in the feed",
            "Pet guard" in TestClient(app).get("/ideas").text,
        )

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

        check("signature check shown", "UniteIdeas signature on the receipt" in verified.text)
        forged = json.loads(json.dumps(bundle))
        forged["receipt"]["submitted_at_utc"] = "2020-01-01T00:00:00"
        forged_res = owner.post(
            "/verify",
            files={"bundle": ("bundle.json", json.dumps(forged).encode(), "application/json")},
        )
        check("forged receipt time is rejected", "Something does not check out" in forged_res.text)
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

        voted = helper.post(f"/ideas/{idea_id}/vote", data={"direction": "up"}, follow_redirects=False)
        check("upvote accepted", voted.status_code == 303)
        page_after = helper.get(f"/ideas/{idea_id}")
        check("upvoted state shows on the idea page", "vote-up is-on" in page_after.text)
        again = helper.post(
            f"/ideas/{idea_id}/vote", data={"direction": "up"}, headers={"Accept": "application/json"}
        )
        check(
            "upvoting again takes the vote away",
            again.json() == {"score": 0, "my_vote": None},
            again.text,
        )
        down = helper.post(
            f"/ideas/{idea_id}/vote", data={"direction": "down"}, headers={"Accept": "application/json"}
        )
        check("a downvote lowers the score", down.json() == {"score": -1, "my_vote": "down"}, down.text)
        switched = helper.post(
            f"/ideas/{idea_id}/vote", data={"direction": "up"}, headers={"Accept": "application/json"}
        )
        check(
            "switching from down to up swings the score by two",
            switched.json() == {"score": 1, "my_vote": "up"},
            switched.text,
        )
        offsite = helper.post(
            f"/ideas/{idea_id}/vote",
            data={"direction": "up", "next": "https://evil.example/x"},
            follow_redirects=False,
        )
        check(
            "vote redirect never leaves the site",
            offsite.headers["location"].startswith(f"/ideas/{idea_id}"),
            offsite.headers["location"],
        )
        helper.post(f"/ideas/{idea_id}/vote", data={"direction": "up"})  # the offsite check toggled it off; put it back
        check(
            "score badge shows the net score",
            'data-score>1</span>' in helper.get(idea_url).text,
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

        headers = {"Authorization": "Bearer smoke-agent-token"}
        check(
            "agent API rejects a bad token",
            owner.get("/api/agent/ping", headers={"Authorization": "Bearer nope"}).status_code == 403,
        )
        check("agent API rejects a missing token", anon.get("/api/agent/ping").status_code == 401)
        ping = owner.get("/api/agent/ping", headers=headers).json()
        check(
            "agent API answers a valid token as AgentBob",
            ping["agent"] == "AgentBob (AI)" and ping["user_id"] == "user-agentbob",
            str(ping),
        )
        check("the POC request button is gone", "Request a POC" not in owner.get(idea_url).text)
        check("the old POC route is gone", owner.post(f"/ideas/{idea_id}/request-poc").status_code in {404, 405})
        check("the old build queue is gone", owner.get("/api/agent/queue", headers=headers).status_code == 404)

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
                "custom_skills": ["Beekeeping", "Gun smuggling logistics"],
                "profile_public": "1",
            },
            follow_redirects=True,
        )
        check("profile saved", "Profile saved" in saved.text)
        helper_id = helper.get("/profile").text.split("/u/")[1].split('"')[0]
        public = anon.get(f"/u/{helper_id}")
        check("public profile shows skills", "3D modelling" in public.text and "Web development" in public.text)
        check("unknown skills are dropped", "not-a-skill" not in public.text and "bogus" not in public.text)
        check("an acceptable custom skill is shown", "Beekeeping" in public.text)
        check("a custom skill on a blocked topic is held back", "smuggling" not in public.text)
        queue_page = owner.get("/moderation").text
        check("the held custom skill reaches the moderator queue", "Gun smuggling logistics" in queue_page and "Held by screening" in queue_page)
        held_id = queue_page.split("/moderation/screening/")[1].split("/")[0]
        check("a moderator can approve a held skill", "Decision saved" in owner.post(f"/moderation/screening/{held_id}/approve", follow_redirects=True).text)
        check("an approved held skill is shown", "smuggling" in anon.get(f"/u/{helper_id}").text)
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
        # --- screening ------------------------------------------------------
        from app import screening as scr

        check("clean text passes the word check", scr.check_text("A booking board for neighbours")[0] == "approved")
        check("blocked topics are escalated, not rejected", scr.check_text("Selling an assault rifle online")[0] == "escalated")
        check("innocent words are not flagged", scr.check_text("Drug discovery for rare diseases and a kill switch")[0] == "approved")
        held_idea = owner.post(
            "/submit",
            data={"title": "Explosive growth hacks", "summary": "How to build a homemade bomb at home for fun.",
                  "category": "general", "idea_type": "digital"},
            follow_redirects=False,
        )
        held_idea_id = held_idea.headers["location"].split("?")[0].rsplit("/", 1)[-1]
        check("a flagged idea is held", anon.get(f"/ideas/{held_idea_id}").status_code == 404)
        mq = owner.get("/moderation").text
        check("the held idea shows in the screening queue", "Held by screening (1)" in mq)
        item_id = mq.split("/moderation/screening/")[1].split("/")[0]
        check("a moderator can reject a held idea", "Decision saved" in owner.post(f"/moderation/screening/{item_id}/reject", data={"note": "No"}, follow_redirects=True).text)
        check("a rejected idea stays hidden", anon.get(f"/ideas/{held_idea_id}").status_code == 404)

        os.environ["SCREENING_MODE"] = "agent"
        from app.config import get_settings as _gs
        _gs.cache_clear()
        waiting = owner.post(
            "/submit",
            data={"title": "Seed library for schools", "summary": "Kids swap seeds and grow herbs on the roof.",
                  "category": "education", "idea_type": "physical"},
            follow_redirects=False,
        )
        waiting_id = waiting.headers["location"].split("?")[0].rsplit("/", 1)[-1]
        check("in agent mode a clean idea is live while AgentBob has yet to look", anon.get(f"/ideas/{waiting_id}").status_code == 200)
        nxt = anon.get("/api/agent/screen/next", headers=headers).json()["item"]
        check("AgentBob is offered the waiting item", nxt is not None and "Seed library" in nxt["text"])
        check("the screening API needs the token", anon.get("/api/agent/screen/next").status_code == 401)
        check("AgentBob cannot reject", anon.post(f"/api/agent/screen/{nxt['id']}/decide", headers=headers, json={"verdict": "rejected"}).status_code == 409)
        ok = anon.post(f"/api/agent/screen/{nxt['id']}/decide", headers=headers, json={"verdict": "approved", "reason": "clean"})
        check("AgentBob confirms a clean idea", ok.status_code == 200 and anon.get(f"/ideas/{waiting_id}").status_code == 200)
        check("a decided item cannot be decided again", anon.post(f"/api/agent/screen/{nxt['id']}/decide", headers=headers, json={"verdict": "escalated"}).status_code == 409)
        # AgentBob's second look can pull a live idea back for a moderator
        second = owner.post(
            "/submit",
            data={"title": "Rooftop bee hotels", "summary": "Small hives for solitary bees on city roofs.",
                  "category": "general", "idea_type": "physical"},
            follow_redirects=False,
        )
        second_id = second.headers["location"].split("?")[0].rsplit("/", 1)[-1]
        nxt2 = anon.get("/api/agent/screen/next", headers=headers).json()["item"]
        esc = anon.post(f"/api/agent/screen/{nxt2['id']}/decide", headers=headers, json={"verdict": "escalated", "reason": "unsure"})
        check("AgentBob escalating a live idea hides it", esc.status_code == 200 and anon.get(f"/ideas/{second_id}").status_code == 404)
        check("AgentBob cannot approve what it escalated", anon.post(f"/api/agent/screen/{nxt2['id']}/decide", headers=headers, json={"verdict": "approved"}).status_code == 409)
        check("the escalated idea reaches the moderators", "Rooftop bee hotels" in owner.get("/moderation").text)
        owner.post(f"/moderation/ideas/{second_id}/approve", follow_redirects=True)
        check("a moderator can approve it back to live", anon.get(f"/ideas/{second_id}").status_code == 200)

        # AgentBob can flag an idea like a member report; it cannot do anything else
        flagged = anon.post("/api/agent/flag", headers=headers, json={"idea_id": second_id, "reason": "Looks like an advert"})
        check("AgentBob can flag an idea", flagged.status_code == 200 and not flagged.json()["duplicate"])
        check("flagging twice does not pile up reports", anon.post("/api/agent/flag", headers=headers, json={"idea_id": second_id, "reason": "again"}).json()["duplicate"])
        check("the flag needs the token", anon.post("/api/agent/flag", json={"idea_id": second_id, "reason": "x"}).status_code == 401)
        check("the flag shows for moderators", "Looks like an advert" in owner.get("/moderation").text)
        os.environ["SCREENING_MODE"] = "rules"
        _gs.cache_clear()

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

        # --- SEO and content pages ------------------------------------------
        import json as _json

        for path, needle in (
            ("/about", "About UniteIdeas"),
            ("/how-it-works", "How UniteIdeas works"),
            ("/faq", "Questions people ask"),
            ("/contact", "Contact"),
            ("/categories", "Browse by category"),
            ("/link-ideas", "Link Ideas"),
            ("/connect-teams", "Connect Teams"),
        ):
            r = anon.get(path)
            check(f"{path} renders", r.status_code == 200 and needle in r.text)
        check("home page announces what is coming", "/link-ideas" in anon.get("/").text and "/connect-teams" in anon.get("/").text)
        check("robots.txt hides private areas", "Disallow: /admin" in anon.get("/robots.txt").text and "Sitemap:" in anon.get("/robots.txt").text)
        sm = anon.get("/sitemap.xml")
        check("sitemap is XML", sm.status_code == 200 and sm.text.startswith("<?xml") and "<urlset" in sm.text)
        check("sitemap lists published ideas", f"/ideas/{idea_id}" in sm.text)
        check("sitemap lists static pages", "/how-it-works" in sm.text and "/faq" in sm.text)
        check("sitemap leaves out private pages", "/admin" not in sm.text and "/profile" not in sm.text and "/login" not in sm.text)
        check("login page is noindex", 'content="noindex,nofollow"' in anon.get("/login").text)
        check("admin responses carry X-Robots-Tag", "noindex" in owner.get("/admin").headers.get("x-robots-tag", ""))
        check("home page is indexable", 'content="index,follow"' in anon.get("/").text)
        idea_html = anon.get(idea_url).text
        check("idea page has a canonical link", f'rel="canonical" href="http://testserver/ideas/{idea_id}"' in idea_html)
        check("idea page uses its summary as description", 'name="description" content="A clip-on guard' in idea_html)
        ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', idea_html, re.S)
        check("idea page has structured data", ld is not None and _json.loads(ld.group(1))["@type"] == "CreativeWork")
        faq_ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', anon.get("/faq").text, re.S)
        check("faq has FAQPage structured data", faq_ld is not None and _json.loads(faq_ld.group(1))["@type"] == "FAQPage")
        check("social image is set", "og:image" in idea_html and "og-image.png" in idea_html)
        check("responses are compressed", anon.get("/", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") == "gzip")
        check("static files are cacheable", "max-age" in anon.get("/static/styles.css").headers.get("cache-control", ""))
        check("filtered feed is kept out of search results", "noindex,follow" in anon.get("/ideas?type=physical").text)
        check("category feed gets its own canonical", "ideas?category=pets" in anon.get("/ideas?category=pets").text)

        with SessionLocal() as _db2:
            owner_row = _db2.query(UserRow).filter_by(email="owner@example.com").one()
            from app.models import Idea as IdeaRow
            for n in range(24):
                _db2.add(IdeaRow(owner_id=owner_row.id, title=f"Bulk idea {n}", summary="bulk summary text", status="published"))
            _db2.add(IdeaRow(owner_id=owner_row.id, title="Hidden pending idea", summary="held for review ok", status="pending_review"))
            _db2.commit()
        page1 = anon.get("/ideas?sort=top")
        page2 = anon.get("/ideas?page=2")
        check("feed is paginated", "More ideas" in page1.text and "Page 2 of" in page2.text)
        check("page two has a canonical and a prev link", "page=2" in page2.text and 'rel="prev"' in page2.text)
        check("pending ideas are not in the sitemap", "Hidden pending" not in anon.get("/sitemap.xml").text)
        check("a page past the end shows the last page", anon.get("/ideas?page=99").status_code == 200)

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

    check_tier1()
    check_base_url_resolution()
    print(f"\n{len(PASSED)} checks passed")


def _reset_rates() -> None:
    from sqlalchemy import delete

    from app.db import SessionLocal
    from app.models import RateEvent

    with SessionLocal() as db:
        db.execute(delete(RateEvent))
        db.commit()


def _login_link(client: TestClient, email: str, name: str = "") -> str:
    response = client.post("/login", data={"email": email, "display_name": name})
    match = LINK_RE.search(response.text)
    return html.unescape(match.group(1)).replace("http://testserver", "") if match else ""


def check_tier1() -> None:
    """Rate limits, posting wait, admin account tools, passwords, tour hooks, staff notices."""
    from sqlalchemy import select, update

    from app.db import SessionLocal
    from app.models import AuditLog, Idea, User, utc_now
    from app.passwords import hash_password, verify_password

    _reset_rates()
    with TestClient(app) as admin, TestClient(app) as member, TestClient(app) as anon:
        admin.get(_login_link(admin, "owner@example.com"))
        check("tier1: admin can sign in", "Admin" in admin.get("/").text)

        # --- 1. sign-in rate limiting
        _reset_rates()
        statuses = []
        for _ in range(6):
            r = anon.post("/login", data={"email": "limit@example.com"}, follow_redirects=False)
            statuses.append(r.status_code)
        check("tier1: repeated sign-in requests for one email are limited", statuses[:5] == [200] * 5 and statuses[5] == 303)
        again = anon.post("/login", data={"email": "limit@example.com"}, follow_redirects=True)
        check("tier1: the limit message says how long to wait", "Too many sign-in requests" in again.text and "minutes" in again.text)
        _reset_rates()
        for _ in range(21):
            anon.get("/auth/verify?token=bogus", follow_redirects=False)
        blocked = anon.get("/auth/verify?token=bogus", follow_redirects=True)
        check("tier1: guessing sign-in tokens is limited", "Too many attempts" in blocked.text)
        _reset_rates()

        # --- 5. passwords
        link = _login_link(member, "pw@example.com", "Pat Word")
        member.get(link)
        check("tier1: password page needs sign-in", anon.get("/profile/password", follow_redirects=False).status_code in {303, 401})
        check("tier1: password page renders", "Set a password" in member.get("/profile/password").text)
        short = member.post("/profile/password", data={"new_password": "short", "confirm_password": "short"}, follow_redirects=True)
        check("tier1: short passwords are refused", "at least 10 characters" in short.text)
        mismatch = member.post("/profile/password", data={"new_password": "a-long-password-1", "confirm_password": "different-long-1"}, follow_redirects=True)
        check("tier1: mismatched passwords are refused", "do not match" in mismatch.text)
        saved = member.post("/profile/password", data={"new_password": "a-long-password-1", "confirm_password": "a-long-password-1"}, follow_redirects=True)
        check("tier1: a password can be set", "Password saved" in saved.text)
        with SessionLocal() as db:
            stored = db.scalar(select(User.password_hash).where(User.email == "pw@example.com"))
        check("tier1: the password is stored hashed, never as typed", stored.startswith("scrypt$") and "a-long-password-1" not in stored)
        check("tier1: hash verifies only the right password", verify_password("a-long-password-1", stored) and not verify_password("nope-nope-nope", stored))
        check("tier1: unknown accounts verify false", not verify_password("anything-at-all", None))
        with TestClient(app) as fresh:
            ok = fresh.post("/login/password", data={"email": "pw@example.com", "password": "a-long-password-1"}, follow_redirects=False)
            check("tier1: signing in with the password works", ok.status_code == 303 and "ui_session" in ok.headers.get("set-cookie", ""))
            fresh.cookies.clear()
            one = fresh.post("/login", data={"email": "pw@example.com", "password": "a-long-password-1"}, follow_redirects=False)
            check("tier1: the single Login button signs in with a password", one.status_code == 303 and "ui_session" in one.headers.get("set-cookie", ""))
            fresh.cookies.clear()
            blank = fresh.post("/login", data={"email": "pw@example.com", "password": ""})
            check("tier1: the single Login button sends a link when the password is blank", "/auth/verify?token=" in blank.text)
            fresh.cookies.clear()
            bad = fresh.post("/login/password", data={"email": "pw@example.com", "password": "wrong-wrong-wrong"}, follow_redirects=True)
            check("tier1: a wrong password is refused without saying which part was wrong", "Email or password is not right" in bad.text)
            nouser = fresh.post("/login/password", data={"email": "nobody@example.com", "password": "wrong-wrong-wrong"}, follow_redirects=True)
            check("tier1: an unknown email gets the same message", "Email or password is not right" in nouser.text)
            for _ in range(8):
                fresh.post("/login/password", data={"email": "pw@example.com", "password": "wrong-wrong-wrong"})
            locked = fresh.post("/login/password", data={"email": "pw@example.com", "password": "a-long-password-1"}, follow_redirects=True)
            check("tier1: too many wrong passwords locks password sign-in for a while", "Too many wrong passwords" in locked.text)
        _reset_rates()
        check("tier1: the emailed link still works for a member with a password", bool(_login_link(anon, "pw@example.com")))
        _reset_rates()
        change = member.post("/profile/password", data={"current_password": "bad-bad-bad-bad", "new_password": "another-long-pw-2", "confirm_password": "another-long-pw-2"}, follow_redirects=True)
        check("tier1: changing a password needs the current one", "current password is not right" in change.text)
        removed = member.post("/profile/password/remove", data={"current_password": "a-long-password-1"}, follow_redirects=True)
        check("tier1: a password can be removed", "Password removed" in removed.text)

        # --- 2. posting limit
        def post(client: TestClient, title: str):
            return client.post(
                "/submit",
                data={"title": title, "summary": "A summary that is long enough to pass.", "public_body": "Body text kept in the draft."},
                follow_redirects=False,
            )

        member.post("/onboarding/complete")
        first = post(member, "First idea of the day")
        check("tier1: a first idea is accepted straight away", first.status_code == 303 and "/ideas/" in first.headers["location"])
        second = post(member, "Second idea too soon")
        check("tier1: a second idea straight after is held back", second.status_code == 429)
        check("tier1: the wait is shown and the draft kept", "You can post your next idea in about" in second.text and "Second idea too soon" in second.text and "Body text kept in the draft." in second.text)
        check("tier1: the form page shows the wait too", "You can post your next idea in about" in member.get("/submit").text)
        with SessionLocal() as db:
            db.execute(update(Idea).where(Idea.title == "First idea of the day").values(created_at=utc_now().replace(year=utc_now().year) - __import__("datetime").timedelta(minutes=45)))
            db.execute(update(User).where(User.email == "pw@example.com").values(created_at=utc_now() - __import__("datetime").timedelta(days=30)))
            db.commit()
        check("tier1: the wait ends once the time has passed", post(member, "Second idea after waiting").status_code == 303)
        third = post(member, "Third idea soon after")
        check("tier1: the wait grows with each idea in a day", third.status_code == 429 and "minutes" in third.text)
        for n in range(3):
            check(f"tier1: admins are not held back ({n + 1})", post(admin, f"Admin idea {n}").status_code == 303)

        # --- 3. admin creates accounts
        check("tier1: members cannot open the create-account page", member.get("/admin/users/new", follow_redirects=False).status_code in {303, 401, 403})
        check("tier1: admin sees the create-account page", "Create an account" in admin.get("/admin/users/new").text)
        made = admin.post("/admin/users/new", data={"email": "newbie@example.com", "display_name": "New Bie", "role": "user"})
        check("tier1: admin creates an account and gets the sign-in link", "Account created" in made.text and "/auth/verify?token=" in made.text)
        dup = admin.post("/admin/users/new", data={"email": "newbie@example.com"}, follow_redirects=True)
        check("tier1: duplicate accounts are refused", "already exists" in dup.text)
        reserved = admin.post("/admin/users/new", data={"email": "agentbob@system.invalid"}, follow_redirects=True)
        check("tier1: bad or reserved emails are refused", "valid email" in reserved.text or "reserved" in reserved.text)
        with TestClient(app) as invited:
            invited_link = html.unescape(LINK_RE.search(made.text).group(1)).replace("http://testserver", "")
            check("tier1: the invited person signs in with the link", invited.get(invited_link).status_code == 200)
            with SessionLocal() as db:
                row = db.scalar(select(User).where(User.email == "newbie@example.com"))
            check("tier1: terms are accepted at first sign-in", bool(row.terms_version) and row.terms_accepted_at is not None)

        # --- 4. admin delete, bulk suspend and delete
        for name in ("spam1", "spam2", "spam3"):
            with TestClient(app) as sp:
                _reset_rates()
                sp.get(_login_link(sp, f"{name}@example.com", name))
                post(sp, f"Buy pills now {name}")
        with SessionLocal() as db:
            ids = {u.email: u.id for u in db.scalars(select(User)).all()}
        check("tier1: admin lists ideas", "Buy pills now spam1" in admin.get("/admin/ideas").text)
        check("tier1: admin can search ideas by owner email", "Buy pills now spam2" in admin.get("/admin/ideas?q=spam2@example.com").text)
        sus = admin.post("/admin/users/bulk", data={"action": "suspend", "ids": [ids["spam1@example.com"], ids["spam2@example.com"]], "reason": "spam"}, follow_redirects=True)
        check("tier1: bulk suspend works", "2 account(s) suspended" in sus.text)
        nores = admin.post("/admin/users/bulk", data={"action": "suspend", "ids": [ids["spam3@example.com"]]}, follow_redirects=True)
        check("tier1: bulk suspend needs a reason", "Give a reason" in nores.text)
        with TestClient(app) as sp:
            _reset_rates()
            check("tier1: suspended members cannot sign in", "suspended" in sp.get(_login_link(sp, "spam1@example.com"), follow_redirects=True).text)
        protect = admin.post("/admin/users/bulk", data={"action": "delete", "ids": [ids["owner@example.com"]]}, follow_redirects=True)
        check("tier1: admins and yourself cannot be bulk-deleted", "protected" in protect.text)
        ask = admin.post("/admin/users/bulk", data={"action": "delete", "ids": [ids["spam1@example.com"], ids["spam2@example.com"], ids["spam3@example.com"]]})
        check("tier1: deleting asks for confirmation first", "Type DELETE" in ask.text and "spam3@example.com" in ask.text)
        with SessionLocal() as db:
            check("tier1: nothing is deleted before confirming", db.scalar(select(User).where(User.email == "spam3@example.com")) is not None)
        wrong = admin.post("/admin/users/bulk", data={"action": "delete", "confirm": "delete", "ids": [ids["spam3@example.com"]]})
        check("tier1: a wrong confirmation does not delete", "Type DELETE" in wrong.text)
        gone = admin.post("/admin/users/bulk", data={"action": "delete", "confirm": "DELETE", "ids": [ids["spam1@example.com"], ids["spam2@example.com"], ids["spam3@example.com"]]}, follow_redirects=True)
        check("tier1: bulk delete removes accounts and their ideas", "3 account(s) and 3 idea(s) deleted" in gone.text)
        with SessionLocal() as db:
            check("tier1: the accounts and ideas are really gone", db.scalar(select(User).where(User.email == "spam1@example.com")) is None and db.scalar(select(Idea).where(Idea.title.like("Buy pills%"))) is None)
            check("tier1: deletions are in the audit log", db.scalar(select(AuditLog).where(AuditLog.action == "user.delete")) is not None)
        victim = admin.get("/admin/ideas?q=Second idea").text
        idea_id = re.search(r'name="ids" value="(idea[^"]+)"', victim).group(1)
        askidea = admin.post("/admin/ideas/bulk", data={"ids": [idea_id]})
        check("tier1: deleting an idea asks for confirmation", "Type DELETE" in askidea.text)
        done = admin.post("/admin/ideas/bulk", data={"ids": [idea_id], "confirm": "DELETE"}, follow_redirects=True)
        check("tier1: an idea can be deleted on its own", "1 idea(s) deleted" in done.text)
        check("tier1: members cannot use bulk delete", member.post("/admin/users/bulk", data={"action": "delete", "confirm": "DELETE", "ids": [ids["pw@example.com"]]}, follow_redirects=False).status_code in {303, 401, 403})

        # --- requests to join
        _reset_rates()
        check("tier2: the request-to-join form renders", "Ask to join" in anon.get("/request-invite").text)
        got = anon.post("/request-invite", data={"email": "friend@example.com", "name": "Fran", "about": "I have an idea"})
        check("tier2: a request is accepted", "we have your request" in got.text)
        anon.post("/request-invite", data={"email": "friend@example.com", "name": "Fran"})
        bot = anon.post("/request-invite", data={"email": "botty@example.com", "website": "http://spam"})
        check("tier2: bots that fill the hidden field get no record", "we have your request" in bot.text)
        page = admin.get("/admin/requests").text
        check("tier2: admin sees the request once, not the bot", page.count("friend@example.com") == 1 and "botty@example.com" not in page)
        check("tier2: members cannot see requests", member.get("/admin/requests", follow_redirects=False).status_code in {303, 401, 403})
        with SessionLocal() as db:
            from app.models import InviteRequest
            rid = db.scalar(select(InviteRequest.id).where(InviteRequest.email == "friend@example.com"))
        invited_resp = admin.post(f"/admin/requests/{rid}/invite")
        check("tier2: inviting creates the account and shows the link", "Account created" in invited_resp.text and "/auth/verify?token=" in invited_resp.text)
        check("tier2: an invited request cannot be invited twice", "already handled" in admin.post(f"/admin/requests/{rid}/invite", follow_redirects=True).text)
        for _ in range(6):
            anon.post("/request-invite", data={"email": "x@example.com"})
        check("tier2: the request form is rate limited", "Too many requests" in anon.post("/request-invite", data={"email": "y@example.com"}, follow_redirects=True).text)
        _reset_rates()
        from app import config as _config
        _config.get_settings.cache_clear()
        os.environ["SIGNUP_MODE"] = "invite"
        with TestClient(app) as inv:
            check("tier2: invite mode refuses unknown emails", "Ask to join" in inv.post("/login", data={"email": "stranger@example.com"}, follow_redirects=True).text)
            check("tier2: invite mode still lets known emails in", "/auth/verify?token=" in inv.post("/login", data={"email": "friend@example.com"}).text)
        os.environ["SIGNUP_MODE"] = "open"
        _config.get_settings.cache_clear()
        _reset_rates()

        # --- 6. tour hooks
        page = member.get("/onboarding").text
        check("tier1: the tour has a start button and script", 'id="tour-start"' in page and "/static/tour.js" in page)
        check("tier1: the real nav buttons carry tour markers", all(f'data-tour="{k}"' in page for k in ("submit", "ideas", "verify", "profile", "theme", "finish")))
        check("tier1: the tour script is served", member.get("/static/tour.js").status_code == 200)

        # --- 7. staff notices
        outbox = Path(os.environ["OUTBOX_DIR"])
        for f in outbox.glob("*"):
            f.unlink()
        _reset_rates()
        with TestClient(app) as sp:
            sp.get(_login_link(sp, "bad@example.com", "Bad Actor"))
            sp.post("/submit", data={"title": "Selling counterfeit passports", "summary": "Fake passports and counterfeit documents for sale.", "public_body": "counterfeit"})
        sent = [f.read_text() for f in outbox.glob("*owner_at_example.com*")]
        check("tier1: staff are emailed when something is held", any("waiting for review" in t for t in sent), str(len(sent)))
        count_before = len(list(outbox.glob("*owner_at_example.com*")))
        with TestClient(app) as sp2:
            sp2.get(_login_link(sp2, "bad2@example.com", "Bad Two"))
            sp2.post("/submit", data={"title": "More counterfeit passports", "summary": "Fake passports and counterfeit documents for sale.", "public_body": "counterfeit"})
        check("tier1: a second notice of the same kind is throttled", len(list(outbox.glob("*owner_at_example.com*"))) == count_before)


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

        from app.glow import levels_for

        check("the most voted idea glows brightest, the least dimmest", levels_for([100, 10, 1]) == [10, 6, 1])
        check("ideas with no positive votes stay dim", levels_for([0, 0, -2]) == [1, 1, 1])
        check("tied ideas share a level", len(set(levels_for([3, 3, 3, 1, 0])[:3])) == 1)
        check("a full board spreads across all ten levels", sorted(set(levels_for(list(range(1, 41))))) == list(range(1, 11)))
    finally:
        os.environ["PUBLIC_BASE_URL"] = pinned
        config.get_settings.cache_clear()


if __name__ == "__main__":
    main()
