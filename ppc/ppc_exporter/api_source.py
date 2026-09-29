"""The preferred path: the official Google Ads API.

Credentials are Google's current model (developer tokens were retired on
2026-09-09): API access belongs to the Google Cloud project that owns the
credentials, and either a service-account key file or an OAuth refresh
token proves who is asking. See ppc/README.md for the setup steps.
"""

import base64
import os
import re
import time
import urllib.parse

from . import queries, schema
from .settings import digits

CONSOLE_OVERVIEW = "https://console.cloud.google.com/google/ads-apis/overview"
ENABLE_API = "https://console.cloud.google.com/flows/enableapi?apiid=googleads.googleapis.com"
OAUTH_SCOPE = "https://www.googleapis.com/auth/adwords"
# Uploading lead outcomes goes through the Data Manager API, which needs its
# own permission on the same sign-in.
DATAMANAGER_SCOPE = "https://www.googleapis.com/auth/datamanager"
# refresh-token receives Google's answer here. Desktop-app OAuth clients accept
# any local address; a Web-application client must list this exact one
# (no trailing slash) under Authorized redirect URIs. Not 8080: local servers
# such as THB's Call Coach on the office PC already use it.
REDIRECT_HOST, REDIRECT_PORT = "127.0.0.1", 8723
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"


class ApiNotConfigured(Exception):
    def __init__(self, missing):
        self.missing = missing
        super().__init__("; ".join(missing))


class ApiAccessError(Exception):
    """Google refused the request for a reason no retry will fix."""


# ---------------------------------------------------------------- settings --


def missing_settings(settings):
    """What still has to be filled in before an API export can run."""

    api = settings["api"]
    missing = []

    if len(digits(settings.get("customer_id"))) != 10:
        missing.append(
            "customer_id: the 10-digit Google Ads account ID shown at the top of "
            "the Google Ads screen (e.g. 123-456-7890)"
        )

    key_file = api.get("json_key_file_path")
    oauth = {k: api.get(k) for k in ("client_id", "client_secret", "refresh_token")}
    if key_file:
        path = os.path.expanduser(key_file)
        if not os.path.isfile(path):
            missing.append(f"json_key_file_path: no file at {path}")
    elif not all(oauth.values()):
        if any(oauth.values()):
            gaps = ", ".join(k for k, v in oauth.items() if not v)
            missing.append(f"OAuth credentials are incomplete, missing: {gaps}")
        else:
            missing.append(
                "credentials: a service-account key file (json_key_file_path), or "
                "OAuth client_id + client_secret + refresh_token"
            )

    login = api.get("login_customer_id")
    if login and len(digits(login)) != 10:
        missing.append("login_customer_id: must be a 10-digit manager account ID, or blank")
    return missing


def build_client(settings):
    from google.ads.googleads.client import GoogleAdsClient

    api = settings["api"]
    config = {"use_proto_plus": True}
    if api.get("json_key_file_path"):
        config["json_key_file_path"] = os.path.expanduser(api["json_key_file_path"])
    else:
        for key in ("client_id", "client_secret", "refresh_token"):
            config[key] = api[key]
    if api.get("login_customer_id"):
        config["login_customer_id"] = digits(api["login_customer_id"])
    if api.get("developer_token"):
        config["developer_token"] = api["developer_token"]
    return GoogleAdsClient.load_from_dict(config)


# ------------------------------------------------------------ reading rows --


def _walk(message, path):
    parent, value = None, message
    parts = path.split(".")
    for part in parts:
        parent, value = value, getattr(value, part)
    return parent, parts[-1], value


def read_field(row, path, kind):
    parent, last, value = _walk(row, path)

    if kind == queries.TEXT or kind == queries.GEO:
        return str(value or "")
    if kind == queries.ID:
        return str(value) if value else ""
    if kind == queries.INT:
        return int(value or 0)
    if kind == queries.FLOAT:
        return float(value or 0)
    if kind == queries.MICROS:
        return (value or 0) / 1_000_000
    if kind == queries.RATIO:
        # Impression share is unset for campaigns it does not apply to;
        # report that as blank, not as 0 %.
        try:
            present = last in parent
        except TypeError:
            present = bool(value)
        return float(value) * 100 if present else None
    if kind == queries.ENUM:
        name = getattr(value, "name", str(value))
        return "" if name in ("UNSPECIFIED", "0") else name
    raise ValueError(f"unknown field kind {kind!r}")


