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

import csv
import datetime
import hashlib
import os
import re

from . import master, schema
from .settings import digits, office_zone

DATAMANAGER_SCOPE = "https://www.googleapis.com/auth/datamanager"
ADWORDS_SCOPE = "https://www.googleapis.com/auth/adwords"
ENDPOINT = "https://datamanager.googleapis.com/v1/events:ingest"
STATUS_ENDPOINT = "https://datamanager.googleapis.com/v1/requestStatus:retrieve"
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


# Every real send is logged here (next to lead_outcomes.csv) so --results can
# ask Google later how it processed each one.
LOG_FILE = "upload_log.csv"
LOG_COLUMNS = ["sent_at", "action", "events", "request_id", "status", "problems", "details", "checked_at"]
FINAL_STATUSES = {"SUCCESS", "PARTIAL_SUCCESS", "FAILED"}
STATUS_WORDS = {
    "SUCCESS": "all recorded",
    "PARTIAL_SUCCESS": "some recorded",
    "FAILED": "none recorded",
    "PROCESSING": "Google is still processing",
    "REQUEST_STATUS_UNKNOWN": "unknown",
}
# Google's processing reasons that people will actually see, in plain words.
REASON_HINTS = {
    "DUPLICATE_TRANSACTION_ID": "already sent before, not counted twice",
    "DUPLICATE_GCLID": "this click already has a conversion at that time",
    "EVENT_TOO_OLD": "the click is older than Google accepts (90 days)",
    "TOO_RECENT_CLICK": "the click was under 6 hours ago; send again later (it won't count twice)",
    "CLICK_NOT_FOUND": "Google can't find the click; check the gclid was copied whole",
    "INVALID_CLICK": "Google can't tie it to a click; check the gclid",
    "INVALID_GCLID": "the gclid is damaged; copy it again from the lead record",
    "INVALID_GBRAID": "the gbraid is damaged",
    "INVALID_WBRAID": "the wbraid is damaged",
    "INVALID_OPERATING_ACCOUNT_FOR_CLICK": "the click belongs to another Google Ads account",
    "OPERATING_ACCOUNT_MISMATCH_FOR_AD_IDENTIFIER": "the click belongs to another Google Ads account",
    "CONVERSION_PRECEDES_CLICK": "lead_date is before the click; check the date",
    "DENIED_CONSENT": "blocked by the account's consent settings",
    "NO_CONSENT": "blocked by the account's consent settings",
    "UNKNOWN_CONSENT": "Google can't tell whether the person consented",
    "DESTINATION_ACCOUNT_ENHANCED_CONVERSIONS_TERMS_NOT_SIGNED":
        "accept the customer data terms in Google Ads (Goals, Settings) to match by email or phone",
}
# Not a problem: re-sending a file is safe by design.
HARMLESS_REASONS = {"DUPLICATE_TRANSACTION_ID"}


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
    """{name: (id, type, owner account id)} for the enabled conversion actions with these names.

    An account also lists actions owned by a manager account it was linked to
    (cross-account conversion tracking), which it cannot send to. When two
    share a name, the one this account owns wins.
    """

    from . import api_source

    quoted = ", ".join("'" + n.replace("'", "\\'") + "'" for n in sorted(names))
    rows = api_source.stream(
        client, customer_id,
        "SELECT conversion_action.id, conversion_action.name, conversion_action.type, conversion_action.owner_customer "
        f"FROM conversion_action WHERE conversion_action.status = 'ENABLED' AND conversion_action.name IN ({quoted})",
    )
    found = {}
    for r in rows:
        action = r.conversion_action
        owner = digits(action.owner_customer) or customer_id
        if action.name not in found or owner == customer_id:
            found[action.name] = (action.id, action.type_.name, owner)
    return found


def events_word(n):
    return f"{n} event" + ("" if n == 1 else "s")


def dashed(account_id):
    text = digits(account_id)
    return f"{text[:3]}-{text[3:6]}-{text[6:]}" if len(text) == 10 else text


def credentials(settings):
    """Google credentials carrying the Data Manager scope."""

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


def access_token(settings):
    from google.auth.transport.requests import Request

    creds = credentials(settings)
    creds.refresh(Request())
    return creds.token


def new_session():
    import requests

    return requests.Session()


def _json(response):
    try:
        return response.json()
    except ValueError:
        return {"error": {"message": response.text[:300]}}


def retrieve(session, token, request_id):
    response = session.get(STATUS_ENDPOINT, params={"requestId": request_id}, headers={"Authorization": "Bearer " + token}, timeout=60)
    return response.status_code, _json(response)


def send(session, token, body):
    response = session.post(ENDPOINT, json=body, headers={"Authorization": "Bearer " + token}, timeout=60)
    return response.status_code, _json(response)


# ---------------------------------------------------------------- results --


def google_reason(reason):
    """PROCESSING_ERROR_REASON_CLICK_NOT_FOUND -> CLICK_NOT_FOUND."""

    return re.sub(r"^PROCESSING_(ERROR|WARNING)_(REASON_)?", "", reason or "UNSPECIFIED")


def reason_text(reason):
    key = google_reason(reason)
    return REASON_HINTS.get(key) or key.lower().replace("_", " ")


