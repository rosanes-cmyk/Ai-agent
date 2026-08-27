/**
 * Track B · Step 3 — the routing branch. The only net-new code in the rollout.
 *
 * TV number  → existing TV Chat destination (unchanged, must not be disturbed)
 * any other  → OTHER LEADS destination, tagged with that number's lead_source
 *
 * ── ONE DELIBERATE DEPARTURE FROM THE PLAN ───────────────────────────────────────
 * The plan named this env var CHAT_WEBHOOK_OTHER_LEADS and assumed a Google Chat
 * incoming webhook. The supplied destination is a ZAPIER CATCH HOOK
 * ("THB Inbound - Other Leads (PPC-POSTCARD)"), which is a different thing:
 *
 *   Google Chat webhook  — expects Chat message JSON ({text} or {cardsV2}) and renders it.
 *   Zapier Catch Hook    — accepts arbitrary JSON; a Zap then formats and posts it.
 *
 * Posting Chat-card JSON to a Zapier hook does not produce a Chat message. So this
 * module sends a FLAT DATA PAYLOAD, not a formatted message, and the Zap owns the
 * formatting — the same split Zap B already uses (Code by Zapier builds the text,
 * Google Chat step posts it). The env var is named for what it actually is.
 *
 * This also keeps a rule the project already paid to learn: Cloud Run never touches
 * the spreadsheet. All sheet reads and writes are Zapier. That is why lead_source is
 * NOT resolved here — see below.
 * ─────────────────────────────────────────────────────────────────────────────────
 *
 * WHO RESOLVES lead_source
 * The design puts the lead-source table in a tab of the Live Call Claims sheet, and
 * only Zapier may read that sheet. So this module sends the KEYS and the Zap does the
 * lookup. Two keys are sent, because step 1 decides which one is usable:
 *
 *   profit_dial_number  present  → step 1 came back PROFIT_DIAL_NUMBER_PRESENT.
 *                                  Key the lookup tab on Profit Dial numbers.
 *                                  Zero Retell numbers bought.
 *   profit_dial_number  null     → step 1 came back ONLY_RETELL_NUMBER.
 *                                  Key the lookup tab on answered_number
 *                                  (~5 Retell numbers, one per lead source).
 *
 * Sending both means the Zap's lookup key can change without redeploying this.
 * For the PPC pilot only, LEAD_SOURCE_MAP_JSON can carry an inline map so the pilot
 * can run before the sheet tab exists. Delete it once the tab is live — two sources
 * of truth for the same mapping is how the "wrong worksheet" defect stayed invisible.
 *
 * FAILURE POSTURE
 * A routing failure must never break a call or the TV path. Every function here
 * returns rather than throws, the POST has a timeout, and a failed OTHER LEADS post
 * is logged loudly but swallowed. The TV branch is untouched code — this module
 * returns a destination decision and only owns the OTHER LEADS post.
 */

'use strict';

/** E.164-normalise so "(510) 800-1662", "5108001662" and "+15108001662" all match. */
function normalize(num) {
  if (num === null || num === undefined) return null;
  const digits = String(num).replace(/\D/g, '');
  if (digits.length < 10 || digits.length > 15) return null;
  return '+' + (digits.length === 10 ? '1' + digits : digits);
}

function loadInlineMap() {
  const raw = process.env.LEAD_SOURCE_MAP_JSON;
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    const out = {};
    for (const [k, v] of Object.entries(parsed)) {
      const key = normalize(k);
      if (key) out[key] = v;
    }
    return out;
  } catch (err) {
    console.error('ROUTE_CONFIG_BAD_LEAD_SOURCE_MAP ' + String(err));
    return {};   // fall through to Zapier-side lookup rather than dying
  }
}

/**
 * Decide where a completed/live call alert belongs.
 * @param {{to_number?:string, metadata?:object, retell_llm_dynamic_variables?:object}} call
 * @returns {{destination:'TV'|'OTHER_LEADS', answered_number:string|null,
 *            profit_dial_number:string|null, lookup_key:string|null, lead_source:string|null}}
 */
