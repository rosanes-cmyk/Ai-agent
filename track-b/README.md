# Track B — extending the agent to the non-TV Profit Dial numbers

Track A (TV line) is live. **Do not touch it.** Everything here is additive and fails
open, so a fault in this code cannot take down the TV path.

## Files

| File | Step | What it does |
|---|---|---|
| `inbound_webhook_probe.js` | 1 | Answers whether the originally-dialed Profit Dial number reaches Retell, deciding whether ~5 numbers need buying. |
| `route_alert.js` | 3 | The routing branch: TV number → TV destination, anything else → OTHER LEADS with a lead-source tag. |

## Environment variables

Set these in Cloud Run. **None of these values belong in source.**

| Variable | Value |
|---|---|
| `TV_NUMBER` | The Retell number behind the TV line, E.164. Any format is accepted and normalised. |
| `ZAP_HOOK_OTHER_LEADS` | The Zapier Catch Hook for *THB Inbound – Other Leads (PPC-POSTCARD)*. |
| `LEAD_SOURCE_MAP_JSON` | **Pilot only.** e.g. `{"(510) 800-1662":"PPC"}`. Delete once the sheet lookup tab exists. |

`ZAP_HOOK_OTHER_LEADS` is a write credential — anyone holding the URL can inject
payloads into that Zap. Treat it like a password: Cloud Run env var or Secret Manager,
never a commit, never a screenshot.

## The destination is a Zapier hook, not a Chat webhook

The rollout plan called for `CHAT_WEBHOOK_OTHER_LEADS`, a Google Chat incoming webhook.
The supplied destination is a **Zapier Catch Hook**, which behaves differently:

- A Chat webhook expects Chat message JSON (`{text}` / `{cardsV2}`) and renders it.
- A Zapier Catch Hook takes arbitrary JSON; a Zap then formats and posts it.

So `route_alert.js` sends a flat data payload and **the Zap owns the message text** —
the same split Zap B already uses (Code by Zapier builds it, a Google Chat step posts
it). Copy Zap B's Code step as the starting point; it already handles empty-field
omission, value humanising and phone formatting.

## What the receiving Zap has to do

1. **Catch Hook** — receives the payload below.
2. **Lookup Spreadsheet Row** — resolve `lead_source` from the lookup tab, keyed on
   `lead_source_lookup_key`. Tick *Create row if it doesn't exist yet* off; a miss should
   be visible, not invented.
3. **Code by Zapier** — build the message, prefixing the 🏷️ `lead_source` tag.
4. **Google Chat — Create Message** — post to the OTHER LEADS space.

Payload keys sent: `call_id`, `answered_number`, `profit_dial_number`,
`lead_source_lookup_key`, `lead_source`, `from_number`, `caller_type`, `seller_name`,
`property_address`, `timeline`, `occupancy`, `property_condition`, `price_expectation`,
`motivation`, `call_summary`, `call_started_at`.

**A Zapier lookup miss reports as "no rows found", not as an error.** That is exactly how
the broken claim write stayed invisible for 105 calls. Add a filter or a fallback tag so a
missing lead source is loud rather than silent.

## Which key the lookup uses depends on step 1

`route_alert.js` sends both keys and sets `lead_source_lookup_key` to the right one, so
the Zap never has to change if the answer changes:

- Step 1 returned `PROFIT_DIAL_NUMBER_PRESENT` → key is the **Profit Dial** number, zero
  Retell numbers bought.
- Step 1 returned `ONLY_RETELL_NUMBER` → key is the **Retell** number, ~5 bought.

## Order of operations

1. Run the probe (step 1). It decides how many numbers to buy — do this before buying any.
2. Deploy `route_alert.js` with `ZAP_HOOK_OTHER_LEADS` set. The branch cannot fire until a
   non-TV Profit Dial number actually forwards, so this deploy is a no-op on live traffic.
   If the TV line shares this Cloud Run service, tell Cherry the redeploy is happening
   rather than let her discover it.
3. Run the PPC pilot on `(510) 800-1662` only. Verify all five: 5th-ring pickup, correct
   🏷️ tag, ME claim, transfer, summary.
4. Only then work the remaining 72 forwarding rules.
