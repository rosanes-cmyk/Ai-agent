"""The fallback path: drive the Google Ads website in a real browser.

Ground rules this module never breaks:

- You sign in yourself. It never types a password, never answers 2-step
  verification, and never touches a CAPTCHA or "verify it's you" page. It
  only waits for you to finish, and gives up after a timeout.
- It never hides that the browser is automated and never works around a
  Google security prompt. If Google refuses to sign in inside the window
  this script opens, use --attach: you sign in inside a normal Chrome
  window you opened yourself, and the script connects only after you say
  you are signed in.
- Every download is captured and saved under the right name, whether the
  script clicked Download or you did.

The Google Ads website changes without notice, so every automated step has
a person-assisted fallback: when a button cannot be found, the terminal
says exactly what to click and waits. The first run should be watched.
"""

import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from . import normalize, schema

GOOGLE_ADS = "https://ads.google.com"
ACCOUNT_PARAMS = ("ocid", "euid", "__u", "uscid", "__c", "authuser")

# Where each report lives in the Google Ads website, and the segment to
# apply. Paths are tried in order; the first one that loads a table with a
# Download button wins. Saved Report Editor URLs in config.yaml override these.
PAGES = {
    "campaigns": {"paths": ["campaigns"], "segment": ("Time", "Day"),
                  "where": "Campaigns > Campaigns"},
    "ad_groups": {"paths": ["adgroups"], "segment": ("Time", "Day"),
                  "where": "Campaigns > Ad groups"},
    "keywords": {"paths": ["keywords"], "segment": ("Time", "Day"),
                 "where": "Campaigns > Audiences, keywords and content > Search keywords"},
    "search_terms": {"paths": ["searchterms", "keywords/searchterms"], "segment": ("Time", "Day"),
                     "where": "Campaigns > Insights and reports > Search terms"},
    "locations": {"paths": ["userlocations", "geographicreport", "locations/matchedlocations", "locations"],
                  "segment": ("Time", "Day"),
                  "where": "Campaigns > Insights and reports > When and where ads showed > Locations "
                           "(Matched locations, city level)"},
    "conversions": {"paths": ["campaigns"], "segment": ("Conversions", "Conversion action"),
                    "where": "Campaigns > Campaigns, then Segment > Conversions > Conversion action"},
}

DOWNLOAD_BUTTONS = [
    lambda page: page.get_by_role("button", name=re.compile(r"^\s*download", re.I)),
    lambda page: page.locator("[aria-label='Download' i]"),
    lambda page: page.locator("[data-tooltip='Download' i]"),
]
CSV_OPTIONS = [
    lambda page: page.get_by_role("menuitem", name=re.compile(r"^\s*\.csv\s*$", re.I)),
    lambda page: page.get_by_role("option", name=re.compile(r"^\s*\.csv\s*$", re.I)),
    lambda page: page.get_by_text(re.compile(r"^\s*\.csv\s*$", re.I)),
]
DATE_BUTTONS = [
    lambda page: page.locator("[aria-label*='date range' i]"),
    lambda page: page.get_by_role(
        "button",
        name=re.compile(r"(last \d+ days|this month|last month|custom|today|yesterday|all time)", re.I),
    ),
]
SEGMENT_BUTTONS = [
    lambda page: page.get_by_role("button", name=re.compile(r"^\s*segment", re.I)),
    lambda page: page.locator("[aria-label='Segment' i]"),
]
APPLY_BUTTONS = [
    lambda page: page.get_by_role("button", name=re.compile(r"^\s*apply\s*$", re.I)),
]


class BrowserError(Exception):
    pass


# ------------------------------------------------------------- utilities --


def is_signed_in(url, base=GOOGLE_ADS):
    parsed, home = urllib.parse.urlparse(url), urllib.parse.urlparse(base)
    return parsed.netloc == home.netloc and parsed.path.startswith("/aw/")


