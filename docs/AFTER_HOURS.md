# The after-hours handoff

What happens when a seller rings outside the shift, why it is built this way,
and every way it goes wrong.

---

## The shift

| When | Who takes the call |
|---|---|
| Mon–Sat, 8:00 AM – 4:59 PM Pacific | the normal Voice AI, running the intake |
| Mon–Sat, 5:00 PM – 7:59 AM | the answering service |
| All day Sunday | the answering service |

## The flow

```
Seller dials, outside the shift
      |
      v
Retell asks the listener: "what time is it?"      (the call_inbound webhook)
      |
      v
The listener works out the hour itself  ->  office_open: no
      |
      +--> override_agent_id = the after-hours agent
      |          |
      |          v
      |    "One moment, connecting you."
      |          |
      |          v
      |    transfers to the answering service
      |          |
      |          v
      |    they take the message, it reaches the team in the morning
      |
      +--> the AFTER HOURS card is posted to Chat
```

The card:

```
🌙 *AFTER HOURS — HANDING TO THE ANSWERING SERVICE*

A seller called outside the 8-5 shift.
The Voice AI is passing them to a live answering service now.

📞 *Caller:* +1...
🕑 *Time:* 7:42 PM on Friday

No action needed now — the message reaches you in the morning.
```

## Three things that were deliberate

**The listener decides, not the AI.** Asking a language model to compare 16
against 17 mid-conversation is a coin toss, and that comparison decides whether
a seller reaches a person or an intake. The listener computes it and hands the
agent a plain yes or no.

**It is a separate agent, not a rule in the main prompt.** After a fixed
greeting the main agent has nothing to respond to, so it takes no turn at all
until silence forces one. On test it sat for **fifteen seconds** and then
started the intake. An agent that speaks first has no such gap.

**The card posts on arrival, not after the transfer.** This is the only moment
we are certain the call is an out-of-hours one -- the transfer leg carries
nothing that tells it apart from a Spanish handover or a claim. That is also
why it says "handing to" rather than "handed to": if the transfer then fails,
the agent's own fallback takes the seller's details and the usual callback card
follows, so the team sees the truth either way.

## Every way it goes wrong

### AFTER_HOURS_AGENT_ID is not set — and the card lies

The card still posts, saying the seller is going to the answering service. But
with no agent to swap in, **the main agent takes the call and runs the full
daytime intake** -- at eleven at night, with nobody awake to act on it.

The card looks identical either way. The only signal is
`AFTER_HOURS_AGENT_ID_NOT_SET` in the log.

### The clock webhook does not answer

Retell runs the call with no dynamic variables at all, so the agent has no
clock, no override happens and no card is posted. The seller gets the daytime
intake. This is the failure that left `{{current_hour}}` empty on every call for
weeks without anyone noticing.

### The hours are still overridden from a test

`OFFICE_OPENS_HOUR` and `OFFICE_CLOSES_HOUR` exist so the after-hours path can
be tested in daylight. Left set, the shift is silently wrong in whichever
direction the test needed. `CLOCK_SETTINGS` prints the values in force at every
startup, and says whether each came from a setting or a default.

### The Chat webhook is missing for that space

`AFTER_HOURS_NOTICE_NO_WEBHOOK`. The handoff still happens -- the seller
reaches the answering service -- but nobody is told it happened.

## The settings

| Setting | Default | What it does |
|---|---|---|
| `AFTER_HOURS_AGENT_ID` | unset | the agent that answers out of hours. **Unset is the dangerous case above** |
| `OFFICE_OPENS_HOUR` | `8` | start of shift, 24-hour clock |
| `OFFICE_CLOSES_HOUR` | `17` | end of shift |
| `OFFICE_CLOSED_DAYS` | `Sunday` | days nobody is on shift. `none` clears it |
| `OFFICE_TIMEZONE` | `America/Los_Angeles` | fixed in code |

A bad value in either hour setting is logged and ignored rather than trusted: a
typo that parsed as an open office would send every night caller into an intake
nobody is awake to answer.

## How to check it

| Question | Log line |
|---|---|
| What hours are in force right now? | `CLOCK_SETTINGS` at startup |
| What did the clock say at boot? | `CLOCK_SETTINGS_NOW` |
| What did it decide for this call? | `CALL_INBOUND_CLOCK` |
| Did the swap happen? | `AFTER_HOURS_AGENT_ID_NOT_SET` means it did not |
| Did the card go out? | `AFTER_HOURS_NOTICE_SENT` / `_FAILED` / `_NO_WEBHOOK` |

## What is not in this repository

The after-hours agent itself -- its one-line script and the number it transfers
to -- lives in Retell. The listener only names it, through
`AFTER_HOURS_AGENT_ID`.

So if calls stop reaching the answering service, check that agent in Retell
before looking at this code. Nothing here can tell you what it is set to dial.
