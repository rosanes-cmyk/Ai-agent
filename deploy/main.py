import base64
import datetime
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import zoneinfo

import functions_framework


logging.basicConfig(level=logging.INFO)


# =========================================================
# TEMPORARY LIVE CALL MEMORY
# =========================================================

THREAD_CALLS = {}

# Latest mapped call, keyed by Google Chat space resource name.
# A claim in one space can only ever match a call mapped in that
# same space, so a "me" typed in TV can never grab an
# Other Leads call (and vice versa).
LATEST_CALLS = {}

# First valid claimant wins.
CLAIMED_CALLS = {}

# Latest seller/call information collected while the call is live.
# Keyed by Retell call_id.
CALL_DATA = {}

# Threads belonging to a human-answered call card rather than a live
# call. Two jobs: a claim word typed in one of these must never
# transfer a seller call, and a "booked" reply in one has to be read
# as an appointment. Keyed by thread name -> context dict.
ANSWERED_THREADS = {}

# How long a thread stays open for a reply. Long enough that someone
# answering later in the day still lands, short enough that memory
# cannot grow without bound.
# How long after a card is posted a transfer leg may still be treated
# as the same seller. Long enough for an agent to hand over, short
# enough that a later caller never inherits the notice.
# The office clock. Every number forwards to one Retell agent, so the
# agent has to be told the time - it has no clock of its own, and an
# unset {{current_hour}} silently reads as nothing at all.
OFFICE_TIMEZONE = "America/Los_Angeles"

def _hour_setting(name, default):
    """A shift boundary, overridable without touching this file.

    Testing the after-hours path in daylight means making the clock say
    closed. Doing that by editing the constants meant the real hours
    came back with the next paste of this file, three times, and each
    time the test quietly passed through the daytime path instead. A
    setting cannot be overwritten by a deploy.
    """

    raw = os.environ.get(name, "").strip()

    if not raw:
        return default

    try:
        hour = int(raw)
    except ValueError:
        logging.error("%s_NOT_A_NUMBER value=%r", name, raw)
        return default

    if not 0 <= hour <= 24:
        logging.error("%s_OUT_OF_RANGE value=%r", name, raw)
        return default

    logging.info("%s_OVERRIDDEN value=%d", name, hour)

    return hour


# Shift start and end, as whole hours on a 24-hour clock. 8 through 16
# inclusive is 8:00 AM up to 4:59 PM; 17 is closed.
OFFICE_OPENS_HOUR = _hour_setting("OFFICE_OPENS_HOUR", 8)
OFFICE_CLOSES_HOUR = _hour_setting("OFFICE_CLOSES_HOUR", 17)

# Days nobody is on shift at any hour. The answering service has
# Sunday outright, so the hours above never apply to it.
def _closed_days():
    """The days the office is shut whatever the hour.

    A blank setting falls back to Sunday rather than meaning "no closed
    days". Someone clearing a variable by accident should not quietly
    hand us Sunday back; "none" says it on purpose.
    """

    raw = os.environ.get("OFFICE_CLOSED_DAYS", "").strip()

    if not raw:
        return {"Sunday"}

    if raw.lower() == "none":
        logging.info("OFFICE_CLOSED_DAYS_CLEARED")
        return set()

    return {
        day.strip()
        for day in raw.split(",")
        if day.strip()
    } or {"Sunday"}


OFFICE_CLOSED_DAYS = _closed_days()


# The agent's welcome message is the field {{greeting}}, so what the
# caller hears first is decided here rather than in the prompt. Out of
# hours the agent is only a doorway to the answering service, and a
# caller who has to sit through an intake greeting before being handed
# to a person has been made to wait for nothing.
OPEN_GREETING = (
    "Thanks for calling Twin Home Buyer. You're speaking with our "
    "Voice AI Agent, and this call may be recorded. "
    "How can I help you today?"
)

CLOSED_GREETING = "One moment, connecting you."


# The agent that answers out-of-hours calls, if one is configured.
#
# The main agent cannot do this job. After a static welcome message it
# has nothing to respond to, so it takes no turn at all until silence
# forces one - on a real test it sat for fifteen seconds and then
# started the intake, never reaching the handoff rule. A dedicated
# agent whose first generated turn IS the transfer has no such gap.
#
# Left unset, nothing changes and the main agent keeps every call.
AFTER_HOURS_AGENT_ID = os.environ.get(
    "AFTER_HOURS_AGENT_ID",
    "",
).strip()


def office_clock(now=None):
    """The time the voice agent should believe, in the office's timezone.

    Returns plain strings because they land in the prompt as text. The
    open/closed answer is computed HERE rather than left to the agent:
    asking a language model to compare 16 against 17 mid-conversation is
    a coin toss, and this decides whether a seller reaches the
    answering service or our own intake.
    """

    if now is None:
        now = datetime.datetime.now(
            zoneinfo.ZoneInfo(OFFICE_TIMEZONE)
        )

    hour = now.hour
    day = now.strftime("%A")

    is_open = (
        day not in OFFICE_CLOSED_DAYS
        and OFFICE_OPENS_HOUR <= hour < OFFICE_CLOSES_HOUR
    )

    return {
        "current_hour": str(hour),
        "current_day": day,
        "current_time": now.strftime("%-I:%M %p"),
        "office_open": "yes" if is_open else "no",
        "greeting": OPEN_GREETING if is_open else CLOSED_GREETING,
    }


LANGUAGE_SWITCH_WINDOW = 5 * 60

# Google Chat renders this as @all and notifies everyone in the space,
# including inside a collapsed thread.
MENTION_ALL = "<users/all>"


ANSWERED_THREAD_TTL = 24 * 60 * 60


# =========================================================
# APPROVED CLAIM PHRASES
# =========================================================

CLAIM_PHRASES = {
    "me",
    "mine",

    "yes",
    "yep",
    "yup",
    "yeah",
    "yea",
    "yah",
    "ya",
    "yess",
    "yesss",
    "yes please",

    "ok",
    "okay",
    "okey",
    "okie",
    "k",
    "kk",
    "kay",
    "mkay",
    "okeydokey",
    "okeydoke",
    "okiedokie",
    "aok",

    "affirmative",
    "alright",
    "all right",
    "agreed",
    "fine",
    "sure",
    "sure thing",
    "absolutely",
    "certainly",
    "definitely",
    "of course",
    "correct",
    "confirmed",
    "approved",

    "roger",
    "roger that",
    "copy",
    "copy that",
    "104",
    "got it",
    "i got it",
    "understood",

    "no problem",
    "no worries",
    "you bet",
    "you got it",
    "for sure",
    "forsure",
    "fo sho",
    "word",
    "bet",
    "aight",
    "ight",
    "igh",
    "aiight",

    "available",
    "available now",
    "im available",
    "i am available",

    "ready",
    "ready now",
    "im ready",
    "i am ready",

    "im free",
    "i am free",
    "free now",

    "ive got it",
    "i have it",

    "ill take it",
    "i will take it",
    "i can take it",

    "ill take the call",
    "i will take the call",
    "i can take the call",

    "take it",
    "take the call",

    "claim",
    "claim it",
    "claim call",
    "claim the call",

    "transfer",
    "transfer it",
    "transfer me",
    "transfer to me",
    "transfer the call",

    "connect me",
    "connect me now",

    "send it",
    "send it over",
    "send it to me",
    "send me the call",

    "put it through",
    "put them through",

    "go",
    "go ahead",
    "go for it",
    "proceed",
    "proceed now",
    "do it",
    "do it now",
    "lets go",
    "lets do it",
    "lets do this",
}


# =========================================================
# EXPLICIT DO-NOT-TRANSFER PHRASES
# =========================================================

NEGATIVE_CLAIM_PHRASES = {
    "no",
    "nope",
    "nah",
    "naw",
    "negative",

    "not me",
    "not mine",
    "someone else",
    "give it to someone else",
    "send it to someone else",

    "maybe",
    "maybe later",
    "not sure",
    "im not sure",
    "i am not sure",

    "wait",
    "wait please",
    "wait a minute",
    "wait a sec",
    "wait a second",
    "hold",
    "hold on",
    "one moment",

    "later",
    "not now",
    "do it later",
    "call later",
    "maybe next time",

    "busy",
    "im busy",
    "i am busy",

    "unavailable",
    "im unavailable",
    "i am unavailable",

    "cant",
    "cannot",
    "i cant",
    "i cannot",
    "cant take it",
    "cannot take it",
    "cant take the call",
    "cannot take the call",

    "dont transfer",
    "do not transfer",
    "dont transfer to me",
    "do not transfer to me",

    "dont send it",
    "do not send it",
    "dont send it to me",
    "do not send it to me",
}


