# UniteIdeas

Share an idea safely, prove when you shared it, and build it with other people.

Sign up, share a public one-pager with an optional sealed detail, get a receipt and a public
timestamp, back ideas, and form teams. Robots (AgentBob) will help with housekeeping later; see
`docs/REBUILD_PROGRESS.md` for what changed in the 0.3 rebuild.

## Quick start

```bash
cd /home/usrbob/uniteideas
cp .env.example .env          # then set SECRET_KEY, AGENT_API_TOKEN, PUBLIC_BASE_URL
./build.sh                    # create .venv and install
./test.sh                     # end-to-end checks against a throwaway DB
.venv/bin/python scripts/test_timestamping.py   # queue and migration checks
.venv/bin/python scripts/check_timestamp.py     # can this server reach the timestamp calendars?
./scripts/run_server.sh       # http://10.0.0.5:8100
```

The site migrates its own database on start (Alembic). To try it with example data:
`DB_PATH=data/demo.db .venv/bin/python scripts/seed_demo.py`, then run the server with the same `DB_PATH`.

Run persistently instead:

```bash
systemctl --user restart uniteideas
systemctl --user status uniteideas
```

## What it does

| Area | Behaviour |
| --- | --- |
| Auth | Magic link only, no passwords. First real account on a fresh DB becomes admin. |
| Profiles | Sign-up questionnaire: goals, skills, hours per week. Public member page at `/u/<id>`. |
| Submission | Public one-pager plus an optional sealed detail and one attachment. |
| Proof | SHA-256 of a canonical payload, a receipt, and a public OpenTimestamps timestamp. |
| Verify | `/verify` looks up an idea by link, id or fingerprint; anyone can check, no account. |
| Sealing | Sealed text is encrypted at rest; only its fingerprint is published. |
| Review gate | An account's first idea is held for moderator review; later ones go live at once. |
| Backers | One backing per signed-in account per idea; click again to take it back. |
| Teams | Request to join with an hours-per-week pledge; the owner approves. |
| Roles | user, moderator (review content), admin (accounts, audit log, system), bot (AgentBob). |
| Audit log | Staff actions that change or reveal something, including sealed-detail views. |
| SEO | Canonical links, sitemap.xml, robots.txt, structured data, noindex on private pages. |

## Proof of authorship

Every submission produces a receipt at `/ideas/<id>/proof-bundle.json`. The idea's fingerprint is
also queued for a public timestamp (OpenTimestamps, written into the Bitcoin chain). See
`docs/PROOF_AND_SEALING.md`. A proof is evidence, not a patent, and not legal advice.

## Agent API

`GET /api/agent/ping` with `Authorization: Bearer $AGENT_API_TOKEN`. It confirms the token and
that AgentBob acts as `user-agentbob`. More endpoints are added when AgentBob gets jobs.

## Configuration

All settings live in `.env`; see `.env.example`. `SECRET_KEY` signs session cookies **and**
derives the sealed-detail encryption key, so rotating it logs everyone out and makes existing
sealed text unreadable. In production set `PUBLIC_BASE_URL` to the real https address.

`DEV_SHOW_MAGIC_LINK=true` shows the sign-in link on screen because no mail server is configured.
Turn it off and wire a real provider before exposing the site publicly.

## Stack

FastAPI, Jinja2, SQLAlchemy 2, Alembic, SQLite (Postgres via `DATABASE_URL`). Server-rendered pages,
a few lines of JavaScript for the theme and the backer button, no build step.

## Layout

```
app/        config db models security permissions audit proof sealing timestamping verification seo skills
  routes/   auth pages content ideas profiles teams moderation admin agent_api
  templates/ static/
migrations/ Alembic revisions
scripts/    smoke_test.py test_timestamping.py check_timestamp.py seed_demo.py make_og_image.py
docs/
```
