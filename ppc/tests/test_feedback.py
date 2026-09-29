"""Sending lead outcomes back to Google through the Data Manager API.

No network: a fake HTTP session records what would be posted, so the
request shape, the validate-only default and the error explanations are
all checked exactly as they would go out.
"""

import datetime
import os
import subprocess
import sys
import zoneinfo

import pytest

from ppc_exporter import feedback, settings as config

LA = zoneinfo.ZoneInfo("America/Los_Angeles")
NOW = datetime.datetime(2026, 9, 29, 10, 0, tzinfo=LA)


def lead(**fields):
    base = {"lead_id": "L-1", "lead_date": "2026-09-10", "gclid": "", "gbraid": "", "wbraid": "", "email": "", "phone": "",
            "qualified_lead": 0, "appointment": 0, "offer": 0, "contract": 0, "closed_deal": 0,
            "not_qualified_reason": "", "profit": None}
    base.update(fields)
    return base


def test_identifiers_are_normalised_then_hashed():
    assert feedback.normalize_email("  Test@Example.COM ") == "test@example.com"
    assert feedback.sha256("test@example.com") == "973dfe463ec85785f5f95af5ba3906eedb2d931c24e69824a89ea65dba4e813b"
    assert feedback.normalize_email("not-an-email") is None
    assert feedback.normalize_phone("(510) 555-1234") == "+15105551234"
    assert feedback.normalize_phone("1-510-555-1234") == "+15105551234"
    assert feedback.normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert feedback.normalize_phone("555-1234") is None


def test_each_status_becomes_one_event_on_its_action():
    events, skipped = feedback.build_events(
        [lead(gclid="TEST-GCLID-abc", qualified_lead=1, appointment=1, closed_deal=1, profit=31500.0)], NOW, LA)
    assert skipped == []
    assert set(events) == {"offline_qualified_lead", "offline_appointment_set", "offline_closed_deal"}
    qualified = events["offline_qualified_lead"][0]
    assert qualified["adIdentifiers"] == {"gclid": "TEST-GCLID-abc"}
    assert qualified["transactionId"] == "L-1-offline_qualified_lead"
    assert qualified["eventTimestamp"] == "2026-09-10T23:59:59-07:00"
    assert qualified["eventSource"] == "WEB" and "conversionValue" not in qualified
    closed = events["offline_closed_deal"][0]
    assert closed["conversionValue"] == 31500.0 and closed["currency"] == "USD"


def test_contact_details_are_sent_hashed_never_raw():
    events, _ = feedback.build_events([lead(email="Seller@Gmail.com", phone="510-555-1234", qualified_lead=1)], NOW, LA)
    event = events["offline_qualified_lead"][0]
    ids = event["userData"]["userIdentifiers"]
    assert {"emailAddress": feedback.sha256("seller@gmail.com")} in ids
    assert {"phoneNumber": feedback.sha256("+15105551234")} in ids
    assert "Seller@Gmail.com" not in repr(event) and "555-1234" not in repr(event)
    assert event["eventSource"] == "OTHER"  # no click ID: matched by contact details only
    assert feedback.request_body({"d": 1}, [event], True)["encoding"] == "HEX"


def test_reasons_map_to_the_disqualification_actions():
    events, skipped = feedback.build_events([
        lead(lead_id="A", gclid="g1", not_qualified_reason="Outside buy area"),
        lead(lead_id="B", gclid="g2", not_qualified_reason="Fraud/Spam"),
        lead(lead_id="C", gclid="g3", not_qualified_reason="Price shopping"),
        lead(lead_id="D", gclid="g4", not_qualified_reason="Moon landing"),
    ], NOW, LA)
    assert [e["transactionId"] for e in events["offline_poor_location"]] == ["A-offline_poor_location"]
    assert [e["transactionId"] for e in events["offline_fraud"]] == ["B-offline_fraud"]
    assert [e["transactionId"] for e in events["offline_retail"]] == ["C-offline_retail"]
    assert ("D", "unknown not_qualified_reason 'Moon landing'") in skipped