def row_to_dict(row, fields):
    return {column: read_field(row, path, kind) for column, path, kind in fields}


# ---------------------------------------------------------------- errors --


def failure_codes(exception):
    """[(kind, name, message)] for each error inside a GoogleAdsException."""

    codes = []
    failure = getattr(exception, "failure", None)
    for error in getattr(failure, "errors", []) or []:
        code = error.error_code
        pb = type(code).pb(code) if hasattr(type(code), "pb") else code
        kind = pb.WhichOneof("error_code") or ""
        name = ""
        if kind:
            number = getattr(pb, kind)
            enum = pb.DESCRIPTOR.fields_by_name[kind].enum_type
            value = enum.values_by_number.get(number)
            name = value.name if value else str(number)
        codes.append((kind, name, error.message))
    return codes


TEST_ACCESS = (
    "Your Google Cloud project only has Test access, which cannot read real "
    f"accounts. Open {CONSOLE_OVERVIEW} (the same project your credentials "
    'come from), expand "Upgrade access level" and click "Apply for access" '
    "(Explorer). The project needs billing turned on: Google does not upgrade "
    "Free Trial projects."
)

FIXES = {
    ("authorization_error", "CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION"): TEST_ACCESS,
    ("authorization_error", "DEVELOPER_TOKEN_NOT_APPROVED"): TEST_ACCESS,
    ("authorization_error", "USER_PERMISSION_DENIED"): (
        "The Google identity behind these credentials cannot open account {cid}. "
        "In Google Ads go to Admin > Access and security > Users > + and add it "
        "(the service-account email, or the Google account you used for the "
        "refresh token) with Read only access. If you reach THB through a "
        "manager account, set login_customer_id to the manager's ID."
    ),
    ("authorization_error", "CUSTOMER_NOT_ENABLED"): (
        "Google Ads account {cid} is not active (cancelled, suspended or never "
        "finished setup)."
    ),
    ("authorization_error", "PROJECT_DISABLED"): (
        f"The Google Ads API is switched off in your Cloud project. Enable it: {ENABLE_API}"
    ),
    ("authorization_error", "MISSING_TOS"): (
        f"Accept the Google Ads API terms of service on {CONSOLE_OVERVIEW}."
    ),
    ("authorization_error", "INCOMPLETE_SIGNUP"): (
        f"Finish the Google Ads API sign-up on {CONSOLE_OVERVIEW}."
    ),
    ("authorization_error", "INVALID_LOGIN_CUSTOMER_ID_SERVING_CUSTOMER_ID_COMBINATION"): (
        "login_customer_id is not a manager of account {cid}. Clear it if you "
        "have direct access to the account, or set the right manager ID."
    ),
    ("authorization_error", "CLOUD_PROJECT_NOT_UNDER_ORGANIZATION"): (
        "Google says this Cloud project is not under a Google Cloud organization. "
        "Create (or move) the project inside your company's organization and retry."
    ),
    ("authentication_error", "NOT_ADS_USER"): (
        "The Google account behind these credentials has no Google Ads access at "
        "all. Use an account that can open THB's Google Ads."
    ),
    ("authentication_error", "TWO_STEP_VERIFICATION_NOT_ENROLLED"): (
        "Google requires 2-Step Verification on the account used for API access. "
        "Turn it on at https://myaccount.google.com/signinoptions/two-step-verification, "
        "then run: python ppc/export.py refresh-token"
    ),
    ("authentication_error", "CUSTOMER_NOT_FOUND"): (
        "No Google Ads account {cid} exists. Check customer_id against the ID at the "
        "top of the Google Ads screen."
    ),
    ("authentication_error", "CLIENT_CUSTOMER_ID_INVALID"): (
        "customer_id {cid} is not a valid Google Ads account ID."
    ),
    ("request_error", "INVALID_CUSTOMER_ID"): (
        "customer_id {cid} is not a valid Google Ads account ID (10 digits)."
    ),
    ("request_error", "LOGIN_CUSTOMER_ID_PARAMETER_MISSING"): (
        "Your access to {cid} is through a manager account: set login_customer_id "
        "to that manager account's 10-digit ID."
    ),
    ("header_error", "INVALID_LOGIN_CUSTOMER_ID"): (
        "login_customer_id is not a valid manager account ID. Fix it or leave it blank."
    ),
    ("query_error", "REQUESTED_METRICS_FOR_MANAGER"): (
        "customer_id {cid} is a manager (MCC) account, which has no ads of its own. "
        "Put THB's own account ID in customer_id and the manager's ID in "
        "login_customer_id."
    ),
}

