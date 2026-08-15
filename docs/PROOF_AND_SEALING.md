# Proof of authorship and sealed detail

## What a proof claims

A UniteIdeas proof says: *this exact content existed at this time and was
submitted by this verified account.* That is all. It is not a patent, it does
not establish novelty, and it is not legal advice.

It is useful for two things: deterring casual theft, and acting as defensive
publication so that someone else cannot later patent the same thing and claim
you copied them.

## How the hash is built

`app/proof.py` builds a canonical JSON payload with sorted keys:

```json
{
  "version": "uniteideas-proof-v1",
  "title": "...",
  "summary": "...",
  "category": "...",
  "idea_type": "digital|physical",
  "public_body": "...",
  "sealed_detail_sha256": "<sha256 of the sealed text, or empty>",
  "attachments_sha256": ["<sorted file hashes>"]
}
```

The proof's `content_hash` is the SHA-256 of that serialised string. Because the
sealed text appears only as its own hash, the entire payload can be published and
verified while the sealed text stays private.

## The bundle and verification

`/ideas/<id>/proof-bundle.json` returns `{receipt, canonical_payload}`.

`/verify` performs three checks:

1. **Content matches its hash** — recompute SHA-256 over `canonical_payload` and
   compare with the receipt. Catches any edit to the bundle.
2. **Registered on UniteIdeas** — look the hash up in the proof table.
3. **Timestamp on record** — report the stored submission time.

Anyone can do this without an account.

## Current limitation: the timestamp is ours

Today `anchor_provider` is `local`, meaning the timestamp is asserted by this
server. That is fine while UniteIdeas is the only party involved, but a
determined challenger can argue the operator backdated a record.

The fix is an external anchor, and the schema already has room for it
(`anchor_provider`, `anchor_reference`, `anchored_at`). The intended upgrade is
an **RFC-3161 timestamping authority**: send the content hash to a trusted TSA,
receive a signed token binding that hash to a time, and store the token. This
needs no blockchain and no coin. Verification then becomes a fourth check
against the TSA's certificate chain.

Adding it requires an ASN.1 dependency (`rfc3161ng` or `asn1crypto`) and a
chosen TSA. Deliberately deferred so milestone 1 has no external runtime
dependency.

## Sealing: what it protects against

Sealed text is encrypted with Fernet using a key derived from `SECRET_KEY`.

**Protects against:** other users, unauthenticated visitors, a stolen copy of
the database file, and accidental disclosure through the API or templates.

**Does not protect against:** the server operator, or anyone who has both the
database and `SECRET_KEY`.

True zero-knowledge sealing would need a key held only in the author's browser.
That was rejected for now because it breaks three things the platform depends
on: an approved contributor being able to read the detail, the Agent System
being able to build a POC from it, and account recovery after a lost key.

Consequences worth being explicit about:

- Rotating `SECRET_KEY` makes existing sealed text permanently unreadable.
- Back up `SECRET_KEY` wherever you back up the database.
- When an owner requests a POC, the sealed detail is sent to the Agent System.
  That is intentional — it cannot build the thing otherwise — but it means
  sealed text reaches whichever model tier handles the job.

## Who can read sealed detail

| Party | Access |
| --- | --- |
| Owner | Always |
| Approved team members | Yes |
| Moderators and admins | Yes, for moderation |
| Signed-in members | No |
| Public | Only after the owner reveals it, which is permanent |
| Agent System | Only for ideas whose owner requested a POC |