def test_leads_google_cannot_use_are_skipped_with_a_reason():
    _, skipped = feedback.build_events([
        lead(lead_id="none", qualified_lead=1),
        lead(lead_id="old", gclid="g", lead_date="2026-05-01", qualified_lead=1),
        lead(lead_id="nodate", gclid="g", lead_date="", qualified_lead=1),
        lead(lead_id="nostatus", gclid="g"),
    ], NOW, LA)
    reasons = dict(skipped)
    assert "no gclid" in reasons["none"]
    assert "older than 90 days" in reasons["old"]
    assert reasons["nodate"] == "no lead_date"
    assert reasons["nostatus"] == "no status to send yet"


def test_a_lead_from_today_is_stamped_in_the_past():
    events, _ = feedback.build_events([lead(gclid="g", lead_date="2026-09-29", qualified_lead=1)], NOW, LA)
    assert events["offline_qualified_lead"][0]["eventTimestamp"] == "2026-09-29T09:59:00-07:00"


def test_transaction_ids_are_stable_so_resending_never_double_counts():
    rows = [lead(lead_id="", gclid="g", email="a@b.co", qualified_lead=1)]
    first, _ = feedback.build_events(rows, NOW, LA)
    second, _ = feedback.build_events(rows, NOW + datetime.timedelta(days=3), LA)
    assert first["offline_qualified_lead"][0]["transactionId"] == second["offline_qualified_lead"][0]["transactionId"]


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, status=200, payload=None):
        self.calls, self.status, self.payload = [], status, payload or {"requestId": "req-1"}

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers))
        return FakeResponse(self.status, self.payload)


@pytest.fixture
def outcomes(tmp_path):
    path = tmp_path / "lead_outcomes.csv"
    path.write_text(
        "lead_date,lead_id,gclid,email,qualified_lead,appointment,closed_deal,not_qualified_reason,profit\n"
        "2026-09-15,EXAMPLE-1,x,,yes,,,,\n"
        "2026-09-10,L-1,TEST-GCLID-abc,,yes,yes,,,\n"
        "2026-09-12,L-2,,seller@example.com,,,,Outside buy area,\n"
        "2026-09-14,L-3,TEST-GCLID-def,,yes,,yes,,\"$20,000\"\n"
    )
    return path


@pytest.fixture
def api_settings(tmp_path):
    loaded = config.load(tmp_path / "none.yaml", environ={})
    loaded["customer_id"] = "989-715-5298"
    loaded["api"].update(client_id="id", client_secret="secret", refresh_token="token")
    return loaded


def fake_actions(monkeypatch, missing=(), owner="9897155298", asked=None):
    names = {"offline_qualified_lead": 11, "offline_appointment_set": 12, "offline_poor_location": 13, "offline_closed_deal": 14,
             "THB - Qualified lead": 21}
    table = {n: (i, "UPLOAD_CLICKS", owner) for n, i in names.items() if n not in missing}

    def lookup(client, cid, wanted):
        if asked is not None:
            asked.update(wanted)
        return {n: v for n, v in table.items() if n in wanted}

    monkeypatch.setattr(feedback, "conversion_actions", lookup)


def test_run_validates_by_default_one_request_per_action(monkeypatch, outcomes, api_settings):
    fake_actions(monkeypatch)
    session, lines = FakeSession(), []
    code = feedback.run(api_settings, outcomes, now=NOW, client=object(), session=session, token="tok", log=lines.append)
    assert code == 0
    assert all(body["validateOnly"] is True for _, body, _ in session.calls)
    by_action = {body["destinations"][0]["productDestinationId"]: body for _, body, _ in session.calls}
    assert set(by_action) == {"11", "12", "13", "14"}
    dest = by_action["11"]["destinations"][0]
    assert dest["operatingAccount"] == {"accountType": "GOOGLE_ADS", "accountId": "9897155298"}
    assert dest["loginAccount"]["accountId"] == "9897155298"
    assert len(by_action["11"]["events"]) == 2  # L-1 and L-3
    assert by_action["14"]["events"][0]["conversionValue"] == 20000.0
    assert session.calls[0][0] == feedback.ENDPOINT and session.calls[0][2]["Authorization"] == "Bearer tok"
    assert any("run the same command with --send" in line for line in lines)


