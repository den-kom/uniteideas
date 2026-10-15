# Milestone 1 walkthrough

Ten minutes, two browser profiles. Everything below runs
against `http://10.0.0.5:8100`.

Open a normal window for the **owner** and a private/incognito window for the
**helper** so the two sessions do not share cookies.

## 1. Create the admin account (owner window)

1. Go to `http://10.0.0.5:8100` and click **Sign in**.
2. Enter an email and a display name, then **Email me a sign-in link**.
3. No mail server is configured, so the link appears on screen in a yellow box.
   Click **Sign in now**.

The first account created on a fresh database becomes admin, so this account
also gets the Moderation and Admin tabs.

You land on a short questionnaire (name, what you can help with). Fill it in or skip it, then read the tour.

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
4. **Admin** (admins only) lists members: promote someone to moderator, or suspend an account with a reason. The audit log records each action.

## 8. Verify an idea

Open `/verify` in the helper window (no account needed), paste the idea's link and press **Check**.
You see when it was recorded, whether the content is unchanged, and the public timestamp state:
"waiting" for a few hours, then "confirmed" with a Bitcoin block number. The one-pager shows the same.

## Resetting

Stop the service, delete `data/uniteideas.db`, and start it again. The next
account you create becomes admin. Uploaded files stay in `data/uploads/` unless
you clear them too.