# =========================================================
# NORMALIZE CLAIM TEXT
# =========================================================

def normalize_claim_text(text):

    text = str(text or "").strip().lower()

    text = text.replace("’", "'")

    # Examples:
    # O.K. -> ok
    # A-OK -> aok
    # 10-4 -> 104
    # I'm available -> im available
    text = re.sub(
        r"[^\w\s]",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


# =========================================================
# GOOGLE CHAT CLAIMANT IDS
# =========================================================

CHERRY_USER_ID = os.environ.get(
    "CHERRY_USER_ID",
    "",
)

THEA_USER_ID = os.environ.get(
    "THEA_USER_ID",
    "",
)

JUAN_USER_ID = os.environ.get(
    "JUAN_USER_ID",
    "",
)


# Everyone allowed to claim a live call, as a Google Chat user id
# mapped to the name printed on the card. Set CLAIMANTS to a JSON
# object so adding a rep is a setting change, not a code change:
#
#   {"users/123456": "Cherry", "users/789012": "Marie"}
#
# A rep who is not in here types "me" and nothing happens, so the list
# is the only thing standing between a claim and a wrong transfer.

def _claimant_record(entry):
    """One roster entry, however it was written.

    A bare string is still accepted so an older CLAIMANTS value keeps
    working; it just has no phone, which the transfer step reports.
    """

    if isinstance(entry, dict):

        return {
            "name": str(entry.get("name", "")).strip(),
            "phone": str(entry.get("phone", "")).strip(),
        }

    return {
        "name": str(entry or "").strip(),
        "phone": "",
    }


# The reps who can claim a live call by typing "me", as Google Chat
# user ids. These ids came from the mention data in the space, so they
# are exact rather than guessed.
#
# Setting the CLAIMANTS environment variable REPLACES this list, which
# is how somebody is removed without touching code.

DEFAULT_CLAIMANTS = {
    "users/114145931346266127748": {
        "name": "Diego Villa",
        "phone": "+14083728643",
    },
    "users/117453347421781344763": {
        "name": "David Romero",
        "phone": "+15102143561",
    },
    "users/115321219780426469079": {
        "name": "Barbie Adorable",
        "phone": "+14084758505",
    },
    "users/111163562030904317973": {
        "name": "Era Miraflor",
        "phone": "+14083205567",
    },
}


def _load_claimants():

    people = {}

    raw = os.environ.get(
        "CLAIMANTS",
        "",
    ).strip()


    parsed = None


    if raw:

        try:

            parsed = json.loads(raw)

        except ValueError:

            parsed = None

            logging.error(
                "CLAIMANTS_NOT_VALID_JSON"
            )


    if isinstance(parsed, dict):

        # An explicit list replaces the built-in one entirely, so a
        # rep who has left can actually be taken off.

        for user_id, entry in parsed.items():

            key = str(user_id).strip()
            record = _claimant_record(entry)

            if key and record["name"]:
                people[key] = record

    else:

        if parsed is not None:

            logging.error(
                "CLAIMANTS_NOT_AN_OBJECT"
            )

        people.update(DEFAULT_CLAIMANTS)


    # The three original variables still work on their own, so the
    # service keeps running unchanged if CLAIMANTS is never set.

    for variable, label in (
        ("CHERRY_USER_ID", "Cherry"),
        ("THEA_USER_ID", "Thea"),
        ("JUAN_USER_ID", "Juan"),
    ):

        value = os.environ.get(
            variable,
            "",
        ).strip()

        if value:
            people.setdefault(
                value,
                {"name": label, "phone": ""},
            )


    logging.info(
        "CLAIMANTS_LOADED count=%s",
        len(people),
    )


    return people


CLAIMANTS = _load_claimants()


# =========================================================
# WEBHOOK URLS
# =========================================================

GOOGLE_CHAT_WEBHOOK_URL = os.environ.get(
    "GOOGLE_CHAT_WEBHOOK_URL",
    "",
)

CLAIM_SHEET_WEBHOOK_URL = os.environ.get(
    "CLAIM_SHEET_WEBHOOK_URL",
    "",
)

# Zap that appends a row to the Intake Inbox tab, which the Property
# Visit Tracking script then turns into a calendar entry.
INTAKE_WEBHOOK_URL = os.environ.get(
    "INTAKE_WEBHOOK_URL",
    "",
)


# =========================================================
# GOOGLE CHAT SPACE ROUTING
# =========================================================

TV_SPACE = os.environ.get(
    "TV_SPACE_ID",
    "spaces/AAQAWCwg62E",
)

OTHER_LEADS_SPACE = os.environ.get(
    "OTHER_LEADS_SPACE_ID",
    "spaces/AAQAacVgBeA",
)


# TV falls back to the original single webhook so Track A keeps
# working even before CHAT_WEBHOOK_TV is set.
CHAT_WEBHOOKS = {

    TV_SPACE: os.environ.get(
        "CHAT_WEBHOOK_TV",
        "",
    ) or GOOGLE_CHAT_WEBHOOK_URL,

    OTHER_LEADS_SPACE: os.environ.get(
        "CHAT_WEBHOOK_OTHER_LEADS",
        "",
    ),
}


def space_from_resource(resource):
    """spaces/XXX/threads/YYY -> spaces/XXX"""

    parts = str(
        resource or ""
    ).strip().split("/")

    if (
        len(parts) >= 2
        and parts[0] == "spaces"
        and parts[1]
    ):
        return "spaces/" + parts[1]

    return ""


def extract_space_name(
    chat_message,
    thread_id="",
    message_id="",
):

    space = (
        chat_message or {}
    ).get(
        "space",
        {},
    ) or {}

    for candidate in (
        space.get("name"),
        thread_id,
        message_id,
    ):

        found = space_from_resource(
            candidate
        )

        if found:
            return found

    # Preserve the original single-space behaviour.
    return TV_SPACE


def mark_answered_thread(thread_id, context):

    now = time.time()

    entry = dict(context or {})
    entry["marked_at"] = now

    ANSWERED_THREADS[thread_id] = entry

    # Opportunistic prune so a long-running instance cannot grow
    # this dict indefinitely.
    if len(ANSWERED_THREADS) > 500:

        for key, value in list(ANSWERED_THREADS.items()):

            if now - value.get("marked_at", 0) > ANSWERED_THREAD_TTL:
                ANSWERED_THREADS.pop(key, None)


def answered_thread(thread_id):
    """The context for a human-answered card thread, or None."""

    key = str(thread_id or "").strip()

    entry = ANSWERED_THREADS.get(key)

    if not entry:
        return None

    if time.time() - entry.get("marked_at", 0) > ANSWERED_THREAD_TTL:

        ANSWERED_THREADS.pop(key, None)

        return None

    return entry


def latest_answered_in_space(space_name):
    """The newest open human-answered card in this space, or ("", None).

    The Reply link under a card is small and the hover arrow is
    "Quote in reply", so a booking typed in the main message box would
    otherwise be lost. It is attached to the newest open card in the
    same space instead.
    """

    wanted = str(space_name or "").strip()

    if not wanted:
        return ("", None)

    now = time.time()

    best_key = ""
    best_entry = None

    for key, value in list(ANSWERED_THREADS.items()):

        if now - value.get("marked_at", 0) > ANSWERED_THREAD_TTL:

            ANSWERED_THREADS.pop(key, None)
            continue

        if value.get("space") != wanted:
            continue

        if (
            best_entry is None
            or value.get("marked_at", 0) > best_entry.get("marked_at", 0)
        ):
            best_key = key
            best_entry = value

    return (best_key, best_entry)


# =========================================================
# HUMAN-ANSWERED CALL: READING A "BOOKED" REPLY
# =========================================================

# The sheet's Lead Source column is a strict dropdown. An out-of-list
# value throws and fails the whole row, so every campaign tag is
# mapped to an allowed value here and the precise tag goes into
# Task Body instead. Anything unmapped is left blank on purpose.
LEAD_SOURCE_SHEET_VALUES = {
    "PPC": "PPC",
    "TV": "TV",
    "PROPERTY-LEADS": "PPL - Property Leads",
    "MOTIVATED-LEADS": "PPL - Motivated Leads",
}

# Visits are done by Juan; whoever answered the call is recorded in
# Task Body. Assigned Visitor is a strict dropdown and does not
# contain everyone who answers calls.
ASSIGNED_VISITOR = "Juan"

BOOKING_KEYWORDS = ("booked", "book", "booking", "appointment", "appt", "set")

NO_APPOINTMENT_PHRASES = {
    "none", "no", "nope", "nothing", "no appt", "no appointment",
    "not booked", "no booking", "nada", "wala", "n a", "na",
    "no appointment set", "didnt book", "did not book",
}

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

PACIFIC = "America/Los_Angeles"


def _pacific_today():

    try:

        from zoneinfo import ZoneInfo

        return datetime.datetime.now(
            ZoneInfo(PACIFIC)
        ).date()

    except Exception:

        # Better a slightly stale date than a crash; the sheet
        # refuses past dates anyway, which surfaces the problem.
        return datetime.datetime.utcnow().date()


def _valid_date(year, month, day):

    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _extract_date(text):
    """Return (date, matched_span) or (None, None).

    Understood: "sep 2", "september 2 2026", "9/2", "9/2/2026",
    "9-2-2026", "2026-09-02". A year-less date rolls forward rather
    than booking in the past.
    """

    today = _pacific_today()

    # 2026-09-02 — written in full, so no rolling
    m = re.search(
        r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",
        text,
    )

    if m:

        found = _valid_date(
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
        )

        if found:
            return found, m.span()

    # 9/2, 9/2/26, 9-2-2026
    m = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b",
        text,
    )

    if m:

        month = int(m.group(1))
        day = int(m.group(2))
        year_text = m.group(3)

        if year_text:

            year = int(year_text)

            if year < 100:
                year += 2000

            found = _valid_date(year, month, day)

            if found:
                return found, m.span()

        else:

            found = _valid_date(today.year, month, day)

            if found:

                if found < today:

                    rolled = _valid_date(today.year + 1, month, day)

                    if rolled:
                        found = rolled

                return found, m.span()

    # sep 2 / september 2, 2026 / 2 september
    names = "|".join(sorted(MONTHS, key=len, reverse=True))

    for pattern, month_group, day_group in (
        (r"\b(" + names + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s*(20\d{2}))?", 1, 2),
        (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + names + r")\b(?:,?\s*(20\d{2}))?", 2, 1),
    ):

        m = re.search(pattern, text, re.IGNORECASE)

        if not m:
            continue

        month = MONTHS[m.group(month_group).lower().rstrip(".")]
        day = int(m.group(day_group))
        year_text = m.group(3)

        year = int(year_text) if year_text else today.year

        found = _valid_date(year, month, day)

        if not found:
            continue

        if not year_text and found < today:

            rolled = _valid_date(today.year + 1, month, day)

            if rolled:
                found = rolled

        return found, m.span()

    return None, None