for _name in ("OAUTH_TOKEN_INVALID", "OAUTH_TOKEN_EXPIRED", "OAUTH_TOKEN_DISABLED", "OAUTH_TOKEN_REVOKED"):
    FIXES[("authentication_error", _name)] = (
        "The OAuth token is no longer accepted. Run: python ppc/export.py refresh-token"
    )

FATAL_KINDS = {"authentication_error", "authorization_error", "header_error", "quota_error", "request_error"}


def explain_google_ads(exception, customer_id=""):
    codes = failure_codes(exception)
    lines = []
    for kind, name, message in codes:
        fix = FIXES.get((kind, name))
        if fix is None and kind == "quota_error":
            fix = (
                "Google's API quota for this Cloud project is used up. Wait and run it "
                "again later (Explorer access allows 2,880 operations a day)."
            )
        label = f"{kind}.{name}" if kind else "error"
        lines.append(f"{label}: {message}")
        if fix:
            lines.append("  Fix: " + fix.format(cid=customer_id))
    request_id = getattr(exception, "request_id", "")
    if request_id:
        lines.append(f"  (Google request ID {request_id}, useful if you contact Google support)")
    return "\n".join(lines) or str(exception)


def explain(exception, settings):
    """Plain-English cause and fix for anything the API path can raise."""

    customer_id = digits(settings.get("customer_id"))
    if hasattr(exception, "failure"):
        return explain_google_ads(exception, customer_id)

    text = str(exception)
    lowered = text.lower()
    using_key = bool(settings["api"].get("json_key_file_path"))

    if type(exception).__name__ == "RefreshError":
        if "invalid_client" in lowered:
            return (
                f"Google rejected the OAuth client ({text}). client_id / client_secret are "
                "wrong, or that OAuth client was deleted in the Cloud console."
            )
        if "unauthorized_client" in lowered:
            return (
                f"Google rejected the refresh token ({text}). It was created with a "
                "different OAuth client. Run: python ppc/export.py refresh-token"
            )
        if "invalid_grant" in lowered and using_key:
            return (
                f"Google rejected the service-account key ({text}). The service account or "
                "this key no longer exists, or the key is disabled. Create a new JSON key: "
                "Cloud console > IAM & Admin > Service Accounts > (account) > Keys > Add key."
            )
        if "invalid_grant" in lowered:
            return (
                f"The refresh token has expired or was revoked ({text}). If the OAuth "
                "consent screen is External and in Testing, Google expires tokens after "
                "7 days: set it to Internal (Workspace) or publish it. Then run: "
                "python ppc/export.py refresh-token"
            )
        return f"Google refused the credentials: {text}"

    if isinstance(exception, FileNotFoundError):
        return f"Credential file not found: {text}"
    if "has not been used in project" in lowered or "service_disabled" in lowered:
        return f"The Google Ads API is not enabled in your Cloud project. Enable it: {ENABLE_API}\n({text})"
    if "unavailable" in lowered or "failed to connect" in lowered or "transporterror" in type(exception).__name__.lower():
        return f"Could not reach Google ({text}). Check the internet connection and try again."
    return f"{type(exception).__name__}: {text}"


# ------------------------------------------------------------- requests --


def _retrying(call):
    """Run call(), retrying twice on Google's transient server errors."""

    import grpc

    transient = {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.INTERNAL}
    for attempt in range(3):
        try:
            return call()
        except grpc.RpcError as problem:
            code = problem.code() if callable(getattr(problem, "code", None)) else None
            if code in transient and attempt < 2 and not hasattr(problem, "failure"):
                time.sleep(2 * (attempt + 1))
                continue
            raise


def stream(client, customer_id, query):
    service = client.get_service("GoogleAdsService")

    def run():
        rows = []
        for batch in service.search_stream(customer_id=customer_id, query=query):
            rows.extend(batch.results)
        return rows

    return _retrying(run)


