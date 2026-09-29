"""Send lead outcomes back to Google Ads: the feedback loop.

Google closed ConversionUploadService.UploadClickConversions to new
integrations, so offline conversions go through the Data Manager API
(datamanager.googleapis.com, events:ingest). Each lead status becomes one
event on its own conversion action, matched to the click by gclid (or
gbraid / wbraid) and, when known, the seller's email or phone. Email and
phone are normalised and SHA-256 hashed on this computer; the raw values
are never sent.

Every run only asks Google to validate the events unless send=True: Google
checks them and records nothing. transaction_id is the lead ID plus the
stage, so sending the same file twice never counts a status twice.
"""

import datetime
import hashlib
import re

from . import master, schema
from .settings import digits, office_zone

DATAMANAGER_SCOPE = "https://www.googleapis.com/auth/datamanager"
ADWORDS_SCOPE = "https://www.googleapis.com/auth/adwords"
ENDPOINT = "https://datamanager.googleapis.com/v1/events:ingest"
ENABLE_API = "https://console.cloud.google.com/apis/library/datamanager.googleapis.com"
MAX_EVENTS = 2000
# The offline_* actions accept clicks up to 90 days old.
WINDOW_DAYS = 90

# CRM stage -> the Google conversion action it feeds.
STAGE_ACTIONS = {
    "qualified_lead": "offline_qualified_lead",
    "appointment": "offline_appointment_set",
    "offer": "offline_offer_made",
    "contract": "offline_under_contract",
    "closed_deal": "offline_closed_deal",
}

# "Not qualified because" -> action. Keys are matched after lower-casing and
# collapsing spaces and slashes, so "Fraud/Spam" and "fraud / spam" both work.
REASON_ACTIONS = {
    "no contact": "offline_no_contact",
    "not a seller": "offline_non_seller",
    "outside buy area": "offline_poor_location",
    "wants retail price": "offline_retail",
    "price shopping": "offline_retail",
    "unqualified seller": "offline_unqualified_seller",
    "fraud spam": "offline_fraud",
    "fraud": "offline_fraud",
    "spam": "offline_fraud",
}


class FeedbackError(Exception):
    pass


# ------------------------------------------------------------ identifiers --


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_email(value):
    email = (value or "").strip().lower()
    return email if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) else None


def normalize_phone(value):
    """E.164 (+15105551234). Ten-digit numbers are taken as US."""

    text = (value or "").strip()
    number = re.sub(r"\D", "", text)
    if text.startswith("+") and 8 <= len(number) <= 15:
        return "+" + number
    if len(number) == 10:
        return "+1" + number
    if len(number) == 11 and number.startswith("1"):
        return "+" + number
    return None


def reason_key(value):
    return re.sub(r"[\s/]+", " ", (value or "").strip().lower()).strip()


# ----------------------------------------------------------------- events --


def _timestamp(lead_date, now, zone):
    """End of the lead's day in office time, never later than a minute ago.

    Google needs the conversion after the click; a lead comes in after its
    click, so the end of that day is always safe and stays the same on
    every run.
    """

    day = datetime.date.fromisoformat(lead_date)
    end = datetime.datetime.combine(day, datetime.time(23, 59, 59), tzinfo=zone)
    latest = now - datetime.timedelta(minutes=1)
    return min(end, latest).isoformat(timespec="seconds")