def _extract_time(text):
    """Return (formatted_time, matched_span) or (None, None)."""

    # 2pm, 2:30 pm, 14:00
    m = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\b",
        text,
        re.IGNORECASE,
    )

    if m:

        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        meridiem = m.group(3).lower()

        if hour < 1 or hour > 12 or minute > 59:
            return None, None

        display_hour = hour

        return (
            "%d:%02d %s" % (
                display_hour,
                minute,
                "AM" if meridiem == "a" else "PM",
            ),
            m.span(),
        )

    # 24-hour, only with a colon so a bare date cannot match
    m = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        text,
    )

    if m:

        hour = int(m.group(1))
        minute = int(m.group(2))

        meridiem = "AM" if hour < 12 else "PM"

        display_hour = hour % 12

        if display_hour == 0:
            display_hour = 12

        return (
            "%d:%02d %s" % (display_hour, minute, meridiem),
            m.span(),
        )

    return None, None


def _clean_address(text):

    cleaned = re.sub(r"\s+", " ", text).strip()

    # Strip connector words and punctuation left behind once the date
    # and time have been cut out of the middle of the sentence. Cutting
    # both can leave several separators in a row ("booked Sep 2, 2pm,
    # 123 Main St" leaves ", , 123 Main St"), so the whole group
    # repeats over the whitespace between them. The word alternatives
    # need boundaries or "Independence Ave" loses its "In".
    cleaned = re.sub(
        r"^(?:(?:at|on|for|in)\s+|[@,\-–—.:;]\s*)+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"(?:\s*[,\-–—.:;])+$",
        "",
        cleaned,
    )

    return cleaned.strip()


def parse_booking(text):
    """Read "booked Sep 2, 2pm, 123 Main St, Oakland".

    Returns a dict with what was found. `date` is the only field the
    sheet cannot do without, so the caller asks again when it is
    missing rather than guessing.
    """

    raw = str(text or "").strip()

    lowered = raw.lower()

    keyword_found = False

    for word in BOOKING_KEYWORDS:

        m = re.match(
            r"^" + word + r"\b[\s:,-]*",
            lowered,
        )

        if m:

            raw = raw[m.end():]
            keyword_found = True
            break

    found_date, date_span = _extract_date(raw)

    remainder = raw

    if date_span:
        remainder = remainder[:date_span[0]] + " " + remainder[date_span[1]:]

    found_time, time_span = _extract_time(remainder)

    if time_span:
        remainder = remainder[:time_span[0]] + " " + remainder[time_span[1]:]

    return {
        "keyword": keyword_found,
        "date": found_date,
        "date_text": (
            "%d/%d/%d" % (
                found_date.month,
                found_date.day,
                found_date.year,
            )
            if found_date else ""
        ),
        "time_text": found_time or "",
        "address": _clean_address(remainder),
    }


def looks_like_no_appointment(normalized_text):

    return normalized_text in NO_APPOINTMENT_PHRASES


def looks_like_booking(text):

    lowered = str(text or "").strip().lower()

    for word in BOOKING_KEYWORDS:

        if re.match(r"^" + word + r"\b", lowered):
            return True

    # The card asks for a bare "Sep 2, 2pm", so a date on its own is a
    # booking. No claim word contains one, so live alerts are unaffected.
    found_date, _span = _extract_date(str(text or ""))

    return found_date is not None


def sheet_lead_source(tag):
    """Map a campaign tag to a value the sheet dropdown accepts."""

    key = str(tag or "").strip().upper()

    if not key:
        return ""

    # The campaign part is what matters; the region is dropped here
    # and kept in Task Body.
    key = key.split()[0]

    if key in LEAD_SOURCE_SHEET_VALUES:
        return LEAD_SOURCE_SHEET_VALUES[key]

    if key.startswith("POSTCARD"):
        return "Direct Mail - Postcard"

    return ""


def get_chat_webhook(space_name):

    webhook = CHAT_WEBHOOKS.get(
        space_name,
        "",
    )

    if not webhook:

        logging.error(
            "NO_CHAT_WEBHOOK_FOR_SPACE %s",
            space_name,
        )

    return webhook


# =========================================================
# LIVE CALL SELLER DATA HELPERS
# =========================================================

LIVE_DATA_FIELDS = (
    "lead_source",
    "name",
    "phone",
    "property",
    "caller_type",
    "reason",
    "timeline",
    "asking_price",
)

LIVE_DATA_ALIASES = {
    "lead_source": ("lead_source", "leadsource", "campaign", "source"),
    "name": ("name", "seller_name", "caller_name"),
    "phone": ("phone", "phone_number", "from_number", "caller_phone"),
    "property": ("property", "property_address", "address"),
    "caller_type": ("caller_type", "seller_type", "lead_type"),
    "reason": ("reason", "reason_for_calling", "call_reason", "motivation"),
    "timeline": ("timeline", "selling_timeline"),
    "asking_price": ("asking_price", "price", "desired_price"),
}


def _clean_live_value(value):

    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
        ).strip()

    return str(value).strip()


def merge_call_data(
    call_id,
    payload,
):

    call_id = str(call_id or "").strip()

    if not call_id:
        return {}

    payload = payload or {}

    nested = payload.get("data")

    if isinstance(nested, dict):
        source = {
            **payload,
            **nested,
        }
    else:
        source = payload

    current = CALL_DATA.get(
        call_id,
        {
            "updated_at": 0,
        },
    )

    for target_field, aliases in LIVE_DATA_ALIASES.items():

        for alias in aliases:

            if alias not in source:
                continue

            value = _clean_live_value(
                source.get(alias)
            )

            if value:
                current[target_field] = value

            break

    current["updated_at"] = time.time()

    CALL_DATA[call_id] = current

    logging.info(
        "LIVE_CALL_DATA_UPDATED "
        "call_id=%s fields=%s",
        call_id,
        json.dumps(
            {
                field: current.get(field, "")
                for field in LIVE_DATA_FIELDS
            },
            ensure_ascii=False,
        ),
    )

    return current


