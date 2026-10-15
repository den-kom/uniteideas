# UniteIdeas rebuild: progress

Branch: `rebuild`. One PR to `main`; nothing here is live until it is merged and pulled.
Preview locally: `DB_PATH=data/demo.db python scripts/seed_demo.py` then run uvicorn on another port.
Tests: `./test.sh`.

## Milestones
- [x] M1 Design foundation, backer vote control (arrow, count, word) on home and /ideas, toggle to remove backing
- [x] M2 Homepage copy
- [x] M3 Verify tied to ideas, timestamp queue (OpenTimestamps), Alembic migrations (0001 baseline, 0002 proof queue)
- [x] M4 Sign-up questionnaire (goals, skills, hours), editable profile, public /u/{id} page, AgentBob (AI) system user (cannot sign in)
- [ ] M5 Admin roles and audit log
- [ ] M6 Terms, privacy, community rules (drafts)
- [ ] M7 SEO and extra pages
- [ ] M8 Placeholders (Unite Ideas, Unite Talent), hide POC request, final checks

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
