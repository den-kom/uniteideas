# Milestone 1 walkthrough

Ten minutes, two browser profiles, no agents involved. Everything below runs
against `http://10.0.0.5:8100`.

Open a normal window for the **owner** and a private/incognito window for the
**helper** so the two sessions do not share cookies.

## 1. Create the admin account (owner window)

1. Go to `http://10.0.0.5:8100` and click **Sign in**.
2. Enter an email and a display name, then **Email me a sign-in link**.
3. No mail server is configured, so the link appears on screen in a yellow box.
   Click **Sign in now**.

The first account created on a fresh database becomes admin, so this account
also gets the Moderation and Users tabs.

You land on the tour. Read it or click **Got it**.

## 2. Submit an idea

Click **Submit an idea** and fill in something like the pet guard:

- **Title** — Pet guard for office chair wheels
- **Summary** — A clip-on guard that stops pets' tails getting caught in chair castors.
- **Type** — Physical product
- **Category** — pets
- **Public one-pager** — the problem, who it helps, roughly how it works.
- **Sealed detail** — dimensions, materials, anything you are not ready to publish.
- **Attachment** — optional sketch (PDF, PNG or JPEG).

Submit. You land on the one-pager. Because this is the account's first idea, it
is held for review: the proof and timestamp are already recorded, but the idea is
not public yet. Open **Moderation**, find it under *First submissions awaiting
review*, and click **Approve and publish**. Every later idea from this account
goes live immediately.

## 3. Look at the proof

Scroll to **Proof of authorship**. You get a submission time, the algorithm, and
a 64-character content fingerprint.

1. Click **Download proof bundle** and save the JSON.
2. Go to **Verify a proof** in the top nav, upload the bundle, click **Verify**.
3. Three checks pass: content matches its hash, registered on UniteIdeas,
   timestamp on record.

To see a failure, open the JSON in a text editor, change one word inside
`canonical_payload`, save, and verify again. The first check fails.

## 4. Confirm the seal actually holds

Copy the idea URL into the helper (incognito) window while signed out. You see
the one-pager, the score, the progress bar, and the proof — but the sealed
detail shows only a note that it is sealed. The sealed text is nowhere in the
page source, and it is not in the proof bundle either, only its fingerprint.

## 5. Back it and ask to join (helper window)

1. Sign in as a second account (different email).
2. Open the idea and click **Back this idea**. The count goes to 1 and the
   button disables. Clicking again is refused.
3. Fill in **Why do you want to help?**, set hours per week, and **Ask to join**.

The pledge is capped at 40h/week summed across every project that account
contributes to, with a warning above 20h/week. Try requesting more than the
remaining allowance on a second idea and it is refused.

## 6. Approve the contributor (owner window)

Reload the idea. Under **Team** there is a pending request showing the pledge.
Click **Approve**. The helper appears on the roster and can now read the sealed
detail.

## 7. Moderation

1. In the helper window, expand **Report this idea**, write a reason, send it.
2. In the owner window, open **Moderation**. The report is in the second queue,
   below the first-submission queue, with the reporter and the reason.
3. Either **Dismiss** with a note, or **Remove idea**, which unpublishes it.
4. **Users** lets the admin promote someone to moderator.

## 8. The POC hand-off

As the owner, click **Request a POC from the Agent System**. That creates a
queued job that UniteIdeas owns. Nothing is running to pick it up yet, so you
can simulate the Agent System from the VM:

```bash
cd /home/usrbob/uniteideas
TOKEN=$(grep '^AGENT_API_TOKEN=' .env | cut -d= -f2-)

curl -s -H "Authorization: Bearer $TOKEN" \
  http://10.0.0.5:8100/api/agent/queue

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"building","notes":"Scaffolding the demo","claim":true}' \
  http://10.0.0.5:8100/api/agent/builds/<build_id>
```

Reload the one-pager: the progress bar advances. Report `demo_ready` with a
`preview_url` and an **Open the demo** button appears — visible to the owner
only until they click **Publish demo**.

## Resetting

Stop the service, delete `data/uniteideas.db`, and start it again. The next
account you create becomes admin. Uploaded files stay in `data/uploads/` unless
you clear them too.