def get_call_data(call_id):

    return CALL_DATA.get(
        str(call_id or "").strip(),
        {},
    )


def display_live_value(
    call_data,
    field,
):

    value = _clean_live_value(
        (call_data or {}).get(field)
    )

    return value or "Being collected"


# =========================================================
# SEND CLAIM UPDATE TO SHEET ZAP
# =========================================================

def send_claim_to_sheet(
    call_id,
    claimed_by,
    sender_id,
):

    if not CLAIM_SHEET_WEBHOOK_URL:

        logging.error(
            "CLAIM_SHEET_WEBHOOK_URL_MISSING"
        )

        return False


    claimed_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(),
    )


    payload = {
        "call_id": call_id,
        "claim_status": "claimed",
        "claimed_by": claimed_by,
        "claimed_at": claimed_at,
        "sender_id": sender_id,
    }


    request = urllib.request.Request(
        CLAIM_SHEET_WEBHOOK_URL,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response_body = response.read().decode(
                "utf-8"
            )


            logging.info(
                "CLAIM_SHEET_WEBHOOK_SENT "
                "claimant=%s "
                "call_id=%s "
                "claimed_at=%s "
                "response=%s",
                claimed_by,
                call_id,
                claimed_at,
                response_body,
            )


            return True


    except urllib.error.HTTPError as error:

        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )


        logging.error(
            "CLAIM_SHEET_WEBHOOK_HTTP_ERROR "
            "claimant=%s "
            "call_id=%s "
            "status=%s "
            "body=%s",
            claimed_by,
            call_id,
            error.code,
            error_body,
        )


        return False


    except Exception as error:

        logging.exception(
            "CLAIM_SHEET_WEBHOOK_FAILED "
            "claimant=%s "
            "call_id=%s "
            "error=%s",
            claimed_by,
            call_id,
            error,
        )


        return False


# =========================================================
# SEND NOTIFICATION #2 TO GOOGLE CHAT
# =========================================================

def send_claimed_notification(
    call_id,
    claimed_by,
    space_name,
):

    # The claimed card must go back to the space the claim was
    # typed in, never to a hardcoded webhook.
    webhook_url = get_chat_webhook(
        space_name
    )


    if not webhook_url:

        logging.error(
            "CLAIM_NOTIFICATION_NO_WEBHOOK "
            "space=%s call_id=%s",
            space_name,
            call_id,
        )

        return False


    call_data = get_call_data(
        call_id
    )


    # Build the Google Chat message dynamically.
    # Only include seller fields that have an actual value.
    # Unknown fields are hidden instead of showing "Being collected".
    lines = [
        "\U0001F7E2 *LIVE CALL CLAIMED*",
        "",
        "\U0001F64B *Claimed By:* " + claimed_by,
        "\U0001F534 *Status:* Preparing live transfer",
        "",
    ]


    seller_fields = [
        ("lead_source", "\U0001F3F7\uFE0F *Lead Source:*"),
        ("name", "\U0001F464 *Name:*"),
        ("phone", "\U0001F4DE *Phone:*"),
        ("property", "\U0001F3E0 *Property:*"),
        ("caller_type", "\U0001F4CB *Caller Type:*"),
        ("reason", "\U0001F4DD *Reason:*"),
        ("timeline", "⏱️ *Timeline:*"),
        ("asking_price", "\U0001F4B0 *Asking Price:*"),
    ]


    for field, label in seller_fields:

        # An asterisk in the data would close the bold span around
        # the label and leave literal asterisks in the card.
        value = _clean_live_value(
            call_data.get(field)
        ).replace("*", "")

        if value:
            lines.append(
                label + " " + value
            )


    lines.extend([
        "",
        "\U0001F916 Voice AI Agent will finish the seller's "
        "current response and make a natural handoff "
        "to " + claimed_by + ".",
        "",
        "Ref: " + str(call_id),
    ])


    message = "\n".join(lines)


    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({
            "text": message,
        }).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response_body = response.read().decode(
                "utf-8"
            )


            logging.info(
                "CLAIM_NOTIFICATION_SENT "
                "claimant=%s "
                "call_id=%s "
                "space=%s "
                "response=%s",
                claimed_by,
                call_id,
                space_name,
                response_body,
            )


            return True


    except urllib.error.HTTPError as error:

        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )


        logging.error(
            "CLAIM_NOTIFICATION_HTTP_ERROR "
            "claimant=%s "
            "call_id=%s "
            "space=%s "
            "status=%s "
            "body=%s",
            claimed_by,
            call_id,
            space_name,
            error.code,
            error_body,
        )


        return False


    except Exception as error:

        logging.exception(
            "CLAIM_NOTIFICATION_FAILED "
            "claimant=%s "
            "call_id=%s "
            "space=%s "
            "error=%s",
            claimed_by,
            call_id,
            space_name,
            error,
        )


        return False


# =========================================================
# TELL THE TEAM A CALL WENT TO THE ANSWERING SERVICE
# =========================================================

def send_after_hours_notice(clock, from_number):
    """Post the card for a call the agent is about to hand to SAS.

    Posted at the moment the call arrives rather than after the
    transfer, because this is the only point at which we are certain
    the call is an out-of-hours one: the transfer leg carries nothing
    that tells it apart from a Spanish handover or a claim.

    It says "handing to" rather than "handed to" for that reason. If
    the transfer then fails, the agent's own fallback takes the
    seller's details and the usual callback card follows, so the team
    sees the truth either way.
    """

    webhook_url = get_chat_webhook(OTHER_LEADS_SPACE)

    if not webhook_url:

        logging.error(
            "AFTER_HOURS_NOTICE_NO_WEBHOOK space=%s",
            OTHER_LEADS_SPACE,
        )

        return False


    caller = str(from_number or "").strip()

    lines = [
        "\U0001F319 *AFTER HOURS \u2014 HANDING TO THE ANSWERING SERVICE*",
        "",
        "A seller called outside the 8-5 shift.",
        "The Voice AI is passing them to a live answering service now.",
        "",
    ]

    if caller:
        lines.append("\U0001F4DE *Caller:* " + caller)

    lines.append(
        "\U0001F551 *Time:* "
        + clock.get("current_time", "")
        + " on "
        + clock.get("current_day", "")
    )

    lines.append("")
    lines.append(
        "No action needed now \u2014 the message reaches you in the morning."
    )

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps({
            "text": "\n".join(lines),
        }).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response.read()

            logging.info(
                "AFTER_HOURS_NOTICE_SENT caller=%s time=%s",
                caller,
                clock.get("current_time", ""),
            )

            return True

    except Exception as error:

        # A failed card must never stop the call being answered.
        logging.exception(
            "AFTER_HOURS_NOTICE_FAILED caller=%s error=%s",
            caller,
            error,
        )

        return False


# =========================================================
# REPLY INSIDE A CHAT THREAD
# =========================================================

def post_thread_reply(
    space_name,
    thread_id,
    text,
):

    webhook_url = get_chat_webhook(
        space_name
    )


    if not webhook_url:

        logging.error(
            "THREAD_REPLY_NO_WEBHOOK space=%s",
            space_name,
        )

        return False


    # The incoming webhook posts a new thread by default; this asks it
    # to reply inside the existing one instead.
    separator = "&" if "?" in webhook_url else "?"

    url = (
        webhook_url
        + separator
        + "messageReplyOption="
        + "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"
    )


    body = {
        "text": text,
    }


    if thread_id:
        body["thread"] = {"name": thread_id}


    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response.read()


            logging.info(
                "THREAD_REPLY_SENT thread=%s space=%s",
                thread_id,
                space_name,
            )


            return True


    except urllib.error.HTTPError as error:

        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )


        logging.error(
            "THREAD_REPLY_HTTP_ERROR "
            "thread=%s status=%s body=%s",
            thread_id,
            error.code,
            error_body,
        )


        return False


    except Exception as error:

        logging.exception(
            "THREAD_REPLY_FAILED thread=%s error=%s",
            thread_id,
            error,
        )


        return False


