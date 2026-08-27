/**
 * Track B · Step 1 probe — does the originally-dialed Profit Dial number reach Retell?
 *
 * WHY THIS EXISTS
 * The Track B design assumes ~5 Retell numbers must be bought, one per lead source,
 * because Retell reports which of ITS numbers answered — not the Profit Dial number
 * the seller dialed, which REI BlackBook consumes when it forwards on the 5th ring.
 *
 * That is true of the POST-CALL payload. It is not the whole story. Retell's separate
 * INBOUND CALL webhook receives `custom_sip_headers`, and its allowlist includes
 * `Diversion` and `History-Info` — the headers a forwarding carrier uses to carry the
 * originally-dialed number. If REI BlackBook's forward emits one, zero numbers need
 * buying and a single lookup table keyed on the Profit Dial number does everything.
 *
 * Checking `to_number` on the post-call payload — which is what the plan said to do —
 * CANNOT answer this. `to_number` is always the Retell number, and custom_sip_headers
 * does not appear in the post-call payload at all. That test returns a false negative.
 *
 * ── SAFETY, READ BEFORE DEPLOYING ────────────────────────────────────────────────
 * Retell's inbound webhook is configured PER NUMBER and fires on EVERY inbound call to
 * that number — including the live TV line. If it 5xx's, times out, or returns
 * `reject: true`, it can disturb a production call path that is currently working.
 *
 * So this handler FAILS OPEN, always: every path returns 200 with a body that changes
 * nothing about how the call is handled. It only reads and logs. It never rejects,
 * never overrides the agent, and never changes the agent version.
 * Do not add a `reject` branch to this file.
 * ─────────────────────────────────────────────────────────────────────────────────
 *
 * HOW TO RUN THE TEST (about two minutes of actual work)
 *   1. Deploy this and point the Retell number's inbound webhook at POST /retell/inbound.
 *   2. Call ONE Profit Dial number that already forwards to that Retell number.
 *      Let it ring past the 5th-ring failover so the forward actually happens.
 *   3. Read the log line tagged PROBE_RESULT.
 *
 * READING THE RESULT
 *   verdict: "PROFIT_DIAL_NUMBER_PRESENT"
 *       Zero Retell numbers to buy. `profit_dial_candidate` is the number the seller
 *       dialed. This handler already returns it as metadata + a dynamic variable, so it
 *       rides through to the post-call payload — see "THE HANDOFF" below.
 *   verdict: "ONLY_RETELL_NUMBER"
 *       No routing header survived the forward. Fall back to the planned design: buy
 *       roughly five numbers, one per lead source, keyed on `to_number`.
 *       Before concluding this, check `sip_header_names` in the log — see the caveat.
 *
 * CAVEAT WORTH KNOWING
 *   Retell had a bug that stripped exactly these allowlisted headers at its ingress
 *   proxy before they reached the webhook. Reported 9 Jul 2026, fixed 16 Jul 2026. It
 *   should be fine now, but it is a recent fix, so distinguish the two failure modes:
 *   if `sip_header_names` is empty but the call connected, that is a header-stripping
 *   or no-header-sent situation; if it lists names but none are routing headers, the
 *   forward genuinely does not carry the dialed number.
 *
 * THE HANDOFF (why metadata, and not just logging)
 *   `custom_sip_headers` exists ONLY on this pre-call webhook — there is no call object
 *   and no call_id yet. To get the Profit Dial number into the post-call payload that
 *   Zap B step 1 reads, it has to be written into the call here, via `metadata` and
 *   `dynamic_variables`. Both are documented as present in `call_analyzed`. Once live,
 *   Zapier maps it as: Step 1 · Metadata → profit_dial_number.
 */

'use strict';

const express = require('express');
const app = express();
app.use(express.json({ limit: '1mb' }));

/** Headers a forwarding carrier may use to carry the originally-dialed number,
 *  best first. Retell lowercases header names in custom_sip_headers. */
const ROUTING_HEADERS = [
  'diversion',
  'history-info',
  'x-diversion-number',   // the community workaround, if a middleware ever transposes it
  'x-original-to',
  'x-forwarded-to',
  'p-asserted-identity',  // usually the caller, not the dialed number — checked last
];

/** Pull the first E.164-looking number out of a SIP header value.
 *  Diversion looks like: <sip:+15108001662@host>;reason=unconditional */
function extractNumber(value) {
  if (typeof value !== 'string') return null;
  const m = value.match(/\+?\d[\d\-.() ]{7,}\d/);
  if (!m) return null;
  const digits = m[0].replace(/\D/g, '');
  if (digits.length < 10 || digits.length > 15) return null;
  return '+' + (digits.length === 10 ? '1' + digits : digits);
}

function findProfitDialNumber(sipHeaders, toNumber) {
  if (!sipHeaders || typeof sipHeaders !== 'object') return null;
  const lower = {};
  for (const [k, v] of Object.entries(sipHeaders)) lower[k.toLowerCase()] = v;

  for (const name of ROUTING_HEADERS) {
    const found = extractNumber(lower[name]);
    // Only interesting if it differs from the Retell number that answered.
    if (found && found !== toNumber) return { number: found, header: name };
  }
  return null;
}

app.post('/retell/inbound', (req, res) => {
  const body = req.body || {};
  const sip = body.custom_sip_headers;
  let hit = null;

  try {
    hit = findProfitDialNumber(sip, body.to_number);

    // The whole point of the probe: the complete raw payload, once, unabridged.
    console.log('PROBE_RAW_PAYLOAD ' + JSON.stringify(body));
    console.log('PROBE_RESULT ' + JSON.stringify({
      verdict: hit ? 'PROFIT_DIAL_NUMBER_PRESENT' : 'ONLY_RETELL_NUMBER',
      profit_dial_candidate: hit ? hit.number : null,
      found_in_header: hit ? hit.header : null,
      retell_number_answered: body.to_number ?? null,
      caller: body.from_number ?? null,
      sip_header_names: sip && typeof sip === 'object' ? Object.keys(sip) : [],
      sip_headers_absent: !sip || Object.keys(sip).length === 0,
      numbers_to_buy: hit ? 0 : 'about 5, one per lead source',
    }));
  } catch (err) {
    // Never let a probe bug touch a live call.
    console.error('PROBE_ERROR ' + (err && err.stack ? err.stack : String(err)));
  }

  // Fail open. Nothing here changes call handling; it only attaches context, and only
  // when a number was actually found. No reject, no agent override, ever.
  const call_inbound = {};
  if (hit) {
    call_inbound.metadata = {
      profit_dial_number: hit.number,
      profit_dial_source_header: hit.header,
    };
    call_inbound.dynamic_variables = {
      profit_dial_number: hit.number,
      // lead_source is deliberately NOT set here. It comes from the lookup table keyed
      // on this number, and that table is a later step. Guessing it here would bake a
      // mapping into code that is supposed to live in the sheet.
    };
  }
  res.status(200).json({ call_inbound });
});

app.get('/healthz', (_req, res) => res.status(200).send('ok'));

const port = process.env.PORT || 8080;
app.listen(port, () => console.log(`inbound probe listening on ${port}`));
