# Questions for a lawyer

The pages at /terms, /privacy and /community-rules are a plain-language draft written from how the
site actually works. They are not legal advice. This file lists what a professional should check and
decide, so the time with them is spent on the right things.

## How the site works (facts to give them)
- Members sign in by email link. No passwords.
- Each idea has a public one-pager and an optional sealed detail (encrypted at rest). Only the owner,
  approved team members, and (once revealed) everyone can read sealed detail.
- Moderators and admins can open sealed detail through a logged review page, and open private attachments
  (also logged). They cannot read sealed text by browsing.
- A SHA-256 fingerprint of each idea is sent to public OpenTimestamps servers and ends up in the Bitcoin
  chain. Only the fingerprint leaves the site. It can never be removed.
- Members can back ideas, ask to join teams, pledge hours per week, and report ideas.
- A robot account (AgentBob) will help moderators and suggest similar ideas and matching people.
- Members must be 18+. The site is run from Sydney, Australia, and members may be anywhere (including EU, UK, US).

## Decisions only you can make
1. Contact address: pages use `contact@uniteideas.org` (set `CONTACT_EMAIL`). Create that mailbox.
2. Who is the legal operator: your name, a company, or a trust? The terms currently say "we" without naming one.
3. Do you accept the promises in the draft? Examples: "a different staff member will look again" on appeals,
   "we do not use sealed detail for suggestions or matching", "we will tell members before a change that matters".
   Engineering must keep each promise true.

## Questions for the lawyer
### Structure and liability
- Which entity should operate the site, and what insurance is sensible for a platform that hosts other people's ideas?
- Is the liability wording in section 10 of the terms enforceable in Australia, the EU and the UK? Australian Consumer Law?
- Do we need safe-harbour or notice-and-takedown wording for infringing content?

### Ideas, ownership and confidentiality
- Is the licence we ask for (display public content, store sealed content) enough and no more than needed?
- Our position is "you keep ownership; we are not a party to agreements between members". Is that safe?
  Should we offer a template collaboration agreement (who owns what teams build)?
- Does a sealed detail create any duty of confidentiality for team members, or only the platform's? Should members accept an
  NDA-style clause when they join a team? Is that enforceable across countries?
- Risk when one member says another copied their idea. What is our stance and process?
- How should we word the patent warning (public disclosure and novelty) so it is accurate in several countries?

### Proof and timestamps
- Is "evidence, not a legal right" the right wording? Anything to add or avoid claiming about Bitcoin timestamps?
- Does permanent public storage of a fingerprint conflict with deletion rights (GDPR "right to erasure")? Is a hash of
  a personal-data-bearing text personal data? (Fingerprints contain no text, but the idea title or body could be personal.)

### Privacy
- Which regimes apply today: Australian Privacy Act (small business exemption?), GDPR, UK GDPR, CCPA? What is required before launch?
- Do we need a data processing record, a breach plan, and an appointed privacy contact?
- Where must data be stored, and what must we say about overseas providers (hosting, email, timestamp calendars)?
- Retention: is "delete or anonymise on closure, keep a limited audit log" acceptable?
- Automated tools: do we need consent or notices for AI-assisted moderation and matching (including profile-based matching)?

### Members and moderation
- Age limit: is 18+ right, given university students and some under-18s? What if a minor joins?
- Our duty regarding illegal content, child safety reporting, and defamation by members.
- Is suspension for a stated reason, with an appeal by email, adequate? Do we owe members more process?
- Staff access to sealed detail for moderation: is the logged-review model acceptable, and what must the terms say?

### Commercial and future features
- Paid features later (e.g., users buying AI model credits through us): payments, consumer law, resale of API credits.
- Students and universities: any special rules for student-owned ideas (institution IP policies)?
- Incubators and investors with their own profiles: any rules about introductions, advice, or securities-style statements?

## Where the draft is least certain
- Section 13 (governing law: NSW), age limit, the liability clause, and the retention wording.
- Anything that says what automated tools do. It describes intent; engineering must enforce it.
