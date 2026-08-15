# UniteIdeas

Share an idea safely, prove when you shared it, and build it with other people.

Milestone 1 (this release) is the platform on its own: sign up, submit an idea,
get a verifiable timestamp, browse, back, and form a team. No agents are
involved yet — the Agent System only pulls POC jobs through a scoped API.

## Quick start

```bash
cd /home/usrbob/uniteideas
cp .env.example .env          # then set SECRET_KEY and AGENT_API_TOKEN
./build.sh                    # create .venv and install
./test.sh                     # 52 end-to-end checks against a throwaway DB
./scripts/run_server.sh       # http://10.0.0.5:8100
```

Run persistently instead:

```bash
systemctl --user restart uniteideas
systemctl --user status uniteideas
```

## What it does

| Area | Behaviour |
| --- | --- |
| Auth | Magic link only, no passwords. First account on a fresh DB becomes admin. |
| Submission | Public one-pager plus an optional sealed detail and one attachment. |
| Proof | SHA-256 over a canonical payload, timestamped and bound to the account. |
| Sealing | Sealed text is encrypted at rest; only its fingerprint is published. |
| Review gate | An account's first idea is held for moderator review; later ones go live at once. |
| Ranking | One upvote per signed-in account per idea. |
| Teams | Request to join with an hours-per-week pledge; the owner approves. |
| Moderation | First-post queue, report queue, admin role management. |
| POC | Owner requests a POC; the Agent System pulls it and reports progress. |

## Proof of authorship

Every submission produces a downloadable proof bundle at
`/ideas/<id>/proof-bundle.json`, containing a canonical JSON payload and a
receipt. Anyone can check it at `/verify` without an account, which confirms
that the content matches its fingerprint and that the fingerprint is registered
here with a timestamp.

The sealed detail is represented in the payload only by its own SHA-256, so a
bundle can be verified in public without revealing sealed text. See
`docs/PROOF_AND_SEALING.md` for the threat model and the upgrade path to an
RFC-3161 timestamping authority.

A proof is evidence, not a patent, and not legal advice.

## Agent API

Two endpoints, bearer-authenticated with `AGENT_API_TOKEN`:

```
GET  /api/agent/queue?limit=5      # POC jobs owners have requested
POST /api/agent/builds/{build_id}  # {status, notes, preview_url, claim}
```

Valid statuses: `queued`, `planning`, `building`, `testing`, `demo_ready`,
`failed`, `escalated`. Demos stay private to the owner until they publish them.

## Configuration

All settings live in `.env`; see `.env.example` for the annotated list.
`SECRET_KEY` signs session cookies **and** derives the sealed-detail encryption
key, so rotating it logs everyone out and makes existing sealed text unreadable.

`DEV_SHOW_MAGIC_LINK=true` prints the sign-in link on screen because no mail
server is configured. Copies of all outgoing mail land in `data/outbox/`. Turn
this off and wire a real provider before exposing the site publicly.

## Stack

FastAPI, Jinja2, SQLAlchemy 2, SQLite. Server-rendered forms, no JavaScript
build step. Set `DATABASE_URL` to move to Postgres without code changes.

## Layout

```
app/
  config.py db.py models.py security.py proof.py sealing.py mailer.py
  routes/    auth, pages, ideas, teams, moderation, agent_api
  templates/ static/
scripts/     run_server.sh  smoke_test.py
deploy/      uniteideas.service
docs/
```
