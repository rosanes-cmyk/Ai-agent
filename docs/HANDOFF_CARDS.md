# Google Chat cards — state and what is left

Paste this into a Claude session picking this up. Written 9 October 2026,
end of a long night. Everything below was verified live, not inferred.

---

## What exists now

Four cards tell the team what happened to a seller call. Three are live and
tested on real calls tonight; the fourth is written and not yet running.

| Card | Built in | State |
|---|---|---|
| 🔴 LIVE SELLER CALL — AI IS HANDLING IT | Zapier, `THB SELLER CALL ROUTING` step 7 | **live** |
| 🟡 LIVE CALL CLAIMED — CONNECTING | listener, `deploy/main.py` | **live** |
| 🟢 TRANSFERRED — <NAME> IS ON THE CALL | listener | **live** |
| ⚠️ TRANSFER DID NOT CONNECT | listener | live, never fired for real |
| 📞 ANSWERED BY A TEAM MEMBER | **Call Coach**, `services/chat/answered.js` | **written, not deployed** |

## The three things that cost the most time to find

**1. The event is `transfer_started`, not `call_analyzed`.** The green card was
first wired to `disconnection_reason=call_transfer`, which arrives on
`call_ended`. These transfers are **warm**: the agent dials the rep, reads them
a handoff prompt and stays on the line, so `call_status` is still `ongoing` at
the handover and `call_ended` does not come until the rep has finished talking
to the seller. Retell fires `transfer_started` at the handover instead — 18
seconds into the test call — and it matched no path in the Zap, so it recorded
as a run with **zero tasks** and nothing happened. A 0-task run in Zap History
means the trigger fired and every path rejected it; that is the signature to
look for. The listener now accepts either signal.

**2. A card posted as a thread reply gets missed.** Chat folds a thread to
"1 reply". The transfer cards now post as cards in the space. Moving them moved
where a booking reply lands: a reply is only read as a booking when **its own**
thread was marked, so the mark follows the new card. Printing the prompt under
one thread and marking another shows the question and silently ignores every
answer.

**3. Answering a call marks it answered upstream.** Playing Twilio's recording
notice answers the line about a second in, so Profit Dial's "Answered" branch
fires before a phone has rung and claims a human took every call the AI went on
to handle. Emptying that branch is the only fix Profit Dial allows, and it
leaves a rep who really did answer producing nothing. That is what the fifth
card is for.

## What is left, in order

### 1. Deploy Call Coach on the office PC  (BLOCKED: needs someone in Iriga)

The repo has **no `main` branch** — its default IS
`claude/twin-home-buyer-call-coach-f4dwee`, so the office PC pulls it directly.
No merge, no PR.

```powershell
cd "C:\Users\Iriga office\Documents\Twin-Home-Buyer-AI-Call-Coach-Platform"
git status --short     # any filenames here = hand-edited, STOP and ask
git pull
npm --prefix backend install --omit=dev --no-audit --no-fund
```

Then add to `.env` in that folder:

```
GOOGLE_CHAT_WEBHOOK_URL=<the Other Leads Chat webhook, same one Cloud Run uses>
VOICE_LISTENER_URL=https://thb-voice-ai-listener-594863513479.europe-west1.run.app
```

Restart with `Start Call Coach.bat`, or `npm run dev:tunnel` (falls back to
`npm start` if cloudflared is absent).

Both settings are required together. `GOOGLE_CHAT_WEBHOOK_URL` alone posts a
card whose booking prompt is decoration — the parser lives in the listener and
ignores threads it was not told about.

### 2. Clear the Answered branch, per migrated callflow

One Profit Dial number per ring group, roughly fifty of them. The rule is per
campaign and rides along with the migration already under way:

- Forwards to **`15109007650`** (Call Coach) → **empty the Answered branch**;
  the Zapier card there is false
- Forwards to **its ring group** → **leave it**; the card there is true

A campaign that is migrated **and** still has `4h1m050` posts two cards, one
early and false, one correct. That is the only combination to avoid.

### 3. Check the No Answer column

In the **Numbers** tab, a row with a Ring Group and a blank **No Answer**, with
`TWILIO_NO_ANSWER_FORWARD` also unset, hangs up on a seller nobody picks up.
No card, no error, nothing in any log. Asked about `5108001662` several times
tonight and never got an answer. **Still unconfirmed.**

## Gotchas worth knowing before touching anything

- **The claim window is 120 seconds** from when the card was mapped, not "while
  the call is live". A rep reading the card at three minutes types a valid
  claim into a thread that answers nothing, with no error either way.
- **Claim text is an exact match** against 107 phrases after lowercasing and
  stripping punctuation. `sure thing` works, `ok ill take it` does not. The 50
  refusal phrases are checked first, so `one moment` blocks your own claim.
- **`CLAIMANTS` replaces the built-in roster** rather than adding to it. The
  live list is whatever Cloud Run holds.
- **Claim state is in memory.** Pin Cloud Run `max-instances=1` or two reps can
  win the same call. (Asked for; not confirmed done.)
- **The main agent's prompt is not in version control.** Only
  `deploy/prompt_sas.txt` is. Brynne (`agent_364bdf0451f3ff541625b66b2b`) lives
  only in Retell's dashboard — unreviewable, undiffable, unrestorable.
- **`backend/test/repReport.test.js:86` fails** and is not from this work; it
  fails at HEAD with dependencies installed. 718 tests, 710 pass, 7 skipped.
  Run `npm install --prefix backend` before trusting any test result.

## Where the documentation is

- `docs/CHAT_CARDS.md` — every card's text, printed by running the code
- `docs/CARD_TRIGGERS.md` — the full condition list per card, and every way
  each one stays silent
- `docs/render_cards.py` — regenerates the first of those; re-run after
  changing any card so it cannot drift
- Call Coach `docs/CALL_PATH.md` — the seam between the two systems
- Call Coach `docs/call-flow.svg` — the diagram, with the recording notice and
  the No Answer fork on it

## Rules that still apply

- **Track A (the TV line) is live. Do not touch it.** `THB SELLER CALL ROUTING`
  steps 13 and 14 are its card.
- Tagging applies to Twin Home Buyer numbers only, never Equity Track (`EQT`).
- Chat webhook URLs and the Retell key are credentials — environment variables
  only, never committed, never in a screenshot.
- Never write to the Apps Script `Data` tab; never install or delete Apps
  Script triggers.
- The Retell API key was pasted into a chat weeks ago. **Still not rotated.**
