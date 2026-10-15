# UniteIdeas rebuild: progress

Branch: `rebuild`. One PR to `main`; nothing here is live until it is merged and pulled.
Preview locally: `DB_PATH=data/demo.db python scripts/seed_demo.py` then run uvicorn on another port.
Tests: `./test.sh`.

## Milestones
- [x] M1 Design foundation, backer vote control (arrow, count, word) on home and /ideas, toggle to remove backing
- [x] M2 Homepage copy
- [ ] M3 Verify tied to ideas, timestamp queue (OpenTimestamps)
- [ ] M4 Accounts, questionnaire, profile, Alembic
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