def summarize_status(payload):
    """(status, problems, details) from Google's report on one request.

    problems counts records that failed for a reason worth fixing; a resent
    lead (duplicate transaction ID) is not one.
    """

    statuses, problems, details = [], 0, []
    for item in payload.get("requestStatusPerDestination", []):
        statuses.append(item.get("requestStatus", "REQUEST_STATUS_UNKNOWN"))
        for key, counts, kind in (("errorInfo", "errorCounts", "not recorded"), ("warningInfo", "warningCounts", "warning")):
            for count in (item.get(key) or {}).get(counts, []):
                number = int(count.get("recordCount") or 0)
                if kind == "not recorded" and google_reason(count.get("reason")) not in HARMLESS_REASONS:
                    problems += number
                details.append(f"{number} {kind}: {reason_text(count.get('reason'))}")
    if not statuses:
        status = "REQUEST_STATUS_UNKNOWN"
    elif len(set(statuses)) == 1:
        status = statuses[0]
    else:
        status = "PROCESSING" if "PROCESSING" in statuses else "PARTIAL_SUCCESS"
    return status, problems, "; ".join(details)


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [{column: row.get(column) or "" for column in LOG_COLUMNS} for row in csv.DictReader(handle)]


def write_log(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def results(settings, log_path, *, now=None, session=None, token=None, log=print, show=40):
    """Ask Google how it processed each logged send and update the log. Returns an exit code."""

    rows = read_log(log_path)
    if not rows:
        log(f"Nothing sent yet ({log_path} does not exist). Send with: python ppc/export.py upload --send")
        return 2
    pending = [row for row in rows if row["request_id"] and row["status"] not in FINAL_STATUSES]
    if pending:
        token = token or access_token(settings)
        session = session or new_session()
        checked = (now or datetime.datetime.now(office_zone(settings))).isoformat(timespec="seconds")
        for row in pending:
            status, payload = retrieve(session, token, row["request_id"])
            if status != 200:
                write_log(log_path, rows)
                log(explain_http(status, payload))
                return 3 if status in (401, 403) else 1
            row["status"], problems, row["details"] = summarize_status(payload)
            row["problems"], row["checked_at"] = str(problems), checked
        write_log(log_path, rows)

    shown = rows[-show:]
    log(f"What Google did with each upload ({log_path}{f', last {show} of {len(rows)}' if len(rows) > show else ''}):")
    worst = 0
    for row in shown:
        words = STATUS_WORDS.get(row["status"], row["status"] or "no request ID, can't check")
        details = f"  ({row['details']})" if row["details"] else ""
        log(f"  {row['sent_at'][:16].replace('T', ' ')}  {row['action']:<28} {row['events']:>5} events  {words}{details}")
        if int(row["problems"] or 0) or (row["status"] == "FAILED" and not row["details"]):
            worst = 1
    if any(row["status"] == "PROCESSING" for row in shown):
        log("Some uploads are still processing. Run this again in a few minutes.")
    return worst


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


def run(settings, path=None, *, leads=None, send_for_real=False, done_message=None, upload_log=None, now=None, client=None,
        session=None, token=None, log=print):
    """Validate (or send) every status in the lead-outcomes file. Returns an exit code.

    Each real send is added to upload_log right away, so --results can check
    it even if a later action fails.
    """

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

    renamed = (settings.get("feedback") or {}).get("actions") or {}
    events = {renamed.get(name, name): batch for name, batch in events.items()}
    customer_id = digits(settings["customer_id"])
    if client is None:
        from . import api_source

        client = api_source.build_client(settings)
    actions = conversion_actions(client, customer_id, set(events))

    token = token or access_token(settings)
    session = session or new_session()

    mode = "Sending" if send_for_real else "Validating (nothing is recorded)"
    log(f"{mode}: {sum(len(v) for v in events.values())} status events for {len(leads)} leads")
    login = digits(settings["api"].get("login_customer_id")) or customer_id
    worst = 0
    for action, batch in sorted(events.items()):
        if action not in actions:
            log(f"  {action}: not in the Google Ads account (or not enabled). Create it as an 'Import from clicks' "
                f"conversion action, or {events_word(len(batch))} skipped.")
            worst = max(worst, 1)
            continue
        action_id, action_type, owner = actions[action]
        if owner != customer_id:
            log(f"  {action}: belongs to another Google Ads account ({dashed(owner)}), not {dashed(customer_id)}, so it can't")
            log(f"    take uploads from here (Google calls this \"Resource not found\"). Create {dashed(customer_id)}'s own")
            log(f"    'Import from clicks' conversion action named {action}; {events_word(len(batch))} skipped until then.")
            worst = max(worst, 1)
            continue
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
                if send_for_real and upload_log:
                    row = dict.fromkeys(LOG_COLUMNS, "")
                    row.update(sent_at=now.isoformat(timespec="seconds"), action=action, events=str(len(chunk)),
                               request_id=payload.get("requestId", ""))
                    write_log(upload_log, read_log(upload_log) + [row])
            else:
                log(f"  {action}: " + explain_http(status, payload))
                return 3 if status in (401, 403) else 1
    if send_for_real:
        log("Sent. In a few minutes, see what Google recorded with: python ppc/export.py upload --results")
    elif worst == 0:
        log(done_message or "All valid. To record them in Google Ads, run the same command with --send.")
    return worst