# =========================================================
# SEND AN APPOINTMENT TO THE INTAKE INBOX ZAP
# =========================================================

def send_booking_to_intake(fields):

    if not INTAKE_WEBHOOK_URL:

        logging.error(
            "INTAKE_WEBHOOK_URL_MISSING"
        )

        return False


    request = urllib.request.Request(
        INTAKE_WEBHOOK_URL,
        data=json.dumps(fields).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
        },
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response_body = response.read().decode(
                "utf-8"
            )


            logging.info(
                "INTAKE_ROW_SENT "
                "visit_date=%s visit_time=%s address=%s response=%s",
                fields.get("visit_date", ""),
                fields.get("visit_time", ""),
                fields.get("property_address", ""),
                response_body,
            )


            return True


    except urllib.error.HTTPError as error:

        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )


        logging.error(
            "INTAKE_ROW_HTTP_ERROR status=%s body=%s",
            error.code,
            error_body,
        )


        return False


    except Exception as error:

        logging.exception(
            "INTAKE_ROW_FAILED error=%s",
            error,
        )


        return False


# =========================================================
# SEND CLAIM TO RETELL
# =========================================================

def send_claim_to_retell(
    call_id,
    claimed_by,
):

    api_key = os.environ.get(
        "RETELL_API_KEY",
        "",
    )


    if not api_key:

        logging.error(
            "RETELL_API_KEY_MISSING"
        )

        return False


    # -----------------------------------------------------
    # THEA
    # -----------------------------------------------------

    if claimed_by == "Thea":

        override_variables = {
            "claimed_by": "Thea",
        }


        additional_context = (
            "CLAIM_DETECTED: Thea has claimed this live call. "
            "Stop asking new intake questions. "
            "Do not interrupt the seller. "
            "If the seller is speaking, let them finish. "
            "Then acknowledge naturally and say exactly: "
            "\"I have someone available to help you now. "
            "Let me connect you.\" "
            "Immediately call transfer_to_thea. "
            "Do NOT call transfer_to_claimant or transfer_to_juan."
        )


    # -----------------------------------------------------
    # JUAN
    # -----------------------------------------------------

    elif claimed_by == "Juan":

        override_variables = {
            "claimed_by": "Juan",
        }


        additional_context = (
            "CLAIM_DETECTED: Juan has claimed this live call. "
            "Stop asking new intake questions. "
            "Do not interrupt the seller. "
            "If the seller is speaking, let them finish. "
            "Then acknowledge naturally and say exactly: "
            "\"I have someone available to help you now. "
            "Let me connect you.\" "
            "Immediately call transfer_to_juan. "
            "Do NOT call transfer_to_claimant or transfer_to_thea."
        )


    # -----------------------------------------------------
    # EVERYONE ELSE
    #
    # Thea and Juan have their own Retell functions with the number
    # built in. Everybody else is dialled through transfer_to_claimant,
    # which takes the number from claim_phone — so adding a rep is a
    # roster entry, not a new branch here.
    # -----------------------------------------------------

    else:

        claim_phone = phone_for_claimant(claimed_by)


        if not claim_phone:

            # The claim was valid, the person is known, and the only
            # missing piece is a number to ring. Say that precisely,
            # because "unknown claimant" sent us looking in the wrong
            # place last time.

            logging.error(
                "CLAIMANT_PHONE_MISSING claimant=%s",
                claimed_by,
            )

            return False


        override_variables = {
            "claimed_by": claimed_by,
            "claim_phone": claim_phone,
        }


        additional_context = (
            "CLAIM_DETECTED: " + str(claimed_by) +
            " has claimed this live call. "
            "Stop asking new intake questions. "
            "Do not interrupt the seller. "
            "If the seller is speaking, let them finish. "
            "Then acknowledge naturally and say exactly: "
            "\"I have someone available to help you now. "
            "Let me connect you.\" "
            "Immediately call transfer_to_claimant. "
            "Do NOT call transfer_to_thea or transfer_to_juan."
        )


    url = (
        "https://api.retellai.com/v2/"
        "update-live-call/" + str(call_id)
    )


    payload = {

        "fields_to_override": {

            "override_dynamic_variables":
                override_variables
        },

        "call_control": {

            "additional_context":
                additional_context,

            "trigger_response":
                True,
        },
    }


    request = urllib.request.Request(
        url,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        method="PATCH",
        headers={

            "Authorization":
                "Bearer " + api_key,

            "Content-Type":
                "application/json",
        },
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=10,
        ) as response:

            response_body = response.read().decode(
                "utf-8"
            )


            logging.info(
                "RETELL_LIVE_CALL_UPDATED "
                "claimant=%s "
                "call_id=%s "
                "response=%s",
                claimed_by,
                call_id,
                response_body,
            )


            return True


    except urllib.error.HTTPError as error:

        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )


        logging.error(
            "RETELL_UPDATE_HTTP_ERROR "
            "claimant=%s "
            "call_id=%s "
            "status=%s "
            "body=%s",
            claimed_by,
            call_id,
            error.code,
            error_body,
        )


        return False


    except Exception as error:

        logging.exception(
            "RETELL_UPDATE_FAILED "
            "claimant=%s "
            "call_id=%s "
            "error=%s",
            claimed_by,
            call_id,
            error,
        )


        return False


# =========================================================
# HANDLE A REPLY UNDER A HUMAN-ANSWERED CALL CARD
# =========================================================

def person_from_sender(sender_id):

    record = CLAIMANTS.get(
        str(sender_id or "").strip(),
    )

    return record["name"] if record else ""


def phone_for_claimant(name):
    """The number Retell should dial for this person, or "" if unset."""

    wanted = str(name or "").strip()

    for record in CLAIMANTS.values():

        if record["name"] == wanted and record["phone"]:
            return record["phone"]

    # Cherry predates the roster and still carries her own variable.
    if wanted == "Cherry":
        return os.environ.get("CHERRY_PHONE", "").strip()

    return ""


def handle_answered_reply(
    context,
    space_name,
    thread_id,
    sender_id,
    text,
):

    normalized = normalize_claim_text(text)

    person = person_from_sender(sender_id)


    # ---- no appointment ----------------------------------

    if looks_like_no_appointment(normalized):

        logging.info(
            "ANSWERED_CALL_NO_APPOINTMENT "
            "thread=%s by=%s text=%s",
            thread_id,
            person or sender_id,
            text,
        )


        post_thread_reply(
            space_name,
            thread_id,
            "\u2705 Noted \u2014 no appointment from this call.",
        )


        return


    # ---- anything that is not an attempt to book ---------

    if not looks_like_booking(text):

        logging.info(
            "ANSWERED_CALL_REPLY_IGNORED "
            "thread=%s by=%s text=%s",
            thread_id,
            person or sender_id,
            text,
        )


        return


    booking = parse_booking(text)

    # The property address is already on the card, taken from the REI
    # contact, so it only has to be typed when the visit is somewhere
    # else. Anything typed wins over the card.
    address = booking["address"] or context.get("address", "")


    # ---- an attempt to book, but not enough to act on ----

    missing = []

    if not booking["date"]:
        missing.append("the day")

    if not booking["time_text"]:
        missing.append("the time")

    # The address is optional now: a row with a phone and no address is
    # parked, and the office PC fills the address in from REI. Only ask
    # when there is neither, since then there is nothing to look up.
    if not address and not context.get("phone", ""):
        missing.append("the property address")


    if missing:

        logging.info(
            "ANSWERED_CALL_BOOKING_INCOMPLETE "
            "thread=%s missing=%s text=%s",
            thread_id,
            ",".join(missing),
            text,
        )


        if missing == ["the time"]:
            hint = "Reply with the time only, e.g. *2pm*"

        elif missing == ["the day"]:
            hint = "Reply with the day only, e.g. *Sep 2*"

        else:
            hint = "Reply like this: *Sep 2, 2pm*"


        post_thread_reply(
            space_name,
            thread_id,
            "\u26A0\uFE0F Still need "
            + " and ".join(missing)
            + ".\n"
            + hint,
        )


        return


    # ---- a complete booking ------------------------------

    campaign = context.get("lead_source", "")

    task_body_parts = [
        "Human-answered call.",
    ]

    if campaign:
        task_body_parts.append("Campaign " + campaign + ".")

    if person:
        task_body_parts.append("Booked by " + person + ".")

    if booking["time_text"]:
        task_body_parts.append(
            "Agreed time " + booking["time_text"] + "."
        )

    task_body_parts.append("Ref " + str(thread_id))


    fields = {
        "seller_name": context.get("name", ""),
        "phone": context.get("phone", ""),
        "property_address": address,
        "visit_date": booking["date_text"],
        "visit_time": booking["time_text"],
        "assigned_visitor": ASSIGNED_VISITOR,
        "lead_source": sheet_lead_source(campaign),
        "task_body": " ".join(task_body_parts),
        "answered_by": person,
        "campaign_tag": campaign,
        "thread_id": thread_id,
    }


    logging.info(
        "ANSWERED_CALL_BOOKING_PARSED "
        "thread=%s date=%s time=%s address=%s "
        "lead_source=%s by=%s",
        thread_id,
        fields["visit_date"],
        fields["visit_time"],
        fields["property_address"],
        fields["lead_source"],
        person,
    )


    sent = send_booking_to_intake(fields)


    if sent:

        confirmation_lines = [
            "\u2705 *PROPERTY VISIT BOOKED*",
            "",
        ]

        if fields["seller_name"]:
            confirmation_lines.append(
                "\U0001F464 " + fields["seller_name"]
            )

        confirmation_lines.append(
            "\U0001F4C5 "
            + fields["visit_date"]
            + (
                " at " + fields["visit_time"]
                if fields["visit_time"] else ""
            )
        )

        if fields["property_address"]:

            confirmation_lines.append(
                "\U0001F3E0 " + fields["property_address"]
            )

        else:

            # Parked: the office PC looks the address up from REI by phone.
            confirmation_lines.append(
                "\U0001F3E0 Address will be filled in from REI"
            )

        confirmation_lines.append(
            "\U0001F697 Assigned: " + ASSIGNED_VISITOR
        )

        confirmation_lines.append("")

        confirmation_lines.append(
            "Sent to Property Visit \u2014 calendar event follows."
        )

        confirmation = "\n".join(confirmation_lines)

    else:

        confirmation = (
            "\u26A0\uFE0F I read that as "
            + fields["visit_date"]
            + (
                " at " + fields["visit_time"]
                if fields["visit_time"] else ""
            )
            + " \u00B7 "
            + fields["property_address"]
            + "\nbut could not save it. Please add it by hand."
        )


    post_thread_reply(
        space_name,
        thread_id,
        confirmation,
    )