def build_events(leads, now, zone):
    """({action name: [event, ...]}, [(lead id, reason skipped), ...])."""

    events, skipped = {}, []
    oldest = (now - datetime.timedelta(days=WINDOW_DAYS)).date().isoformat()
    for lead in leads:
        who = lead.get("lead_id") or lead.get("gclid") or "(no id)"
        ad_ids = {key: lead[key] for key in ("gclid", "gbraid", "wbraid") if lead.get(key)}
        users = []
        email = normalize_email(lead.get("email"))
        if email:
            users.append({"emailAddress": sha256(email)})
        phone = normalize_phone(lead.get("phone"))
        if phone:
            users.append({"phoneNumber": sha256(phone)})

        if not ad_ids and not users:
            skipped.append((who, "no gclid, gbraid, wbraid, email or phone"))
            continue
        if not lead.get("lead_date"):
            skipped.append((who, "no lead_date"))
            continue
        if lead["lead_date"] < oldest:
            skipped.append((who, f"lead is older than {WINDOW_DAYS} days, past Google's window"))
            continue

        statuses = [(flag, action) for flag, action in STAGE_ACTIONS.items() if lead.get(flag)]
        reason = reason_key(lead.get("not_qualified_reason"))
        if reason:
            if reason in REASON_ACTIONS:
                statuses.append(("reason", REASON_ACTIONS[reason]))
            else:
                skipped.append((who, f"unknown not_qualified_reason {lead['not_qualified_reason']!r}"))
        if not statuses:
            skipped.append((who, "no status to send yet"))
            continue

        base = lead.get("lead_id") or sha256("|".join([lead.get("gclid", ""), email or "", phone or "", lead["lead_date"]]))[:16]
        timestamp = _timestamp(lead["lead_date"], now, zone)
        for stage, action in statuses:
            event = {
                "transactionId": f"{base}-{action}",
                "eventTimestamp": timestamp,
                "eventSource": "WEB" if ad_ids else "OTHER",
            }
            if ad_ids:
                event["adIdentifiers"] = ad_ids
            if users:
                event["userData"] = {"userIdentifiers": users}
            if stage == "closed_deal" and lead.get("profit"):
                event["conversionValue"] = round(float(lead["profit"]), 2)
                event["currency"] = "USD"
            events.setdefault(action, []).append(event)
    return events, skipped


def request_body(destination, events, validate_only):
    body = {"destinations": [destination], "events": events, "validateOnly": bool(validate_only)}
    if any("userData" in e for e in events):
        body["encoding"] = "HEX"
    return body


def destination(customer_id, login_id, action_id):
    return {
        "operatingAccount": {"accountType": "GOOGLE_ADS", "accountId": customer_id},
        "loginAccount": {"accountType": "GOOGLE_ADS", "accountId": login_id or customer_id},
        "productDestinationId": str(action_id),
    }


# ------------------------------------------------------------- Google I/O --


def conversion_actions(client, customer_id, names):
    """{name: (id, type)} for the enabled conversion actions with these names."""

    from . import api_source

    quoted = ", ".join("'" + n.replace("'", "\\'") + "'" for n in sorted(names))
    rows = api_source.stream(
        client, customer_id,
        "SELECT conversion_action.id, conversion_action.name, conversion_action.type FROM conversion_action "
        f"WHERE conversion_action.status = 'ENABLED' AND conversion_action.name IN ({quoted})",
    )
    return {r.conversion_action.name: (r.conversion_action.id, r.conversion_action.type_.name) for r in rows}