function decideRoute(call) {
  const call_ = call || {};
  const answered = normalize(call_.to_number);

  // Written by the inbound-webhook probe when a Diversion/History-Info header survived
  // the REI BlackBook forward. Checked in both places Retell can carry it.
  const profitDial = normalize(
    (call_.metadata && call_.metadata.profit_dial_number) ||
    (call_.retell_llm_dynamic_variables && call_.retell_llm_dynamic_variables.profit_dial_number)
  );

  const tv = normalize(process.env.TV_NUMBER);

  // Unknown answered number routes to OTHER LEADS, never to TV. A misconfigured or
  // missing TV_NUMBER must not silently send strange traffic into the TV space.
  const isTv = tv !== null && answered !== null && answered === tv;

  const lookupKey = profitDial || answered;
  const inline = loadInlineMap();

  return {
    destination: isTv ? 'TV' : 'OTHER_LEADS',
    answered_number: answered,
    profit_dial_number: profitDial,
    lookup_key: lookupKey,
    // null is the normal case: Zapier resolves it from the sheet tab.
    lead_source: (lookupKey && inline[lookupKey]) || null,
  };
}

/** Flat payload for the Zap. Keys are snake_case and stable — the Zap maps them by name. */
function buildOtherLeadsPayload(call, route) {
  const call_ = call || {};
  const custom = (call_.call_analysis && call_.call_analysis.custom_analysis_data) || {};
  return {
    call_id: call_.call_id ?? null,
    answered_number: route.answered_number,
    profit_dial_number: route.profit_dial_number,
    lead_source_lookup_key: route.lookup_key,
    lead_source: route.lead_source,          // null unless the pilot map supplied it
    from_number: call_.from_number ?? null,
    caller_type: custom.call_type ?? null,
    seller_name: custom.seller_name ?? null,
    property_address: custom.property_address ?? null,
    timeline: custom.timeline ?? null,
    occupancy: custom.occupancy ?? null,
    property_condition: custom.property_condition ?? null,
    price_expectation: custom.price_expectation ?? null,
    motivation: custom.motivation ?? null,
    call_summary: (call_.call_analysis && call_.call_analysis.call_summary) ?? null,
    call_started_at: call_.start_timestamp ?? null,
  };
}

/**
 * Route one alert. Returns the decision; performs the OTHER LEADS POST as a side effect.
 * Never throws.
 */
async function routeAlert(call) {
  const route = decideRoute(call);

  if (route.destination === 'TV') {
    // Existing TV path stays exactly as it is. Caller handles it.
    console.log('ROUTE_DECISION ' + JSON.stringify({ ...route, posted: false, reason: 'tv_path_unchanged' }));
    return route;
  }

  const hook = process.env.ZAP_HOOK_OTHER_LEADS;
  if (!hook) {
    // Deploy-safe: without the hook configured this logs and does nothing. It never
    // falls back to the TV destination, which would put non-TV calls in the TV space.
    console.error('ROUTE_NO_OTHER_LEADS_HOOK ' + JSON.stringify({ ...route, posted: false }));
    return route;
  }

  const payload = buildOtherLeadsPayload(call, route);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(hook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    console.log('ROUTE_DECISION ' + JSON.stringify({
      ...route, posted: res.ok, status: res.status, call_id: payload.call_id,
    }));
  } catch (err) {
    // Swallowed on purpose: a Zapier outage must not take down the call path.
    console.error('ROUTE_OTHER_LEADS_POST_FAILED ' + JSON.stringify({
      ...route, call_id: payload.call_id, error: String(err && err.message ? err.message : err),
    }));
  } finally {
    clearTimeout(timer);
  }
  return route;
}

module.exports = { routeAlert, decideRoute, buildOtherLeadsPayload, normalize };