# =========================================================
# MAIN CLOUD RUN ENDPOINT
# =========================================================

@functions_framework.http
def hello_http(request):


    # -----------------------------------------------------
    # HEALTH CHECK
    # -----------------------------------------------------

    if request.method != "POST":

        return (
            "THB Voice AI Listener is running",
            200,
        )


    payload = request.get_json(
        silent=True
    ) or {}


    # Zapier sends a list when "Wrap Request In Array" is on, which
    # used to crash here rather than say what was wrong.
    if isinstance(payload, list):

        payload = (
            payload[0]
            if payload and isinstance(payload[0], dict)
            else {}
        )


    if not isinstance(payload, dict):
        payload = {}


    # A value typed into Zapier often carries a trailing space, and an
    # action that misses by one invisible character looks exactly like
    # an action nobody recognises. Normalise it once, here, so every
    # branch below compares against something clean.
    raw_action = payload.get("action")

    if isinstance(raw_action, str):

        trimmed_action = raw_action.strip()

        if trimmed_action != raw_action:

            logging.info(
                "ACTION_WHITESPACE_TRIMMED action=%r",
                raw_action,
            )

        payload["action"] = trimmed_action


    # =====================================================
    # RETELL ASKS WHAT TIME IT IS
    #
    # Retell calls this the moment a call arrives, before the agent
    # speaks, and whatever comes back becomes a dynamic variable for
    # that call. It is the only way the agent learns the hour - and
    # the hour is what decides whether an out-of-hours seller goes to
    # the answering service or stays with us.
    #
    # Never raise from here. A failure means Retell runs the call with
    # no variables at all, which is how {{current_hour}} came to be
    # empty on every call for weeks without anyone noticing.
    # =====================================================

    if payload.get("event") == "call_inbound":

        clock = office_clock()

        inbound = payload.get("call_inbound")

        if not isinstance(inbound, dict):
            inbound = {}

        logging.info(
            "CALL_INBOUND_CLOCK day=%s hour=%s open=%s from=%s",
            clock["current_day"],
            clock["current_hour"],
            clock["office_open"],
            inbound.get("from_number", ""),
        )

        response = {
            "dynamic_variables": clock,
        }

        if clock["office_open"] == "no":

            if AFTER_HOURS_AGENT_ID:

                response["override_agent_id"] = AFTER_HOURS_AGENT_ID

            else:

                # Worth saying out loud: without it the main agent
                # takes the call and the seller gets an intake nobody
                # is awake to act on.
                logging.warning(
                    "AFTER_HOURS_AGENT_ID_NOT_SET"
                )

            send_after_hours_notice(
                clock,
                inbound.get("from_number", ""),
            )

        return (
            json.dumps({
                "call_inbound": response,
            }),
            200,
            {
                "Content-Type":
                    "application/json"
            },
        )


    # =====================================================
    # RETELL / ZAPIER:
    # UPDATE LIVE SELLER DATA FOR A CALL
    # =====================================================

    if payload.get("action") == "update_call_data":

        call_id = str(
            payload.get(
                "call_id",
                "",
            )
        ).strip()


        if not call_id:

            logging.error(
                "UPDATE_CALL_DATA_MISSING_CALL_ID"
            )

            return (
                json.dumps({
                    "success": False,
                    "error": "call_id missing",
                }),
                400,
                {
                    "Content-Type":
                        "application/json"
                },
            )


        call_data = merge_call_data(
            call_id,
            payload,
        )


        return (
            json.dumps({
                "success": True,
                "call_id": call_id,
                "call_data": {
                    field: call_data.get(field, "")
                    for field in LIVE_DATA_FIELDS
                },
            }),
            200,
            {
                "Content-Type":
                    "application/json"
            },
        )


    # =====================================================
    # ZAPIER:
    # A HUMAN ANSWERED THIS CALL
    # Registers the card's thread so that (a) a claim word typed
    # under it never transfers a seller call, and (b) a "booked"
    # reply can be read as an appointment.
    # =====================================================

    # =====================================================
    # ZAPIER:
    # POST A MESSAGE INTO A CHAT THREAD
    # Zapier's Custom Request drops the nested "thread" object, so
    # anything that must land inside a thread — the delayed
    # "not logged" alert, for one — is posted from here instead.
    # =====================================================

    if payload.get("action") == "post_thread_message":

        thread_id = str(
            payload.get(
                "thread_id",
                "",
            )
        ).strip()

        message_text = str(
            payload.get(
                "text",
                "",
            )
        ).strip()


        if not thread_id or not message_text:

            logging.error(
                "POST_THREAD_MESSAGE_MISSING "
                "thread=%s text_len=%d",
                thread_id,
                len(message_text),
            )

            return (
                json.dumps({
                    "success": False,
                    "error": "thread_id and text are both required",
                }),
                400,
                {
                    "Content-Type":
                        "application/json"
                },
            )


        space_name = space_from_resource(thread_id)


        posted = post_thread_reply(
            space_name,
            thread_id,
            message_text,
        )


        logging.info(
            "POST_THREAD_MESSAGE "
            "space=%s thread=%s posted=%s",
            space_name,
            thread_id,
            posted,
        )


        return (
            json.dumps({
                "success": bool(posted),
                "thread_id": thread_id,
            }),
            200,
            {
                "Content-Type":
                    "application/json"
            },
        )


    if payload.get("action") in ("answered_call", "ignore_thread"):

        thread_id = str(
            payload.get(
                "thread_id",
                "",
            )
        ).strip()


        if not thread_id:

            logging.error(
                "ANSWERED_CALL_MISSING_THREAD_ID"
            )

            return (
                json.dumps({
                    "success": False,
                    "error": "thread_id missing",
                }),
                400,
                {
                    "Content-Type":
                        "application/json"
                },
            )


        context = {
            "phone": _clean_live_value(
                payload.get("phone")
            ),
            "name": _clean_live_value(
                payload.get("name")
            ),
            "lead_source": _clean_live_value(
                payload.get("lead_source")
            ),
            # Printed on the card, and used when the reply carries no
            # address of its own.
            "address": _clean_live_value(
                payload.get("address")
            ),
            # Lets a booking typed outside the thread still find this
            # card.
            "space": space_from_resource(thread_id),
        }


        mark_answered_thread(thread_id, context)


        logging.info(
            "ANSWERED_CALL_THREAD_MARKED "
            "thread=%s phone=%s lead_source=%s",
            thread_id,
            context["phone"],
            context["lead_source"],
        )


        return (
            json.dumps({
                "success": True,
                "thread_id": thread_id,
            }),
            200,
            {
                "Content-Type":
                    "application/json"
            },
        )


    # =====================================================
    # ZAPIER:
    # MAP GOOGLE CHAT NOTIFICATION TO RETELL CALL
    # =====================================================

    # =====================================================
    # A LIVE CALL HAS CHANGED LANGUAGE
    #
    # The English agent hands the seller to the Spanish agent, and
    # Retell logs that as a brand new call. Nothing on the new leg
    # names the call it came from - not the seller's number, not a
    # reference - so the only link available is time: the card posted
    # moments ago in this space is the one the seller is on.
    #
    # Rather than post a second card for what is one seller, reply
    # under the card that already exists and point the claim at the
    # leg that is now live.
    # =====================================================

    if payload.get("action") == "language_switch":

        call_id = str(
            payload.get(
                "call_id",
                "",
            )
        ).strip()


        if not call_id:

            logging.error(
                "LANGUAGE_SWITCH_MISSING_CALL_ID"
            )


            return (
                json.dumps({
                    "success": False,
                    "error": "call_id missing",
                }),
                400,
                {
                    "Content-Type":
                        "application/json"
                },
            )


        language = str(
            payload.get(
                "language",
                "",
            )
        ).strip() or "Spanish"


        space_name = (
            space_from_resource(
                payload.get("space")
            )
            or OTHER_LEADS_SPACE
        )


        latest = LATEST_CALLS.get(space_name)


        too_old = (
            not latest
            or time.time()
            - latest.get("mapped_at", 0)
            > LANGUAGE_SWITCH_WINDOW
        )


        if too_old:

            # Better to say nothing than to hang a Spanish notice under
            # a card from an unrelated seller.

            logging.warning(
                "LANGUAGE_SWITCH_NO_LIVE_CARD "
                "space=%s call_id=%s",
                space_name,
                call_id,
            )


            return (
                json.dumps({
                    "success": False,
                    "error":
                        "no live card to update",
                }),
                200,
                {
                    "Content-Type":
                        "application/json"
                },
            )


        thread_id = str(
            latest.get("thread_id", "")
        ).strip()


        previous_call_id = str(
            latest.get("call_id", "")
        ).strip()


        lines = []
        lines.append(
            "\U0001F1EA\U0001F1F8 *NOW SPEAKING "
            + language.upper()
            + "*"
        )
        lines.append("")
        lines.append(
            "The seller could not carry on in English."
        )
        lines.append(
            "Handed to the "
            + language
            + " AI \u2014 the call is still live."
        )
        lines.append("")
        lines.append(
            "A "
            + language
            + " speaker should take this one."
        )
        lines.append(
            "\U0001F4DE Reply \"ME\" to claim."
        )
        lines.append("")
        # Chat collapses a thread to "1 reply", which is easy to walk
        # past while a seller waits on the line. A mention pushes the
        # notification out even when the thread stays closed.
        lines.append(MENTION_ALL)
        lines.append("")
        lines.append("Ref: " + call_id)


        posted = post_thread_reply(
            space_name,
            thread_id,
            "\n".join(lines),
        )


        # The claim has to reach the leg the seller is actually on, so
        # both maps move to the new call id while the thread stays put.
        switched_at = time.time()

        THREAD_CALLS[thread_id] = {
            "call_id": call_id,
            "mapped_at": switched_at,
        }

        LATEST_CALLS[space_name] = {
            "call_id": call_id,
            "thread_id": thread_id,
            "mapped_at": switched_at,
        }

        merge_call_data(call_id, payload)


        logging.info(
            "LANGUAGE_SWITCHED "
            "space=%s thread=%s from_call=%s "
            "to_call=%s language=%s posted=%s",
            space_name,
            thread_id,
            previous_call_id,
            call_id,
            language,
            bool(posted),
        )


        return (
            json.dumps({
                "success": True,
                "thread_id": thread_id,
                "call_id": call_id,
                "replaced_call_id": previous_call_id,
                "posted": bool(posted),
            }),
            200,
            {
                "Content-Type":
                    "application/json"
            },
        )


    if payload.get("action") == "map_thread":

        thread_id = str(
            payload.get(
                "thread_id",
                "",
            )
        ).strip()


        call_id = str(
            payload.get(
                "call_id",
                "",
            )
        ).strip()


        if not thread_id or not call_id:

            logging.error(
                "MAP_THREAD_MISSING_DATA "
                "thread=%s call_id=%s",
                thread_id,
                call_id,
            )


            return (
                json.dumps({
                    "success": False,
                    "error":
                        "thread_id or call_id missing",
                }),
                400,
                {
                    "Content-Type":
                        "application/json"
                },
            )


        # Store any seller information Zapier already has at
        # the time the live Google Chat thread is mapped.
        merge_call_data(
            call_id,
            payload,
        )


        mapped_at = time.time()


        THREAD_CALLS[thread_id] = {
            "call_id": call_id,
            "mapped_at": mapped_at,
        }


        # Zapier does not send the space, but the thread name
        # it sends already contains it:
        # spaces/XXX/threads/YYY
        space_name = (
            space_from_resource(
                payload.get("space")
            )
            or space_from_resource(
                thread_id
            )
            or TV_SPACE
        )


        LATEST_CALLS[space_name] = {
            "call_id": call_id,
            "thread_id": thread_id,
            "mapped_at": mapped_at,
        }


        logging.info(
            "THREAD_CALL_MAPPED "
            "thread=%s call_id=%s space=%s",
            thread_id,
            call_id,
            space_name,
        )


        logging.info(
            "LATEST_CALL_SET "
            "space=%s call_id=%s",
            space_name,
            call_id,
        )


        return (
            json.dumps({
                "success": True,
                "thread_id": thread_id,
                "call_id": call_id,
                "space": space_name,
            }),
            200,
            {
                "Content-Type":
                    "application/json"
            },
        )


    # =====================================================
    # GOOGLE CHAT / WORKSPACE EVENTS
    # =====================================================

    chat_message = None
    event_type = None
    source = "unknown"


    direct_message = payload.get(
        "message"
    )


    if (
        isinstance(
            direct_message,
            dict,
        )
        and (
            "text" in direct_message
            or "sender" in direct_message
        )
        and "data" not in direct_message
    ):

        chat_message = direct_message

        event_type = payload.get(
            "type"
        )

        source = (
            "google-chat-interaction"
        )


    else:

        pubsub_message = payload.get(
            "message",
            {},
        )


        if (
            isinstance(
                pubsub_message,
                dict,
            )
            and pubsub_message.get(
                "data"
            )
        ):

            try:

                decoded = base64.b64decode(
                    pubsub_message["data"]
                ).decode(
                    "utf-8"
                )


                event_data = json.loads(
                    decoded
                )


                logging.info(
                    "WORKSPACE_EVENT_DATA %s",
                    json.dumps(
                        event_data,
                        ensure_ascii=False,
                    ),
                )


                chat_message = (
                    event_data.get(
                        "message"
                    )
                )


                attributes = (
                    pubsub_message.get(
                        "attributes",
                        {},
                    )
                )


                event_type = (
                    attributes.get(
                        "ce-type"
                    )
                    or attributes.get(
                        "ce_type"
                    )
                )


                source = (
                    "workspace-events"
                )


            except Exception as error:

                logging.exception(
                    "PUBSUB_DECODE_FAILED %s",
                    error,
                )


    # -----------------------------------------------------
    # NON-MESSAGE WORKSPACE EVENT
    # -----------------------------------------------------

    if not chat_message:

        logging.info(
            "EVENT_RECEIVED "
            "source=%s event_type=%s",
            source,
            event_type,
        )


        return (
            "OK",
            200,
        )


    # =====================================================
    # EXTRACT MESSAGE DATA
    # =====================================================

    sender = chat_message.get(
        "sender",
        {},
    ) or {}


    thread = chat_message.get(
        "thread",
        {},
    ) or {}


    sender_id = sender.get(
        "name",
        "",
    )


    thread_id = thread.get(
        "name",
        "",
    )


    text = (
        chat_message.get(
            "text"
        )
        or chat_message.get(
            "argumentText"
        )
        or chat_message.get(
            "formattedText"
        )
        or ""
    ).strip()


    message_id = chat_message.get(
        "name",
        "",
    )


    # Which Chat space did this message come from?
    # Everything below is scoped to this space.
    space_name = extract_space_name(
        chat_message,
        thread_id,
        message_id,
    )


    logging.info(
        "GOOGLE_CHAT_MESSAGE "
        "text=%s "
        "sender_id=%s "
        "space=%s "
        "thread=%s "
        "message_id=%s",
        text,
        sender_id,
        space_name,
        thread_id,
        message_id,
    )


    # =====================================================
    # NEVER READ OUR OWN MESSAGES
    # The cards and confirmations this service posts come back as
    # events. A confirmation quotes the date it just read, so without
    # this guard it would be taken for a new booking and answered
    # again, forever.
    # =====================================================

    sender_type = str(
        sender.get("type", "")
    ).strip().upper()


    if sender_type == "BOT" or sender.get("isAnonymous") is True:

        logging.info(
            "GOOGLE_CHAT_MESSAGE_FROM_APP_IGNORED "
            "space=%s thread=%s",
            space_name,
            thread_id,
        )

        return (
            "OK",
            200,
        )


    # =====================================================
    # HUMAN-ANSWERED CALL THREADS
    # These share the space with live call alerts, so a claim word
    # typed under one must never transfer a seller call. A "booked"
    # reply here is an appointment, not a claim.
    # =====================================================

    answered = answered_thread(thread_id)

    answered_target = thread_id


    if answered is None:

        # Typed in the main box, or quoted rather than replied. Only a
        # message carrying a real date is adopted, so claim words are
        # never captured by an open card.
        fallback_key, fallback = latest_answered_in_space(space_name)

        if fallback is not None and looks_like_booking(text):

            logging.info(
                "ANSWERED_CALL_OUT_OF_THREAD "
                "space=%s typed_in=%s adopted=%s text=%s",
                space_name,
                thread_id,
                fallback_key,
                text,
            )

            answered = fallback
            answered_target = fallback_key


    if answered is not None:

        handle_answered_reply(
            answered,
            space_name,
            answered_target,
            sender_id,
            text,
        )


        return (
            "OK",
            200,
        )


    # =====================================================
    # CHECK CLAIM WORD / PHRASE
    # =====================================================

    normalized_text = normalize_claim_text(
        text
    )


    # Explicit decline = never transfer.

    if normalized_text in NEGATIVE_CLAIM_PHRASES:

        logging.info(
            "CLAIM_DECLINED "
            "text=%s "
            "normalized=%s "
            "sender_id=%s "
            "space=%s",
            text,
            normalized_text,
            sender_id,
            space_name,
        )


        return (
            "OK",
            200,
        )


    # Anything not explicitly approved is ignored.

    if normalized_text not in CLAIM_PHRASES:

        logging.info(
            "NON_CLAIM_MESSAGE_IGNORED "
            "text=%s "
            "normalized=%s "
            "sender_id=%s "
            "space=%s",
            text,
            normalized_text,
            sender_id,
            space_name,
        )


        return (
            "OK",
            200,
        )


    logging.info(
        "VALID_CLAIM_PHRASE "
        "text=%s "
        "normalized=%s "
        "sender_id=%s "
        "space=%s",
        text,
        normalized_text,
        sender_id,
        space_name,
    )


    # =====================================================
    # IDENTIFY WHO CLAIMED
    # =====================================================

    claimed_by = person_from_sender(sender_id)


    if not claimed_by:

        logging.warning(
            "CLAIM_REJECTED_UNKNOWN_USER "
            "sender_id=%s space=%s",
            sender_id,
            space_name,
        )


        return (
            "OK",
            200,
        )


    # =====================================================
    # TRY EXACT THREAD MATCH FIRST
    # =====================================================

    call_id = ""


    exact_match = THREAD_CALLS.get(
        thread_id
    )


    if exact_match:

        age = (
            time.time()
            - exact_match[
                "mapped_at"
            ]
        )


        if age <= 120:

            call_id = exact_match[
                "call_id"
            ]


            logging.info(
                "CLAIM_EXACT_THREAD_MATCH "
                "claimant=%s "
                "call_id=%s "
                "space=%s "
                "age=%.1f",
                claimed_by,
                call_id,
                space_name,
                age,
            )


    # =====================================================
    # TEMPORARY GOOGLE CHAT THREAD FALLBACK
    # Scoped to the space the claim came from, so a claim in
    # one space can never pick up another space's call.
    # =====================================================

    if not call_id:

        latest = LATEST_CALLS.get(
            space_name,
            {},
        )


        latest_call_id = (
            latest.get(
                "call_id",
                "",
            )
        )


        latest_mapped_at = (
            latest.get(
                "mapped_at",
                0,
            )
        )


        age = (
            time.time()
            - latest_mapped_at
        )


        if (
            latest_call_id
            and age <= 120
        ):

            call_id = latest_call_id


            logging.info(
                "CLAIM_LATEST_CALL_FALLBACK "
                "claimant=%s "
                "call_id=%s "
                "space=%s "
                "original_thread=%s "
                "claim_thread=%s "
                "age=%.1f",
                claimed_by,
                call_id,
                space_name,
                latest.get(
                    "thread_id",
                    "",
                ),
                thread_id,
                age,
            )


    # =====================================================
    # NO VALID CALL FOUND
    # =====================================================

    if not call_id:

        logging.warning(
            "CLAIM_NO_ACTIVE_CALL "
            "claimant=%s "
            "sender_id=%s "
            "space=%s "
            "thread=%s",
            claimed_by,
            sender_id,
            space_name,
            thread_id,
        )


        return (
            "OK",
            200,
        )


    # =====================================================
    # FIRST PERSON TO CLAIM WINS
    # =====================================================

    if call_id in CLAIMED_CALLS:

        existing_claim = (
            CLAIMED_CALLS[
                call_id
            ]
        )


        logging.warning(
            "CALL_ALREADY_CLAIMED "
            "call_id=%s "
            "attempted_by=%s "
            "claimed_by=%s",
            call_id,
            claimed_by,
            existing_claim.get(
                "claimed_by",
                "",
            ),
        )


        return (
            "OK",
            200,
        )


    # Lock immediately.

    CLAIMED_CALLS[call_id] = {
        "claimed_by": claimed_by,
        "claimed_at": time.time(),
        "sender_id": sender_id,
        "claim_text": normalized_text,
        "space": space_name,
    }


    logging.info(
        "CLAIM_MATCHED "
        "claimant=%s "
        "sender_id=%s "
        "call_id=%s "
        "space=%s "
        "claim_text=%s",
        claimed_by,
        sender_id,
        call_id,
        space_name,
        normalized_text,
    )


    # =====================================================
    # SEND CLAIM TO RETELL
    # =====================================================

    success = send_claim_to_retell(
        call_id,
        claimed_by,
    )


    if success:

        logging.info(
            "TRANSFER_SIGNAL_SENT "
            "claimant=%s "
            "call_id=%s",
            claimed_by,
            call_id,
        )


        # ================================================
        # UPDATE LIVE CALL CLAIMS SHEET
        # ================================================

        sheet_success = send_claim_to_sheet(
            call_id,
            claimed_by,
            sender_id,
        )


        if sheet_success:

            logging.info(
                "CLAIM_SHEET_UPDATE_TRIGGERED "
                "claimant=%s "
                "call_id=%s",
                claimed_by,
                call_id,
            )


        else:

            logging.error(
                "CLAIM_SHEET_UPDATE_TRIGGER_FAILED "
                "claimant=%s "
                "call_id=%s",
                claimed_by,
                call_id,
            )


        # ================================================
        # NOTIFICATION #2 — LIVE CALL CLAIMED
        # Posted back to the space the claim came from.
        # ================================================

        send_claimed_notification(
            call_id,
            claimed_by,
            space_name,
        )


    else:

        logging.error(
            "TRANSFER_SIGNAL_FAILED "
            "claimant=%s "
            "call_id=%s",
            claimed_by,
            call_id,
        )


        # Unlock if Retell did not accept the claim.

        CLAIMED_CALLS.pop(
            call_id,
            None,
        )


    return (
        "OK",
        200,
    )