def account_query(url):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    kept = {k: v[0] for k, v in query.items() if k in ACCOUNT_PARAMS and v}
    return urllib.parse.urlencode(kept)


def page_url(base, path, query):
    return f"{base}/aw/{path}" + (f"?{query}" if query else "")


def dashed(customer_id):
    d = re.sub(r"\D", "", customer_id or "")
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d) == 10 else ""


def human(day):
    """Sep 1, 2026 - the way the Google Ads date picker writes dates."""

    return f"{day:%b} {day.day}, {day.year}"


def preset_name(start, end, today):
    """Google's own preset for this range, if there is one."""

    yesterday = today.toordinal() - 1
    span = end.toordinal() - start.toordinal() + 1
    if end.toordinal() == yesterday and span in (7, 14, 30):
        return f"Last {span} days"
    return None


def _first_visible(page, candidates, timeout_ms):
    """The first candidate locator that becomes visible within timeout_ms."""

    deadline = time.time() + timeout_ms / 1000
    while True:
        for make in candidates:
            try:
                locator = make(page).first
                if locator.is_visible():
                    return locator
            except Exception:
                continue
        if time.time() >= deadline:
            return None
        page.wait_for_timeout(250)


class Session:
    """One browser session: the page, captured downloads, and how to ask for help."""

    def __init__(self, context, page, base, interactive, log, assist_timeout_s=300,
                 page_timeout_ms=15000, control_timeout_ms=5000, settle_ms=1500):
        self.context = context
        self.page = page
        self.base = base.rstrip("/")
        self.interactive = interactive
        self.log = log
        self.assist_timeout_s = assist_timeout_s
        # How long to wait for a report table to render, and for one button.
        self.page_timeout_ms = page_timeout_ms
        self.control_timeout_ms = control_timeout_ms
        # Pause after changing the date range or segment so the table reloads.
        self.settle_ms = settle_ms
        self.downloads = []
        for existing in context.pages:
            existing.on("download", self._captured)
        context.on("page", self._watch)

    def _captured(self, download):
        self.downloads.append(download)

    def _watch(self, page):
        page.on("download", self._captured)

    # -- asking the person -------------------------------------------------

    def ask(self, instruction):
        """Show an instruction and wait for Enter. False when nobody is there."""

        if not self.interactive:
            self.log("    (needs a person: " + instruction + ")")
            return False
        self.log("")
        self.log("  >>> " + instruction)
        try:
            answer = input("  >>> Press Enter when done (or type s + Enter to skip): ")
        except EOFError:
            return False
        return answer.strip().lower() not in ("s", "skip")

    def wait_for_download(self, instruction, timeout_s=None):
        """Wait for any download in any tab (used when the person clicks)."""

        timeout_s = timeout_s or self.assist_timeout_s
        if not self.interactive:
            self.log("    (needs a person: " + instruction + ")")
            return None
        self.log("")
        self.log("  >>> " + instruction)
        self.log(f"  >>> Waiting up to {timeout_s // 60} minutes for the download...")
        seen = len(self.downloads)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if len(self.downloads) > seen:
                return self.downloads[-1]
            self.page.wait_for_timeout(500)
        return None

    # -- signing in ----------------------------------------------------------

    def wait_for_sign_in(self, timeout_s, home_url=None):
        target = home_url or f"{self.base}/aw/overview"
        if not is_signed_in(self.page.url, self.base):
            try:
                self.page.goto(target, wait_until="domcontentloaded")
            except Exception as problem:
                raise BrowserError(f"Could not open {target}: {problem}") from None

        if is_signed_in(self.page.url, self.base):
            self.log("  Already signed in (saved browser profile).")
            return self.page.url

        self.log("")
        self.log("  >>> Sign in to Google Ads in the browser window.")
        self.log("  >>> Enter your password and complete 2-step verification and any")
        self.log("  >>> security check yourself. This script never types or clicks on")
        self.log("  >>> Google's sign-in pages; it just waits for you to finish.")
        if "accounts.google" in self.page.url:
            self.log("  >>> If Google says the browser may not be secure, do not work around")
            self.log("  >>> it: close this and use  python ppc/export.py browser --attach")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            page = self._signed_in_page()
            if page:
                self.page = page
                self.page.wait_for_load_state("domcontentloaded")
                self.log("  Signed in.")
                return self.page.url
            self.page.wait_for_timeout(1000)
        raise BrowserError(
            f"Timed out after {timeout_s // 60} minutes waiting for sign-in. Run the command again."
        )

    def _signed_in_page(self):
        for page in self.context.pages:
            try:
                if is_signed_in(page.url, self.base):
                    return page
            except Exception:
                continue
        return None

    # -- steps -----------------------------------------------------------------

    def open_report(self, report, query, saved_url=None):
        """Navigate to the report. False only if it could not be opened at all.

        A path Google redirects away from is not the report, so the next
        candidate is tried; when none of them stick, the person is asked to
        open it. Landing on the right page is enough: if its Download button
        has moved, the download step asks for that click instead.
        """

        targets = [saved_url] if saved_url else [page_url(self.base, p, query) for p in PAGES[report]["paths"]]
        for target in targets:
            try:
                self.page.goto(target, wait_until="domcontentloaded")
            except Exception:
                continue
            landed = urllib.parse.urlparse(self.page.url).path
            wanted = urllib.parse.urlparse(target).path
            if saved_url or landed.rstrip("/") == wanted.rstrip("/"):
                _first_visible(self.page, DOWNLOAD_BUTTONS, self.page_timeout_ms)  # let the table render
                return True
        where = PAGES[report]["where"]
        return self.ask(f"Open the {schema.TITLES[report]} report ({where}) in the browser.")

    def _dismiss(self):
        """Close a menu an automated step opened but could not finish."""

        try:
            self.page.keyboard.press("Escape")
        except Exception:
            pass

    def set_date_range(self, start, end, today):
        done = self._set_date_range(start, end, today)
        if not done:
            self._dismiss()
        return done

    def _set_date_range(self, start, end, today):
        preset = preset_name(start, end, today)
        button = _first_visible(self.page, DATE_BUTTONS, self.control_timeout_ms)
        if button is None:
            return False
        try:
            button.click()
            if preset:
                option = _first_visible(
                    self.page,
                    [
                        lambda p: p.get_by_role("menuitem", name=re.compile(rf"^\s*{preset}\s*$", re.I)),
                        lambda p: p.get_by_role("option", name=re.compile(rf"^\s*{preset}\s*$", re.I)),
                        lambda p: p.get_by_text(re.compile(rf"^\s*{preset}\s*$", re.I)),
                    ],
                    self.control_timeout_ms,
                )
                if option is None:
                    return False
                option.click()
            else:
                first = _first_visible(self.page, [lambda p: p.locator("input[aria-label*='start date' i]")], self.control_timeout_ms)
                last = _first_visible(self.page, [lambda p: p.locator("input[aria-label*='end date' i]")], 1000)
                if first is None or last is None:
                    return False
                first.fill(human(start))
                last.fill(human(end))
            apply = _first_visible(self.page, APPLY_BUTTONS, 500 if preset else 1000)
            if apply is not None:
                apply.click()
            self.page.wait_for_timeout(self.settle_ms)
            return True
        except Exception:
            return False

    def segment(self, group, item):
        done = self._segment(group, item)
        if not done:
            self._dismiss()
        return done

    def _segment(self, group, item):
        button = _first_visible(self.page, SEGMENT_BUTTONS, self.control_timeout_ms)
        if button is None:
            return False
        try:
            button.click()
            for label in (group, item):
                option = _first_visible(
                    self.page,
                    [
                        lambda p, l=label: p.get_by_role("menuitem", name=re.compile(rf"^\s*{re.escape(l)}\s*$", re.I)),
                        lambda p, l=label: p.get_by_role("option", name=re.compile(rf"^\s*{re.escape(l)}\s*$", re.I)),
                        lambda p, l=label: p.get_by_text(re.compile(rf"^\s*{re.escape(l)}\s*$", re.I)),
                    ],
                    self.control_timeout_ms,
                )
                if option is None:
                    return False
                option.click()
            self.page.wait_for_timeout(self.settle_ms)
            return True
        except Exception:
            return False

    def download_csv(self):
        """Click Download > .csv and return the Playwright download, or None."""

        button = _first_visible(self.page, DOWNLOAD_BUTTONS, self.control_timeout_ms)
        if button is None:
            return None
        try:
            with self.page.expect_download(timeout=120000) as pending:
                button.click()
                option = _first_visible(self.page, CSV_OPTIONS, self.control_timeout_ms)
                if option is None:
                    raise BrowserError("no .csv option")
                option.click()
            return pending.value
        except Exception:
            self._dismiss()
            return None