def test_send_flag_records_for_real(monkeypatch, outcomes, api_settings):
    fake_actions(monkeypatch)
    session = FakeSession()
    feedback.run(api_settings, outcomes, send_for_real=True, now=NOW, client=object(), session=session, token="t", log=lambda *_: None)
    assert session.calls and all(body["validateOnly"] is False for _, body, _ in session.calls)


def test_missing_conversion_action_is_reported(monkeypatch, outcomes, api_settings):
    fake_actions(monkeypatch, missing=("offline_closed_deal",))
    lines = []
    code = feedback.run(api_settings, outcomes, now=NOW, client=object(), session=FakeSession(), token="t", log=lines.append)
    assert code == 1
    assert any("offline_closed_deal: not in the Google Ads account" in line for line in lines)


def test_missing_upload_permission_says_how_to_fix(monkeypatch, outcomes, api_settings):
    fake_actions(monkeypatch)
    denied = {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Request had insufficient authentication scopes.",
                        "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
    lines = []
    code = feedback.run(api_settings, outcomes, now=NOW, client=object(), session=FakeSession(403, denied), token="t", log=lines.append)
    assert code == 3
    assert any("python ppc/export.py refresh-token" in line for line in lines)


def test_api_switched_off_says_where_to_turn_it_on():
    message = feedback.explain_http(403, {"error": {"message": "Data Manager API has not been used in project 1 before or it is disabled.",
                                                    "details": [{"reason": "SERVICE_DISABLED"}]}})
    assert feedback.ENABLE_API + "?project=1" in message and "(project 1)" in message


def test_refresh_token_is_saved_into_the_env_file(tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import export

    env = tmp_path / ".env"
    env.write_text("GOOGLE_ADS_CLIENT_ID=abc\nGOOGLE_ADS_REFRESH_TOKEN=1//old\nGOOGLE_ADS_CUSTOMER_ID=9897155298\n")
    settings = config.load(tmp_path / "config.yaml", environ={})
    assert export.save_refresh_token(settings, "1//new-token") == str(env)
    assert env.read_text() == "GOOGLE_ADS_CLIENT_ID=abc\nGOOGLE_ADS_REFRESH_TOKEN=1//new-token\nGOOGLE_ADS_CUSTOMER_ID=9897155298\n"

    env.unlink()
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text('api:\n  refresh_token: "old"\n')
    settings = config.load(yaml_path, environ={})
    assert export.save_refresh_token(settings, "1//new") == str(yaml_path)
    assert 'refresh_token: "1//new"' in yaml_path.read_text()


@pytest.mark.parametrize("granted, code, saved, says", [
    ({"https://www.googleapis.com/auth/adwords", "https://www.googleapis.com/auth/datamanager"}, 0, True, "Both permissions allowed"),
    ({"https://www.googleapis.com/auth/adwords"}, 1, True, "Data Manager box was not ticked"),
    ({"https://www.googleapis.com/auth/datamanager"}, 2, False, "Google Ads permission was not ticked"),
])
def test_refresh_token_reports_an_unticked_permission(tmp_path, monkeypatch, capsys, granted, code, saved, says):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import export

    env = tmp_path / ".env"
    env.write_text("GOOGLE_ADS_CLIENT_ID=abc\nGOOGLE_ADS_CLIENT_SECRET=s\nGOOGLE_ADS_REFRESH_TOKEN=1//old\n")
    monkeypatch.setattr(export.api_source, "port_in_use", lambda *_: False)
    monkeypatch.setattr(export.api_source, "redirect_problem", lambda *_: None)
    monkeypatch.setattr(export.api_source, "generate_refresh_token", lambda *_a, **_k: ("1//new", granted))
    for name in [k for k in os.environ if k.startswith("GOOGLE_ADS_")]:
        monkeypatch.delenv(name)
    assert export.main(["refresh-token", "--config", str(tmp_path / "config.yaml")]) == code
    assert says in capsys.readouterr().out
    assert ("1//new" in env.read_text()) is saved


def _sign_in(monkeypatch, answer_path):
    """Run generate_refresh_token on a free port; play the browser: /start, a favicon, then Google's answer."""

    import http.client
    import socket
    import threading
    import time
    import types
    import urllib.parse

    import google_auth_oauthlib.flow as flow_module
    from ppc_exporter import api_source

    seen = {}

    class FakeFlow:
        @classmethod
        def from_client_config(cls, config_, scopes):
            seen["scopes"] = scopes
            return cls()

        def authorization_url(self, **kw):
            assert os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE") == "1"
            seen["auth_kw"] = kw
            return "https://accounts.google.com/o/oauth2/auth?redirect_uri=" + urllib.parse.quote(self.redirect_uri, safe=""), "st"

        def fetch_token(self, authorization_response):
            seen["response"] = authorization_response
            self.credentials = types.SimpleNamespace(refresh_token="1//x", granted_scopes=["https://www.googleapis.com/auth/adwords"])

    monkeypatch.delenv("OAUTHLIB_RELAX_TOKEN_SCOPE", raising=False)
    monkeypatch.setattr(flow_module, "InstalledAppFlow", FakeFlow)
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    out, lines, opened = {}, [], []

    def run():
        try:
            out["result"] = api_source.generate_refresh_token("id", "secret", port=port, say=lines.append,
                                                              open_link=lambda url: opened.append(url) or "Chrome")
        except Exception as problem:  # handed to the test thread
            out["error"] = problem

    worker = threading.Thread(target=run)
    worker.start()

    def get(path):
        for _ in range(100):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("GET", path)
                response = conn.getresponse()
                return response.status, response.getheader("Location"), response.read().decode()
            except (ConnectionRefusedError, ConnectionResetError):
                time.sleep(0.05)
        raise AssertionError("local sign-in server never answered")

    replies = [get("/start"), get("/favicon.ico"), get(answer_path)]
    worker.join(15)
    assert not worker.is_alive()
    assert opened == [f"http://127.0.0.1:{port}/start"]
    return port, seen, out, lines, replies


def test_sign_in_uses_a_short_start_link_then_takes_googles_answer(monkeypatch):
    """Google's own link is ~450 characters and broke when copied out of cmd ("400. That's an error")."""

    port, seen, out, lines, (start, favicon, answer) = _sign_in(monkeypatch, "/?state=st&code=4%2Fabc&scope=x")
    assert start[0] == 302 and start[1].startswith("https://accounts.google.com/")
    assert f"redirect_uri=http%3A%2F%2F127.0.0.1%3A{port}" in start[1]
    assert favicon[0] == 404  # a stray request does not end the wait
    assert answer[0] == 200 and "Signed in" in answer[2]
    assert out["result"] == ("1//x", {"https://www.googleapis.com/auth/adwords"})
    assert seen["auth_kw"] == {"access_type": "offline", "prompt": "consent"}
    assert seen["response"] == f"https://127.0.0.1:{port}/?state=st&code=4%2Fabc&scope=x"
    assert any(line.strip() == f"http://127.0.0.1:{port}/start" for line in lines)
    assert any(line.startswith("Opened the sign-in in Chrome") for line in lines)
    assert not any("Ctrl+C" in line for line in lines)  # pressing it to copy the link stopped the sign-in


def test_sign_in_opens_chrome_where_the_google_account_is(monkeypatch, tmp_path):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import subprocess as sp
    import webbrowser

    import export
    from ppc_exporter import browser_source

    started, defaulted = [], []
    monkeypatch.setattr(sp, "Popen", lambda args, **_k: started.append(args))
    monkeypatch.setattr(webbrowser, "open", lambda url, new=0: defaulted.append(url) or True)
    settings = config.load(tmp_path / "none.yaml", environ={})

    monkeypatch.setattr(browser_source, "find_chrome", lambda _s: r"C:\Chrome\chrome.exe")
    assert export.open_sign_in("http://127.0.0.1:8723/start", settings) == "Chrome"
    assert started == [[r"C:\Chrome\chrome.exe", "http://127.0.0.1:8723/start"]] and defaulted == []

    monkeypatch.setattr(browser_source, "find_chrome", lambda _s: "")
    assert export.open_sign_in("http://127.0.0.1:8723/start", settings) == "your default browser"
    assert defaulted == ["http://127.0.0.1:8723/start"]


def test_ctrl_c_during_sign_in_says_how_to_redo_it(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import export

    (tmp_path / ".env").write_text("GOOGLE_ADS_CLIENT_ID=4242-abc\nGOOGLE_ADS_CLIENT_SECRET=s\n")
    for name in [k for k in os.environ if k.startswith("GOOGLE_ADS_")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(export.api_source, "port_in_use", lambda *_: False)
    monkeypatch.setattr(export.api_source, "redirect_problem", lambda *_: None)

    def interrupted(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr(export.api_source, "generate_refresh_token", interrupted)
    assert export.main(["refresh-token", "--config", str(tmp_path / "config.yaml")]) == export.EXIT_ERROR
    assert "leave this" in capsys.readouterr().out


def test_sign_in_refused_in_the_browser_says_so(monkeypatch):
    _port, _seen, out, _lines, (_start, _favicon, answer) = _sign_in(monkeypatch, "/?error=access_denied&state=st")
    assert answer[0] == 200 and "did not finish" in answer[2]
    assert "access_denied" in str(out["error"]) and "result" not in out


class FakeAuthSession:
    """Google's authorization endpoint: a 302 to a sign-in page, or to an error page."""

    def __init__(self, location):
        self.location, self.urls = location, []

    def get(self, url, allow_redirects, timeout):
        import types

        self.urls.append(url)
        return types.SimpleNamespace(status_code=302, headers={"Location": self.location})


def google_error_page(reason):
    import base64

    blob = base64.urlsafe_b64encode(b"\x08\x01\x12\x15" + reason.encode() + b"\x1a\x10You can't sign in").decode().rstrip("=")
    return f"https://accounts.google.com/signin/oauth/error?authError={blob}&client_id=1-x"


def test_redirect_problem_reads_googles_answer():
    from ppc_exporter import api_source

    session = FakeAuthSession(google_error_page("redirect_uri_mismatch"))
    assert api_source.redirect_problem("123-abc.apps.googleusercontent.com", "http://127.0.0.1:8723", session) == "redirect_uri_mismatch"
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8723" in session.urls[0]
    fine = FakeAuthSession("https://accounts.google.com/v3/signin/identifier?x=1")
    assert api_source.redirect_problem("123-abc", "http://127.0.0.1:8723", fine) is None
    assert api_source.redirect_problem("123-abc", "http://127.0.0.1:8723", FakeAuthSession(google_error_page("something_new"))) is None

    class Offline:
        def get(self, *_a, **_k):
            raise OSError("no network")

    assert api_source.redirect_problem("123-abc", "http://127.0.0.1:8723", Offline()) is None
    assert api_source.client_page("9876-abc.apps.googleusercontent.com") == \
        "https://console.cloud.google.com/auth/clients/9876-abc.apps.googleusercontent.com?project=9876"


def test_refresh_token_explains_an_unregistered_return_address(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import export

    (tmp_path / ".env").write_text("GOOGLE_ADS_CLIENT_ID=4242-abc.apps.googleusercontent.com\nGOOGLE_ADS_CLIENT_SECRET=s\n")
    for name in [k for k in os.environ if k.startswith("GOOGLE_ADS_")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(export.api_source, "port_in_use", lambda *_: False)
    monkeypatch.setattr(export.api_source, "redirect_problem", lambda *_: "redirect_uri_mismatch")
    monkeypatch.setattr(export.api_source, "generate_refresh_token", lambda *_a, **_k: pytest.fail("browser must not open"))
    assert export.main(["refresh-token", "--config", str(tmp_path / "config.yaml")]) == export.EXIT_SETUP
    out = capsys.readouterr().out
    assert "'Authorized redirect URIs' box" in out and "       http://127.0.0.1:8723\n" in out
    assert "auth/clients/4242-abc.apps.googleusercontent.com?project=4242" in out


def test_refresh_token_never_uses_a_port_another_program_listens_on(tmp_path, monkeypatch, capsys):
    """The office PC runs the Call Coach on 8080; the browser must not land there."""

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import export

    (tmp_path / ".env").write_text("GOOGLE_ADS_CLIENT_ID=4242-abc\nGOOGLE_ADS_CLIENT_SECRET=s\n")
    for name in [k for k in os.environ if k.startswith("GOOGLE_ADS_")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(export.api_source, "port_in_use", lambda port, *_: port == 8723)
    monkeypatch.setattr(export.api_source, "redirect_problem", lambda *_: pytest.fail("checked before the port"))
    monkeypatch.setattr(export.api_source, "generate_refresh_token", lambda *_a, **_k: pytest.fail("browser must not open"))
    assert export.main(["refresh-token", "--config", str(tmp_path / "config.yaml")]) == export.EXIT_SETUP
    out = capsys.readouterr().out
    assert "Port 8723" in out and "refresh-token --port 8724" in out

    def cannot_open(*_a, **_k):
        raise OSError(10013, "An attempt was made to access a socket in a way forbidden by its access permissions")

    monkeypatch.setattr(export.api_source, "port_in_use", lambda *_: False)
    monkeypatch.setattr(export.api_source, "free_port_after", lambda port: port + 3)
    monkeypatch.setattr(export.api_source, "redirect_problem", lambda *_: None)
    monkeypatch.setattr(export.api_source, "generate_refresh_token", cannot_open)
    assert export.main(["refresh-token", "--config", str(tmp_path / "config.yaml")]) == export.EXIT_SETUP
    assert "refresh-token --port 8726" in capsys.readouterr().out


def test_port_in_use_sees_a_listening_program():
    import socket

    from ppc_exporter import api_source

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert api_source.port_in_use(port) is True
    finally:
        server.close()
    assert api_source.port_in_use(port) is False


def test_upload_command_without_credentials_says_what_is_missing(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_ADS_")}
    result = subprocess.run([sys.executable, os.path.join(here, "export.py"), "upload", "--config", str(tmp_path / "none.yaml")],
                            capture_output=True, text=True, env=clean, timeout=60)
    assert result.returncode == 2 and "customer_id" in result.stdout


def test_self_test_uses_a_real_recent_click_and_only_validates(monkeypatch, api_settings):
    import types

    today = datetime.date(2026, 9, 29)
    seen = []

    def fake_stream(client, cid, query):
        seen.append(query)
        if "2026-09-27" in query:
            return [types.SimpleNamespace(click_view=types.SimpleNamespace(gclid="TEST-GCLID-recent"))]
        return []

    import ppc_exporter.api_source as api
    monkeypatch.setattr(api, "stream", fake_stream)
    lead_row = feedback.self_test_lead(object(), "9897155298", today)
    assert lead_row["gclid"] == "TEST-GCLID-recent" and lead_row["lead_date"] == "2026-09-27" and lead_row["qualified_lead"] == 1
    assert "2026-09-28" in seen[0]  # yesterday is tried first

    fake_actions(monkeypatch)
    session = FakeSession()
    code = feedback.run(api_settings, leads=[lead_row], now=NOW, client=object(), session=session, token="t", log=lambda *_: None)
    assert code == 0 and len(session.calls) == 1
    assert session.calls[0][1]["validateOnly"] is True


def test_test_and_send_together_are_refused(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_ADS_")}
    env.update(GOOGLE_ADS_CUSTOMER_ID="9897155298", GOOGLE_ADS_CLIENT_ID="id", GOOGLE_ADS_CLIENT_SECRET="s", GOOGLE_ADS_REFRESH_TOKEN="t")
    result = subprocess.run([sys.executable, os.path.join(here, "export.py"), "upload", "--test", "--send", "--config", str(tmp_path / "none.yaml")],
                            capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 2 and "never records" in result.stdout


# ------------------------------------------------ Google's processing report --


def status_payload(status, errors=(), warnings=()):
    item = {"requestStatus": status}
    if errors:
        item["errorInfo"] = {"errorCounts": [{"recordCount": str(n), "reason": "PROCESSING_ERROR_REASON_" + r} for r, n in errors]}
    if warnings:
        item["warningInfo"] = {"warningCounts": [{"recordCount": str(n), "reason": "PROCESSING_WARNING_REASON_" + r} for r, n in warnings]}
    return {"requestStatusPerDestination": [item]}


def test_processing_report_in_plain_words():
    assert feedback.summarize_status(status_payload("SUCCESS")) == ("SUCCESS", 0, "")
    status, problems, details = feedback.summarize_status(
        status_payload("PARTIAL_SUCCESS", errors=[("CLICK_NOT_FOUND", 2), ("DUPLICATE_TRANSACTION_ID", 5)]))
    assert (status, problems) == ("PARTIAL_SUCCESS", 2)
    assert "2 not recorded: Google can't find the click" in details
    assert "5 not recorded: already sent before, not counted twice" in details
    assert feedback.summarize_status(status_payload("FAILED", errors=[("SOMETHING_NEW", 1)]))[2] == "1 not recorded: something new"
    assert feedback.summarize_status({})[0] == "REQUEST_STATUS_UNKNOWN"


class FakeStatusSession(FakeSession):
    def __init__(self, reports, status=200):
        super().__init__()
        self.reports, self.get_status, self.gets = reports, status, []

    def get(self, url, params, headers, timeout):
        self.gets.append(params["requestId"])
        return FakeResponse(self.get_status, self.reports.get(params["requestId"], {}))


def test_sends_are_logged_then_results_are_read_back(monkeypatch, outcomes, api_settings, tmp_path):
    fake_actions(monkeypatch)
    log_path = str(tmp_path / "upload_log.csv")

    feedback.run(api_settings, outcomes, now=NOW, client=object(), session=FakeSession(), token="t",
                 upload_log=log_path, log=lambda *_: None)
    assert not os.path.exists(log_path)  # validating never logs

    lines = []
    code = feedback.run(api_settings, outcomes, send_for_real=True, now=NOW, client=object(),
                        session=FakeSession(payload={"requestId": "req-9"}), token="t", upload_log=log_path, log=lines.append)
    assert code == 0 and any("upload --results" in line for line in lines)
    logged = feedback.read_log(log_path)
    assert len(logged) == 4 and {row["request_id"] for row in logged} == {"req-9"}
    assert {row["action"] for row in logged} == {"offline_qualified_lead", "offline_appointment_set", "offline_poor_location",
                                                  "offline_closed_deal"}

    session = FakeStatusSession({"req-9": status_payload("PROCESSING")})
    lines = []
    assert feedback.results(api_settings, log_path, now=NOW, session=session, token="t", log=lines.append) == 0
    assert len(session.gets) == 4 and any("still processing" in line for line in lines)

    session = FakeStatusSession({"req-9": status_payload("PARTIAL_SUCCESS", errors=[("TOO_RECENT_CLICK", 1)])})
    lines = []
    assert feedback.results(api_settings, log_path, now=NOW, session=session, token="t", log=lines.append) == 1
    assert any("some recorded" in line and "under 6 hours ago" in line for line in lines)

    session = FakeStatusSession({})
    feedback.results(api_settings, log_path, now=NOW, session=session, token="t", log=lambda *_: None)
    assert session.gets == []  # finished requests are not asked about again


def test_results_before_any_send_and_with_old_sign_in(api_settings, tmp_path):
    lines = []
    assert feedback.results(api_settings, str(tmp_path / "none.csv"), log=lines.append) == 2
    assert "Nothing sent yet" in lines[0]

    log_path = str(tmp_path / "upload_log.csv")
    feedback.write_log(log_path, [dict(dict.fromkeys(feedback.LOG_COLUMNS, ""), sent_at="2026-09-29T10:00:00-07:00",
                                       action="offline_qualified_lead", events="1", request_id="req-1")])
    scope = {"error": {"message": "insufficient scopes", "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
    lines = []
    code = feedback.results(api_settings, log_path, session=FakeStatusSession({"req-1": scope}, status=403), token="t", log=lines.append)
    assert code == 3 and "refresh-token" in lines[-1]


def test_results_and_send_together_are_refused(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_ADS_")}
    env.update(GOOGLE_ADS_CUSTOMER_ID="9897155298", GOOGLE_ADS_CLIENT_ID="id", GOOGLE_ADS_CLIENT_SECRET="s", GOOGLE_ADS_REFRESH_TOKEN="t")
    result = subprocess.run([sys.executable, os.path.join(here, "export.py"), "upload", "--results", "--send", "--config",
                             str(tmp_path / "none.yaml")], capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 2 and "only reads" in result.stdout


# ------------------------------------------- actions owned by another account --


def test_actions_owned_by_a_former_manager_account_are_explained_not_sent(monkeypatch, outcomes, api_settings):
    """THB's offline_* actions belong to 119-568-5646 (Bateman era, link inactive): Google said "Resource not found"."""

    fake_actions(monkeypatch, owner="1195685646")
    session, lines = FakeSession(), []
    code = feedback.run(api_settings, outcomes, now=NOW, client=object(), session=session, token="t", log=lines.append)
    assert code == 1 and session.calls == []
    text = "\n".join(lines)
    assert "belongs to another Google Ads account (119-568-5646), not 989-715-5298" in text
    assert "'Import from clicks' conversion action named offline_qualified_lead" in text


def test_own_action_wins_over_a_managers_action_with_the_same_name(monkeypatch):
    import types

    import ppc_exporter.api_source as api

    def row(action_id, owner):
        return types.SimpleNamespace(conversion_action=types.SimpleNamespace(
            id=action_id, name="offline_qualified_lead", type_=types.SimpleNamespace(name="UPLOAD_CLICKS"),
            owner_customer=f"customers/{owner}"))

    monkeypatch.setattr(api, "stream", lambda client, cid, query: [row(950298127, 1195685646), row(555, 9897155298)])
    assert feedback.conversion_actions(object(), "9897155298", {"offline_qualified_lead"}) == \
        {"offline_qualified_lead": (555, "UPLOAD_CLICKS", "9897155298")}
    monkeypatch.setattr(api, "stream", lambda client, cid, query: [row(950298127, 1195685646)])
    assert feedback.conversion_actions(object(), "9897155298", {"offline_qualified_lead"})["offline_qualified_lead"][2] == "1195685646"


def test_actions_can_be_renamed_in_settings(monkeypatch, outcomes, api_settings):
    asked = set()
    fake_actions(monkeypatch, asked=asked)
    api_settings["feedback"]["actions"] = {"offline_qualified_lead": "THB - Qualified lead"}
    session = FakeSession()
    feedback.run(api_settings, outcomes, now=NOW, client=object(), session=session, token="t", log=lambda *_: None)
    assert "THB - Qualified lead" in asked and "offline_qualified_lead" not in asked
    sent_to = {body["destinations"][0]["productDestinationId"] for _, body, _ in session.calls}
    assert "21" in sent_to and "11" not in sent_to