def credentials(settings):
    """Google credentials carrying the Data Manager scope."""

    import os

    api = settings["api"]
    if api.get("json_key_file_path"):
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(
            os.path.expanduser(api["json_key_file_path"]), scopes=[DATAMANAGER_SCOPE]
        )
    from google.oauth2.credentials import Credentials

    return Credentials(
        None,
        refresh_token=api["refresh_token"],
        client_id=api["client_id"],
        client_secret=api["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )


def explain_http(status, payload):
    error = (payload or {}).get("error", {}) if isinstance(payload, dict) else {}
    message = error.get("message") or str(payload)[:300]
    reasons = {d.get("reason") for d in error.get("details", []) if isinstance(d, dict)}
    if "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons:
        return (
            "Your sign-in only covers Google Ads reports, not uploads. Run: python ppc/export.py refresh-token "
            "(it now asks for both permissions), then try again."
        )
    if "SERVICE_DISABLED" in reasons or "has not been used in project" in message or "is disabled" in message:
        # The project that matters is the one owning the OAuth client, which may not be the one open in the console.
        project = re.search(r"project (\d+)", message)
        where = f" (project {project.group(1)})" if project else ""
        link = ENABLE_API + (f"?project={project.group(1)}" if project else "")
        return f"The Data Manager API is off in the Google Cloud project your sign-in belongs to{where}. Turn it on: {link}"
    if status == 403:
        return (
            f"Google refused the upload ({message}). The Google account behind the token needs access "
            "to the Google Ads account, and the Data Manager API must be on: " + ENABLE_API
        )
    if status == 429:
        return f"Google's upload limit was hit ({message}). Wait a minute and run it again."
    details = []
    for d in error.get("details", []):
        for violation in d.get("fieldViolations", []) if isinstance(d, dict) else []:
            details.append(f"{violation.get('field')}: {violation.get('description')}")
    return f"Google rejected the upload ({status}): {message}" + ("\n  " + "\n  ".join(details) if details else "")


def send(session, token, body):
    response = session.post(ENDPOINT, json=body, headers={"Authorization": "Bearer " + token}, timeout=60)
    try:
        payload = response.json()
    except ValueError:
        payload = {"error": {"message": response.text[:300]}}
    return response.status_code, payload


# -------------------------------------------------------------------- run --


def sample_click(client, customer_id, today, days=14):
    """(date, gclid) of the most recent click in the last `days` days, or None."""

    from . import api_source

    for back in range(1, days + 1):
        day = (today - datetime.timedelta(days=back)).isoformat()
        rows = api_source.stream(client, customer_id, f"SELECT click_view.gclid FROM click_view WHERE segments.date = '{day}' LIMIT 10")
        for row in rows:
            if row.click_view.gclid:
                return day, row.click_view.gclid
    return None


def self_test_lead(client, customer_id, today):
    """One pretend lead on a real recent click, marked qualified, for --test."""

    found = sample_click(client, customer_id, today)
    if found is None:
        raise FeedbackError("No ad clicks in the last 14 days to test with.")
    day, gclid = found
    return {"lead_id": "SELF-TEST", "lead_date": day, "gclid": gclid, "gbraid": "", "wbraid": "", "email": "", "phone": "",
            "qualified_lead": 1, "appointment": 0, "offer": 0, "contract": 0, "closed_deal": 0,
            "not_qualified_reason": "", "profit": None}


def run(settings, path=None, *, leads=None, send_for_real=False, done_message=None, now=None, client=None, session=None,
        token=None, log=print):
    """Validate (or send) every status in the lead-outcomes file. Returns an exit code."""

    zone = office_zone(settings)
    now = now or datetime.datetime.now(zone)
    if leads is None:
        leads = master.read_outcome_rows(path)
    if not leads:
        log(f"No leads in {path} yet. Add one row per lead (see ppc/README.md, Lead outcomes).")
        return 2

    events, skipped = build_events(leads, now, zone)
    for who, why in skipped:
        log(f"  skipped {who}: {why}")
    if not events:
        log("Nothing to send: no lead has a click ID or contact detail together with a status.")
        return 2

    customer_id = digits(settings["customer_id"])
    if client is None:
        from . import api_source

        client = api_source.build_client(settings)
    actions = conversion_actions(client, customer_id, set(events))

    if token is None:
        from google.auth.transport.requests import Request

        creds = credentials(settings)
        creds.refresh(Request())
        token = creds.token
    if session is None:
        import requests

        session = requests.Session()

    mode = "Sending" if send_for_real else "Validating (nothing is recorded)"
    log(f"{mode}: {sum(len(v) for v in events.values())} status events for {len(leads)} leads")
    login = digits(settings["api"].get("login_customer_id")) or customer_id
    worst = 0
    for action, batch in sorted(events.items()):
        if action not in actions:
            log(f"  {action}: not in the Google Ads account (or not enabled). Create it as an 'Import from clicks' "
                f"conversion action, or these {len(batch)} events are skipped.")
            worst = max(worst, 1)
            continue
        action_id, action_type = actions[action]
        if action_type != "UPLOAD_CLICKS":
            log(f"  {action}: is a {action_type} action; only 'Import from clicks' actions accept uploads. Skipped.")
            worst = max(worst, 1)
            continue
        for offset in range(0, len(batch), MAX_EVENTS):
            chunk = batch[offset:offset + MAX_EVENTS]
            status, payload = send(session, token, request_body(destination(customer_id, login, action_id), chunk, not send_for_real))
            if status == 200:
                warnings = payload.get("fieldWarnings") or []
                note = f", {len(warnings)} warnings" if warnings else ""
                log(f"  {action}: {len(chunk)} events {'sent' if send_for_real else 'valid'}{note} (request {payload.get('requestId', '?')})")
                for warning in warnings[:5]:
                    log(f"    warning: {warning}")
            else:
                log(f"  {action}: " + explain_http(status, payload))
                return 3 if status in (401, 403) else 1
    if not send_for_real and worst == 0:
        log(done_message or "All valid. To record them in Google Ads, run the same command with --send.")
    return worst
