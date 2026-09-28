"""The browser fallback, driven against a local mock of the Google Ads website.

These prove the mechanics: waiting for a person to sign in, carrying the
account through the URL, setting the date range, segmenting, capturing the
download and verifying the file's own date-range line. They cannot prove the
real website's buttons are still named the same; the first real run should
be watched.
"""

import os
import shutil

import pytest

from conftest import END, START, TODAY
from mock_ads_ui import MockAds
from ppc_exporter import browser_source, master, schema, settings as config

pytest.importorskip("playwright.sync_api")


def chrome_path():
    for candidate in (os.environ.get("PPC_TEST_CHROME"), "/opt/pw-browsers/chromium"):
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


@pytest.fixture
def browser_settings(tmp_path):
    settings = config.load(tmp_path / "none.yaml", environ={})
    settings["customer_id"] = "123-456-7890"
    settings["browser"]["profile_dir"] = str(tmp_path / "profile")
    settings["browser"]["chrome_path"] = chrome_path()
    settings["browser"]["login_timeout_minutes"] = 1
    return settings


def run_export(settings, server, raw_dir, **kwargs):
    lines = []
    try:
        reports, meta = browser_source.export(
            settings, START, END, TODAY, raw_dir, base_url=server.base, headless=True, interactive=False,
            log=lines.append, timeouts={"page_timeout_ms": 1500, "control_timeout_ms": 1000, "settle_ms": 150}, **kwargs,
        )
    except browser_source.BrowserError as problem:
        if "Could not start a browser" in str(problem):
            pytest.skip("no Chromium available: " + str(problem))
        raise
    return reports, meta, lines


def test_full_browser_export_against_mock(browser_settings, tmp_path):
    server = MockAds(TODAY).start()
    try:
        reports, meta, lines = run_export(browser_settings, server, tmp_path / "raw")
    finally:
        server.shutdown()

    assert "  Signed in." in lines and "  Account 123-456-7890 is open." in lines
    for report in schema.REPORTS:
        info = meta["reports"][report]
        assert info["status"] == "ok", (report, info)
        assert info["date_range_ok"], (report, info)
        assert reports[report], report
        assert (tmp_path / "raw" / f"{report}.csv").exists()

    # The account query string from sign-in is carried to every report page.
    report_pages = [p for p in server.requests if p.startswith("/aw/") and not p.startswith("/aw/overview")]
    assert report_pages and all("ocid=111" in p and "__c=444" in p for p in report_pages)

    campaigns = reports["campaigns"]
    assert [r["date"] for r in campaigns] == ["2026-08-29", "2026-08-30"]  # unsplit total row dropped
    assert sum(r["cost"] for r in campaigns) == pytest.approx(1200.0)
    assert {r["keyword"]: r["match_type"] for r in reports["keywords"]} == {"sell my house fast": "EXACT", "we buy houses": "PHRASE"}
    term = reports["search_terms"][0]
    assert term["search_term_match_type"] == "NEAR_PHRASE" and term["keyword"] == "sell my house fast"
    assert {r["city"] for r in reports["locations"]} == {"Oakland", "Hayward"}
    assert [r["conversion_action"] for r in reports["conversions"]] == ["Calls from ads", "Website lead form"]
    assert meta["warnings"] == []

    manifest = master.write_bundle(str(tmp_path / "out"), reports, start=START, end=END, source="browser",
                                   meta=meta, log=lambda *_: None)
    assert manifest["totals"]["keywords_cost"] == pytest.approx(1200.0)
    assert manifest["totals"]["keyword_city_spend"] == pytest.approx(1200.0)


def test_changed_website_degrades_to_asking_a_person(browser_settings, tmp_path):
    """If Google renames the Download button, nothing crashes: each report is
    marked as needing a person, and in a real (interactive) run the terminal
    asks them to click it."""

    server = MockAds(TODAY, download_label="Export table").start()
    try:
        reports, meta, lines = run_export(browser_settings, server, tmp_path / "raw")
    finally:
        server.shutdown()
    assert all(meta["reports"][r]["status"] == "failed" for r in schema.REPORTS)
    assert all(meta["reports"][r]["summary"] == "no download" for r in schema.REPORTS)
    assert any("needs a person: Click the Download icon" in line for line in lines)


def test_download_clicked_by_a_person_is_captured(browser_settings, tmp_path):
    from playwright.sync_api import sync_playwright

    server = MockAds(TODAY).start()
    try:
        with sync_playwright() as playwright:
            try:
                context = browser_source._launch(playwright, browser_settings, True, lambda *_: None)
            except browser_source.BrowserError as problem:
                pytest.skip(str(problem))
            page = context.pages[0] if context.pages else context.new_page()
            session = browser_source.Session(context, page, server.base, True, lambda *_: None)
            page.goto(server.base + "/signin")
            page.wait_for_url("**/aw/overview**")
            page.goto(server.base + "/aw/campaigns?ocid=111")
            # Stand-in for a person clicking Download > .csv while the script waits.
            page.evaluate("setTimeout(() => { document.getElementById('dl').click(); document.getElementById('csv').click(); }, 800)")
            download = session.wait_for_download("click Download > .csv", timeout_s=20)
            assert download is not None
            target = tmp_path / "captured.csv"
            download.save_as(str(target))
            context.close()
    finally:
        server.shutdown()
    assert target.read_bytes().decode("utf-8-sig").startswith("Campaign report")


def test_sign_in_detection():
    assert browser_source.is_signed_in("https://ads.google.com/aw/overview?ocid=1")
    assert not browser_source.is_signed_in("https://accounts.google.com/ServiceLogin?service=adwords")
    assert not browser_source.is_signed_in("https://ads.google.com/nav/selectaccount")
    assert not browser_source.is_signed_in("https://ads.google.com.evil.example/aw/overview")
    assert browser_source.account_query("https://ads.google.com/aw/overview?ocid=1&subid=x&__c=2&authuser=0") == "ocid=1&__c=2&authuser=0"


def test_preset_names():
    assert browser_source.preset_name(START, END, TODAY) == "Last 30 days"
    assert browser_source.preset_name(START, END, END) is None
    assert browser_source.human(START) == "Aug 29, 2026"


def test_chrome_lookup_honours_config(browser_settings):
    browser_settings["browser"]["chrome_path"] = "/opt/custom/chrome"
    assert browser_source.find_chrome(browser_settings) == "/opt/custom/chrome"
    browser_settings["browser"]["chrome_path"] = ""
    found = browser_source.find_chrome(browser_settings)
    assert found == "" or os.path.exists(found) or shutil.which(found)