# --------------------------------------------------------------- launching --


def find_chrome(settings):
    configured = settings["browser"].get("chrome_path")
    if configured:
        return os.path.expanduser(configured)
    candidates = {
        "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "win32": [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ],
    }.get(sys.platform, [])
    candidates += [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    return next((c for c in candidates if c and os.path.exists(c)), "")


def open_chrome(settings, port=9222, url=f"{GOOGLE_ADS}/aw/overview"):
    """Start a normal Chrome window you sign in to yourself (for --attach)."""

    chrome = find_chrome(settings)
    if not chrome:
        raise BrowserError("Google Chrome was not found. Install it, or set browser.chrome_path in config.yaml.")
    profile = os.path.expanduser(settings["browser"]["profile_dir"]) + "-chrome"
    os.makedirs(profile, exist_ok=True)
    subprocess.Popen(
        [chrome, f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "--no-first-run", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return chrome, profile


def _launch(playwright, settings, headless, log):
    profile = os.path.expanduser(settings["browser"]["profile_dir"])
    os.makedirs(profile, exist_ok=True)
    options = {"user_data_dir": profile, "headless": headless, "accept_downloads": True, "no_viewport": True}
    chrome_path = settings["browser"].get("chrome_path")
    attempts = [{"executable_path": os.path.expanduser(chrome_path)}] if chrome_path else [{"channel": "chrome"}, {}]
    problems = []
    for extra in attempts:
        try:
            context = playwright.chromium.launch_persistent_context(**options, **extra)
            which = extra.get("executable_path") or ("Google Chrome" if extra.get("channel") else "Playwright Chromium")
            log(f"  Browser: {which}, profile {profile}")
            return context
        except Exception as problem:
            problems.append(str(problem).splitlines()[0])
    raise BrowserError(
        "Could not start a browser. Install Google Chrome, or run: python -m playwright install chromium\n  "
        + "\n  ".join(problems)
    )


# ------------------------------------------------------------------ export --


def export(settings, start, end, today, raw_dir, *, attach=None, base_url=GOOGLE_ADS,
           headless=False, interactive=None, log=print, timeouts=None):
    """Download the six reports through the website. Returns (reports, meta)."""

    from playwright.sync_api import sync_playwright

    interactive = sys.stdin.isatty() if interactive is None else interactive
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    browser_cfg = settings["browser"]
    saved = browser_cfg.get("saved_reports") or {}
    timeout_s = int(float(browser_cfg.get("login_timeout_minutes") or 15) * 60)

    reports, info = {}, {}
    meta = {"reports": info, "warnings": [], "notes": []}
    with sync_playwright() as playwright:
        browser = None
        if attach:
            if interactive:
                input("  >>> Sign in to Google Ads in the Chrome window you opened, then press Enter here: ")
            try:
                browser = playwright.chromium.connect_over_cdp(attach)
            except Exception as problem:
                raise BrowserError(
                    f"Could not connect to Chrome at {attach} ({problem}). Start it with: "
                    "python ppc/export.py open-chrome"
                ) from None
            context = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            context = _launch(playwright, settings, headless, log)
        page = context.pages[0] if context.pages else context.new_page()
        session = Session(context, page, base_url, interactive, log, **(timeouts or {}))

        try:
            signed_in_url = session.wait_for_sign_in(timeout_s, browser_cfg.get("home_url") or None)
            query = account_query(signed_in_url)
            _confirm_account(session, settings)

            range_set = False
            for report in schema.REPORTS:
                log(f"  {schema.TITLES[report]} ...")
                result = _one_report(session, report, query, saved.get(report), start, end, today, raw_dir, range_set)
                info[report] = result["info"]
                reports[report] = result["rows"]
                range_set = range_set or result["info"].get("date_range_ok", False)
                log("    " + result["info"]["summary"])
        except BrowserError:
            raise
        except Exception as problem:
            if "closed" in str(problem).lower():
                raise BrowserError("The browser window was closed before the export finished.") from None
            raise
        finally:
            if browser is None:
                try:
                    context.close()
                except Exception:
                    pass

    for report, entry in info.items():
        for warning in entry.get("warnings", []):
            meta["warnings"].append(f"{schema.FILENAMES[report]}: {warning}")
    return reports, meta


def _confirm_account(session, settings):
    wanted = dashed(settings.get("customer_id"))
    try:
        visible = wanted and wanted in session.page.content()
    except Exception:
        visible = False
    if visible:
        session.log(f"  Account {wanted} is open.")
        return
    if wanted:
        session.ask(f"Make sure the browser shows Google Ads account {wanted} (THB). Switch accounts if needed.")
    else:
        session.ask("Make sure the browser shows the THB Google Ads account. Switch accounts if needed.")


def _one_report(session, report, query, saved_url, start, end, today, raw_dir, range_set):
    entry = {"status": "failed", "warnings": [], "errors": []}
    result = {"rows": [], "info": entry}

    if not session.open_report(report, query, saved_url):
        entry["summary"] = "skipped"
        entry["errors"].append("report page was not opened")
        return result

    wanted = f"{human(start)} to {human(end)}"
    if not saved_url and not session.set_date_range(start, end, today):
        if not range_set:
            session.ask(f"Set the date range (top right) to {wanted}.")

    group, item = PAGES[report]["segment"]
    if not saved_url and not session.segment(group, item):
        if item == "Day":
            entry["warnings"].append("not split by day (Segment > Time > Day was not applied)")
        else:
            session.ask(f"Click Segment > {group} > {item} above the table.")

    target = raw_dir / f"{report}.csv"
    for attempt in range(2):
        download = session.download_csv() or session.wait_for_download(
            "Click the Download icon above the table and choose .csv."
        )
        if download is None:
            entry["summary"] = "no download"
            entry["errors"].append("no CSV was downloaded")
            return result
        suggested = download.suggested_filename or ""
        download.save_as(str(target))
        entry["raw_file"] = str(target)
        entry["downloaded_as"] = suggested

        try:
            _, rows, found_range = normalize.load_file(target, report)
        except Exception as problem:
            entry["errors"].append(f"could not read the download: {problem}")
            entry["summary"] = "unreadable download (was .csv chosen?)"
            return result

        if found_range and found_range != (start.isoformat(), end.isoformat()):
            message = f"file covers {found_range[0]}..{found_range[1]}, not {start}..{end}"
            if attempt == 0 and session.ask(f"The download {message}. Set the date range to {wanted}."):
                continue
            entry["warnings"].append(message)
        entry["date_range_ok"] = found_range == (start.isoformat(), end.isoformat())
        if not found_range:
            entry["warnings"].append("download did not state its date range; check it")
        entry.update(status="ok", rows=len(rows))
        entry["summary"] = f"{len(rows)} rows ({suggested or target.name})"
        result["rows"] = rows
        return result
    return result
