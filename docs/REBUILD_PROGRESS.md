# UniteIdeas rebuild: progress

Branch: `rebuild`. One PR to `main`; nothing here is live until it is merged and pulled.
Preview locally: `DB_PATH=data/demo.db python scripts/seed_demo.py` then run uvicorn on another port.
Tests: `./test.sh`.

## Milestones
- [x] M1 Design foundation, backer vote control (arrow, count, word) on home and /ideas, toggle to remove backing
- [x] M2 Homepage copy
- [x] M3 Verify tied to ideas, timestamp queue (OpenTimestamps), Alembic migrations (0001 baseline, 0002 proof queue)
- [x] M4 Sign-up questionnaire (goals, skills, hours), editable profile, public /u/{id} page, AgentBob (AI) system user (cannot sign in)
- [x] M5 Admin area (/admin), moderator vs admin permissions, suspend/reactivate, audit log, timestamp queue page, logged sealed review
- [x] M6 Terms, privacy, community rules (drafts, flagged as not legal advice), acceptance recorded at sign-up, docs/LEGAL_QUESTIONS.md
- [x] M7 SEO: canonical, Open Graph, structured data (Organization, CreativeWork, FAQPage), sitemap.xml, robots.txt, noindex for private pages, gzip, cache headers, paginated feed. Pages: About, How it works, FAQ, Contact, Categories
- [x] M8 Placeholders (Unite Ideas, Unite Talent), POC request removed (PocBuild table kept as legacy, unused), agent API reduced to /ping, final checks

## Slogan options (the live one is in app/templates/index.html)
1. Put your idea on the record. (current)
2. Good ideas deserve company.
3. Share the idea. Keep the proof. Find your team.
4. Ideas are better built together.
5. Your idea, dated and safe.

## Decisions taken without asking (change any of them)
- Kept FastAPI. Added Alembic for migrations (M4).
- Backing is a toggle: click again to remove it.
- Home shows 4 most backed and 4 newest to keep the page light.

## Deploy notes
- Run `./build.sh` after pulling: new dependencies are `alembic` and `opentimestamps`.
- On start the site upgrades its own database (old databases are stamped and migrated).
- Run `.venv/bin/python scripts/check_timestamp.py` on the server. The sandbox that built this
  could not reach the calendar servers, so real timestamping is untested until you run it.

## Bugs found and fixed on the way
- /profile crashed for anyone who had joined a team (it read a column that does not exist).
- The first real sign-up becomes admin; the AgentBob account is excluded from that count.
- Moderators no longer see sealed text just by opening an idea. They use a "sealed review" page and every view
  (and every private attachment opened) is written to the audit log. Change this if you disagree.
- Legal pages assume: 18+, NSW law, contact@uniteideas.org (set CONTACT_EMAIL). All unconfirmed, listed in docs/LEGAL_QUESTIONS.md.

## SEO notes
- Set `PUBLIC_BASE_URL` to https://uniteideas.org in production, or canonical links and the sitemap will point at the dev address.
- The logo and favicon were re-saved losslessly (metadata stripped): 17KB to 2KB. The pixels are unchanged.
- The social sharing image is drawn by scripts/make_og_image.py.
- Idea URLs stay `/ideas/idea-xxxxxxxx`. Title-based slugs would read nicer in search results; say if you want them.


## Instant receipt and public timestamp (two layers)

1. At submit: the receipt (content hash, time, account) is issued at once. The proof bundle carries `receipt_signature`
   (HMAC-SHA256 keyed from SECRET_KEY, domain-separated from the sealing key). `/verify` checks it when a bundle is uploaded.
   Only this server can check it, so it proves "issued by UniteIdeas, unaltered", not independent truth.
2. In the background: the fingerprint goes to OpenTimestamps calendars and becomes a Bitcoin-backed proof anyone can check.
   Rotating SECRET_KEY invalidates old receipt signatures (the public timestamp is unaffected).
3. Later: an own append-only hash-chained log with asymmetric signatures can replace the HMAC so third parties can check layer 1.