def validate(client, customer_id, query):
    service = client.get_service("GoogleAdsService")
    request = client.get_type("SearchGoogleAdsRequest")
    request.customer_id = customer_id
    request.query = query
    request.validate_only = True
    return _retrying(lambda: service.search(request=request))


def is_fatal(exception):
    codes = failure_codes(exception)
    if not codes:
        return True
    for kind, name, _ in codes:
        if kind in FATAL_KINDS or name == "REQUESTED_METRICS_FOR_MANAGER":
            return True
    return False


def fetch_account(client, customer_id):
    from google.ads.googleads.errors import GoogleAdsException

    try:
        rows = stream(client, customer_id, queries.CUSTOMER_QUERY)
    except GoogleAdsException as problem:
        raise ApiAccessError(explain_google_ads(problem, customer_id)) from problem
    if not rows:
        raise ApiAccessError(f"Account {customer_id} returned no customer record.")
    customer = rows[0].customer
    return {
        "customer_id": str(customer.id),
        "name": customer.descriptive_name,
        "currency": customer.currency_code,
        "time_zone": customer.time_zone,
    }


def fetch_report(client, customer_id, report, start, end, log=print):
    """(rows, info). Tries each variant until Google accepts one."""

    from google.ads.googleads.errors import GoogleAdsException

    variants = queries.REPORT_QUERIES[report].variants
    info = {"status": "failed", "variant": None, "errors": []}
    for index, fields in enumerate(variants):
        query = queries.build_query(report, start, end, index)
        try:
            raw = stream(client, customer_id, query)
        except GoogleAdsException as problem:
            if is_fatal(problem):
                raise ApiAccessError(explain_google_ads(problem, customer_id)) from problem
            message = explain_google_ads(problem, customer_id)
            info["errors"].append(f"variant {index}: {message}")
            if index + 1 < len(variants):
                log(f"    Google rejected the full {report} query; retrying with a smaller one.")
            continue
        info.update(status="ok", variant=index, query=query)
        return [row_to_dict(row, fields) for row in raw], info
    return [], info


def resolve_geo(client, customer_id, rows, log=print):
    """Fill city / region / country from Google's geo target names."""

    from google.ads.googleads.errors import GoogleAdsException

    names = sorted({r["geo_target_id"] for r in rows if r.get("geo_target_id")})
    lookup = {}
    for offset in range(0, len(names), 200):
        chunk = names[offset:offset + 200]
        try:
            found = stream(client, customer_id, queries.geo_query(chunk))
        except GoogleAdsException as problem:
            log("    Could not look up city names: " + explain_google_ads(problem, customer_id))
            break
        for row in found:
            geo = row.geo_target_constant
            parts = [p.strip() for p in (geo.canonical_name or "").split(",") if p.strip()]
            lookup[geo.resource_name] = {
                "city": geo.name,
                "region": parts[-2] if len(parts) >= 3 else "",
                "country": parts[-1] if len(parts) >= 2 else geo.country_code,
            }

    for row in rows:
        resource = row.get("geo_target_id") or ""
        place = lookup.get(resource)
        if place:
            row.update(place)
        else:
            row.update(city="(unknown)" if not resource else resource, region="", country="")
        row["geo_target_id"] = resource.rsplit("/", 1)[-1]
    return rows


def export(settings, start, end, log=print):
    """Pull all six reports. Returns (reports, meta)."""

    customer_id = digits(settings["customer_id"])
    try:
        client = build_client(settings)
        account = fetch_account(client, customer_id)
    except ApiAccessError:
        raise
    except Exception as problem:  # credentials, network, key file
        raise ApiAccessError(explain(problem, settings)) from problem

    log(f"  Connected to {account['name'] or 'account'} ({customer_id}), currency {account['currency']}.")
    start_s, end_s = start.isoformat(), end.isoformat()
    reports, report_info = {}, {}
    for report in schema.REPORTS:
        log(f"  Downloading {schema.TITLES[report]} ...")
        try:
            rows, info = fetch_report(client, customer_id, report, start_s, end_s, log)
        except ApiAccessError:
            raise
        except Exception as problem:
            raise ApiAccessError(explain(problem, settings)) from problem
        if report == "locations" and rows:
            resolve_geo(client, customer_id, rows, log)
        for row in rows:
            row["currency"] = account["currency"]
        reports[report] = rows
        report_info[report] = info
        status = f"{len(rows)} rows" if info["status"] == "ok" else "FAILED"
        log(f"    {status}")

    meta = {"account": account, "reports": report_info}
    return reports, meta


def check(settings, start, end, log=print):
    """Confirm access and have Google validate every query without running it."""

    from google.ads.googleads.errors import GoogleAdsException

    customer_id = digits(settings["customer_id"])
    try:
        client = build_client(settings)
        account = fetch_account(client, customer_id)
    except ApiAccessError:
        raise
    except Exception as problem:
        raise ApiAccessError(explain(problem, settings)) from problem

    results = []
    for report in schema.REPORTS:
        variants = queries.REPORT_QUERIES[report].variants
        for index in range(len(variants)):
            query = queries.build_query(report, start.isoformat(), end.isoformat(), index)
            try:
                validate(client, customer_id, query)
            except GoogleAdsException as problem:
                if is_fatal(problem):
                    raise ApiAccessError(explain_google_ads(problem, customer_id)) from problem
                if index + 1 < len(variants):
                    continue
                results.append((report, index, False, explain_google_ads(problem, customer_id)))
                break
            results.append((report, index, True, ""))
            break
    return account, results


def redirect_uri(port=REDIRECT_PORT):
    return f"http://{REDIRECT_HOST}:{port}"


def port_in_use(port, host=REDIRECT_HOST):
    """True when another program already listens on host:port.

    Connects first: Windows lets a second server bind a port that another
    one listens on, and the browser then lands on the wrong program.
    Refused (nobody listening) takes about 2 seconds on Windows.
    """

    import socket

    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((host, port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def free_port_after(port, tries=30):
    return next((p for p in range(port + 1, port + 1 + tries) if not port_in_use(p)), None)


def client_page(client_id):
    """Cloud console page of this OAuth client. Its ID starts with the owning project's number."""

    number = re.match(r"(\d+)-", client_id or "")
    return f"https://console.cloud.google.com/auth/clients/{client_id}" + (f"?project={number.group(1)}" if number else "")


def redirect_problem(client_id, uri, session=None):
    """Why Google would refuse this sign-in before anyone signs in, or None.

    Google checks the client ID and return address before it shows a sign-in
    page, so asking needs no password and changes nothing. Anything
    unexpected (no network, a new error format) gives None and the normal
    sign-in goes ahead.
    """

    try:
        import requests

        query = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": uri, "response_type": "code", "scope": OAUTH_SCOPE})
        response = (session or requests.Session()).get(f"{AUTH_URI}?{query}", allow_redirects=False, timeout=20)
        location = response.headers.get("Location", "")
        if "/signin/oauth/error" not in location:
            return None
        blob = urllib.parse.parse_qs(urllib.parse.urlparse(location).query).get("authError", [""])[0]
        detail = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
    except Exception:
        return None
    for reason in ("redirect_uri_mismatch", "deleted_client", "invalid_client", "disabled_client"):
        if reason.encode() in detail:
            return reason
    return None


def generate_refresh_token(client_id, client_secret, port=REDIRECT_PORT):
    """Open the browser for the one-time OAuth consent; return (refresh token, granted scopes).

    The person signs in themselves (password, MFA, any security prompts);
    this only receives the token Google hands back on localhost. Google lets
    them untick a permission; oauthlib would then raise "Scope has changed",
    so it is told to accept that and the caller checks what was granted.
    """

    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    import wsgiref.simple_server

    from google_auth_oauthlib.flow import InstalledAppFlow

    # Never share the port with another program (SO_REUSEADDR allows that on Windows).
    wsgiref.simple_server.WSGIServer.allow_reuse_address = False

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[OAUTH_SCOPE, DATAMANAGER_SCOPE],
    )
    credentials = flow.run_local_server(
        host=REDIRECT_HOST,
        port=port,
        redirect_uri_trailing_slash=False,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Opening your browser to sign in to Google...\nIf it does not open, visit:\n{url}",
        success_message="Signed in. You can close this tab and return to the terminal.",
    )
    if not credentials.refresh_token:
        raise ApiAccessError("Google did not return a refresh token. Run the command again.")
    granted = credentials.granted_scopes
    if isinstance(granted, str):
        granted = granted.split()
    return credentials.refresh_token, set(granted or (OAUTH_SCOPE, DATAMANAGER_SCOPE))
