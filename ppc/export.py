#!/usr/bin/env python3
"""THB PPC exporter: pull the Google Ads reports we analyse, build the master file.

    python ppc/export.py                 API if it is set up, otherwise the browser
    python ppc/export.py api             official Google Ads API only
    python ppc/export.py check           test API access and have Google validate every query
    python ppc/export.py browser         Google Ads website in a browser (you sign in)
    python ppc/export.py import --from ~/Downloads/ads   CSVs you downloaded by hand
    python ppc/export.py rebuild exports/2026-09-28      re-merge after updating lead outcomes
    python ppc/export.py demo            synthetic data end to end, no Google needed
    python ppc/export.py status          what is configured and what is missing
    python ppc/export.py refresh-token   one-time OAuth sign-in (only for the OAuth option)
    python ppc/export.py upload          send lead statuses back to Google (validates unless --send)

Every run writes exports/<date>/ with the six reports, ppc_master_data.csv,
keyword_city_performance.csv, data_dictionary.md and manifest.json.
See ppc/README.md for setup.
"""

import argparse
import datetime
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ppc_exporter import api_source, master, normalize, schema, values, settings as config  # noqa: E402

EXIT_OK, EXIT_PARTIAL, EXIT_SETUP, EXIT_ERROR = 0, 1, 2, 3


def log(message=""):
    print(message, flush=True)


# ------------------------------------------------------------------ output --


def folder_for(settings, args, demo=False):
    root = config.output_root(settings, args.out)
    run_date = args.run_date or config.today(settings).isoformat()
    return (root / "demo" / run_date) if demo else (root / run_date), root


def summarise(folder, manifest):
    log("")
    log(f"Saved to {folder}")
    width = max(len(name) for name in manifest["files"])
    for name, rows in manifest["files"].items():
        log(f"  {name.ljust(width)}  {rows:>6} rows")
    log(f"  {'manifest.json'.ljust(width)}")
    log(f"  {'data_dictionary.md'.ljust(width)}")

    totals = manifest["totals"]
    currency = manifest.get("account", {}).get("currency") or ""
    log("")
    log(
        f"Account totals {manifest['date_range']['start']} to {manifest['date_range']['end']}: "
        f"spend {totals['campaigns_cost']:,.2f}{' ' + currency if currency else ''}, "
        f"clicks {totals['campaigns_clicks']:,.0f}, conversions {totals['campaigns_conversions']:,.1f}"
    )

    path = os.path.join(folder, "keyword_city_performance.csv")
    rows = values.read_csv(path) if os.path.exists(path) else []
    if rows:
        exact = totals.get("exact_city_spend_pct")
        log("")
        log("Top Keyword + City by spend" + (f" ({exact:.0f}% of spend has an exact city):" if exact is not None else ":"))
        log(f"  {'keyword':32} {'city':16} {'spend':>10} {'clicks':>7} {'conv':>6}  city_method")
        for row in rows[:10]:
            log(
                f"  {row['keyword'][:32]:32} {row['city'][:16]:16} {row['spend'] or 0:>10,.2f} "
                f"{row['clicks'] or 0:>7,.0f} {row['conversions'] or 0:>6,.1f}  {row['city_method']}"
            )
    if manifest["warnings"]:
        log("")
        log("Warnings:")
        for warning in manifest["warnings"]:
            log("  - " + warning)


def finish(folder, reports, meta, start, end, source, outcomes_path):
    manifest = master.write_bundle(
        str(folder), reports, start=start, end=end, source=source, meta=meta, outcomes_path=outcomes_path, log=log
    )
    summarise(folder, manifest)
    failed = [r for r, info in manifest["reports"].items() if info.get("status") == "failed"]
    return EXIT_PARTIAL if failed else EXIT_OK


# ---------------------------------------------------------------- commands --


def run_api(settings, args, start, end):
    missing = api_source.missing_settings(settings)
    if missing:
        raise api_source.ApiNotConfigured(missing)
    folder, root = folder_for(settings, args)
    log(f"Google Ads API export, {start} to {end}")
    reports, meta = api_source.export(settings, start, end, log=log)
    return finish(folder, reports, meta, start, end, "api", master.ensure_outcomes_file(root))


def run_browser(settings, args, start, end):
    from ppc_exporter import browser_source

    folder, root = folder_for(settings, args)
    log(f"Browser export, {start} to {end}")
    attach = args.attach if getattr(args, "attach", None) else None
    reports, meta = browser_source.export(
        settings,
        start,
        end,
        config.today(settings),
        folder / "raw",
        attach=attach,
        base_url=getattr(args, "base_url", None) or browser_source.GOOGLE_ADS,
        headless=getattr(args, "headless", False),
        interactive=None if not getattr(args, "no_prompts", False) else False,
        log=log,
    )
    meta.setdefault("notes", []).append(f"Raw downloads kept in {folder / 'raw'}")
    return finish(folder, reports, meta, start, end, "browser", master.ensure_outcomes_file(root))


def cmd_auto(settings, args, start, end):
    missing = api_source.missing_settings(settings)
    if not missing:
        try:
            return run_api(settings, args, start, end)
        except api_source.ApiAccessError as problem:
            log("")
            log("The Google Ads API refused the export:")
            log(str(problem))
            reason = "the API is not usable yet"
    else:
        log("The Google Ads API is not set up yet. Missing:")
        for item in missing:
            log("  - " + item)
        reason = "the API is not set up"

    if not sys.stdin.isatty():
        log("")
        log(f"Not falling back to the browser because {reason} and nobody is at the keyboard to sign in.")
        log("Run  python ppc/export.py browser  yourself, or finish the API setup (ppc/README.md).")
        return EXIT_SETUP
    log("")
    log(f"Because {reason}, using the browser fallback. You will sign in to Google yourself.")
    return run_browser(settings, args, start, end)


def cmd_check(settings, args, start, end):
    missing = api_source.missing_settings(settings)
    if missing:
        raise api_source.ApiNotConfigured(missing)
    log("Checking Google Ads API access ...")
    account, results = api_source.check(settings, start, end, log=log)
    log(f"  Access OK: {account['name']} ({account['customer_id']}), {account['currency']}, {account['time_zone']}")
    worst = EXIT_OK
    for report, variant, ok, message in results:
        label = schema.FILENAMES[report]
        if ok:
            note = "" if variant == 0 else f"  (Google rejected the full query; the smaller variant {variant} will run)"
            log(f"  {label:18} query OK{note}")
        else:
            worst = EXIT_PARTIAL
            log(f"  {label:18} REJECTED: {message}")
    log("")
    log("Ready: run  python ppc/export.py api" if worst == EXIT_OK else "Some queries were rejected; see above.")
    return worst


def cmd_demo(settings, args, start, end):
    from ppc_exporter import demo

    folder, root = folder_for(settings, args, demo=True)
    log(f"DEMO export (synthetic data), {start} to {end}")
    reports, cells = demo.reports(start, end)
    outcomes = root / "demo" / master.OUTCOMES_FILE
    os.makedirs(outcomes.parent, exist_ok=True)
    leads = demo.write_demo_outcomes(outcomes, cells)
    log(f"  Simulated {sum(len(r) for r in reports.values())} report rows and {leads} demo leads ({outcomes}).")
    meta = {
        "account": {"customer_id": "000-000-0000", "name": "DEMO (synthetic)", "currency": "USD",
                    "time_zone": settings.get("timezone")},
        "notes": ["Synthetic data from ppc/ppc_exporter/demo.py. Not real performance."],
    }
    return finish(folder, reports, meta, start, end, "demo", outcomes)


def _import_paths(sources):
    paths = []
    for source in sources:
        source = os.path.expanduser(source)
        if os.path.isdir(source):
            for pattern in ("*.csv", "*.tsv", "*.txt"):
                paths.extend(sorted(glob.glob(os.path.join(source, pattern))))
        else:
            paths.extend(sorted(glob.glob(source)) or [source])
    return paths


def cmd_import(settings, args, start, end):
    reports = {r: [] for r in schema.REPORTS}
    info = {r: {"status": "empty", "files": []} for r in schema.REPORTS}
    ranges, warnings = set(), []
    for path in _import_paths(args.sources):
        name = os.path.basename(path)
        if name in ("ppc_master_data.csv", "keyword_city_performance.csv", master.OUTCOMES_FILE):
            continue
        try:
            report, rows, found = normalize.load_file(path)
        except Exception as problem:
            warnings.append(f"skipped {name}: {problem}")
            log(f"  skipped {name}: {problem}")
            continue
        reports[report].extend(rows)
        info[report]["files"].append(path)
        info[report]["status"] = "ok"
        if found:
            ranges.add(found)
        log(f"  {name}: {schema.TITLES[report]}, {len(rows)} rows")
    if not any(reports.values()):
        log("No importable Google Ads CSVs found.")
        return EXIT_SETUP

    if not args.start and len(ranges) == 1:
        first, last = next(iter(ranges))
        start, end = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
        log(f"  Date range taken from the files: {start} to {end}")
    elif len(ranges) > 1:
        warnings.append("The imported files cover different date ranges: " + ", ".join(f"{a}..{b}" for a, b in sorted(ranges)))
    folder, root = folder_for(settings, args)
    return finish(folder, reports, {"reports": info, "warnings": warnings}, start, end, "import", master.ensure_outcomes_file(root))


def cmd_rebuild(settings, args, _start, _end):
    import json

    folder = os.path.abspath(os.path.expanduser(args.folder))
    manifest_path = os.path.join(folder, "manifest.json")
    if not os.path.exists(manifest_path):
        log(f"{folder} has no manifest.json; point rebuild at a folder this tool wrote.")
        return EXIT_SETUP
    with open(manifest_path, encoding="utf-8") as handle:
        previous = json.load(handle)
    start = datetime.date.fromisoformat(previous["date_range"]["start"])
    end = datetime.date.fromisoformat(previous["date_range"]["end"])
    root = config.output_root(settings, args.out)
    if previous["source"] == "demo":
        outcomes = root / "demo" / master.OUTCOMES_FILE
    else:
        outcomes = master.ensure_outcomes_file(root)
    log(f"Rebuilding {folder} ({start} to {end}) with lead outcomes from {outcomes}")
    reports = master.read_bundle(folder)
    meta = {"account": previous.get("account", {}), "reports": previous.get("reports", {}), "notes": previous.get("notes", [])}
    return finish(folder, reports, meta, start, end, previous["source"], outcomes)


def cmd_status(settings, args, start, end):
    api = settings["api"]
    log(f"Config file: {settings['config_path']} ({'found' if settings['config_found'] else 'not found'})")
    log(f"Pasted credentials file: {settings['env_path']} ({'found' if settings['env_found'] else 'not found'})")
    cid = config.digits(settings.get("customer_id"))
    log(f"customer_id: {cid if cid else 'missing'}")
    if api.get("json_key_file_path"):
        method = "service-account key file"
    elif any(api.get(k) for k in ("client_id", "client_secret", "refresh_token")):
        method = "OAuth refresh token"
    else:
        method = "none yet"
    log(f"API credentials: {method}")
    for key in ("json_key_file_path", "client_id", "client_secret", "refresh_token"):
        log(f"  {key:20} {config.describe_secret(api.get(key))}")
    login = config.digits(api.get("login_customer_id"))
    log(f"  {'login_customer_id':20} {login if login else 'not set (only needed with a manager account)'}")
    missing = api_source.missing_settings(settings)
    log("API export: " + ("ready (run: python ppc/export.py check)" if not missing else "not ready"))
    for item in missing:
        log("  - missing " + item)
    root = config.output_root(settings, args.out)
    log(f"Exports go to: {root / config.today(settings).isoformat()}/")
    log(f"Lead outcomes file: {root / master.OUTCOMES_FILE}")
    log(f"Browser profile (browser mode): {os.path.expanduser(settings['browser']['profile_dir'])}")
    log(f"Default date range: {start} to {end}")
    return EXIT_OK if not missing else EXIT_SETUP


def save_refresh_token(settings, token):
    """Write the token where the current one lives: ppc/.env first, then config.yaml.

    Returns the path written, or None when neither file holds a token line.
    """

    for path, pattern, render in (
        (settings.get("env_path"), r"(?m)^(\s*(?:set\s+|export\s+)?GOOGLE_ADS_REFRESH_TOKEN\s*=\s*).*$", lambda m: m.group(1) + token),
        (settings.get("config_path"), r"(?m)^(\s*refresh_token:\s*).*$", lambda m: m.group(1) + '"' + token + '"'),
    ):
        if not path or not os.path.exists(path):
            continue
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
        updated, count = re.subn(pattern, render, text, count=1)
        if count:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(updated)
            return path
    return None


def cmd_refresh_token(settings, args, _start, _end):
    api = settings["api"]
    if not (api.get("client_id") and api.get("client_secret")):
        log("Put your OAuth client_id and client_secret in ppc/.env or ppc/config.yaml first (see README, OAuth option).")
        return EXIT_SETUP
    log("A browser window opens. Sign in with the Google account that runs THB's Google Ads and allow both")
    log("permissions (Google Ads, and Data Manager for sending lead results back).")
    token = api_source.generate_refresh_token(api["client_id"], api["client_secret"])
    written = None if args.print_only else save_refresh_token(settings, token)
    if written:
        log(f"Saved the new refresh token into {written}. Next: python ppc/export.py check")
        return EXIT_OK
    log("Refresh token (store it like a password; put it in ppc/.env as GOOGLE_ADS_REFRESH_TOKEN=...):")
    log(token)
    return EXIT_OK


def cmd_upload(settings, args, _start, _end):
    from ppc_exporter import feedback

    missing = api_source.missing_settings(settings)
    if missing:
        raise api_source.ApiNotConfigured(missing)
    path = os.path.expanduser(args.file) if args.file else str(config.output_root(settings, args.out) / master.OUTCOMES_FILE)
    log(f"Lead results file: {path}")
    try:
        return feedback.run(settings, path, send_for_real=args.send, log=log)
    except Exception as problem:
        if type(problem).__name__ == "RefreshError":
            log(api_source.explain(problem, settings))
            return EXIT_SETUP
        raise


def cmd_open_chrome(settings, args, _start, _end):
    from ppc_exporter import browser_source

    chrome, profile = browser_source.open_chrome(settings, port=args.port)
    log(f"Opened Chrome ({chrome}) with its own profile at {profile}.")
    log("Sign in to Google Ads in that window yourself, then run:")
    log(f"  python ppc/export.py browser --attach http://127.0.0.1:{args.port}")
    return EXIT_OK


# -------------------------------------------------------------------- main --


def _common(p, default):
    p.add_argument("--config", default=default, help="settings file (default: ppc/config.yaml)")
    p.add_argument("--start", default=default, help="first day, e.g. 2026-09-01 (default: 30 days ending yesterday)")
    p.add_argument("--end", default=default, help="last day, e.g. 2026-09-27")
    p.add_argument("--days", type=int, default=default, help="last N complete days (default 30)")
    p.add_argument("--customer-id", default=default, help="Google Ads account ID (overrides config)")
    p.add_argument("--out", default=default, help="export root folder (default: exports/ in the repo)")
    p.add_argument("--run-date", default=default, help=argparse.SUPPRESS)


def parser():
    p = argparse.ArgumentParser(description="Export THB Google Ads reports for PPC analysis.")
    _common(p, None)
    # The same options after the command ("api --days 7") too. SUPPRESS keeps
    # a value given before the command from being reset to None.
    common = argparse.ArgumentParser(add_help=False)
    _common(common, argparse.SUPPRESS)
    sub = p.add_subparsers(dest="command")

    def command(name, help_text):
        return sub.add_parser(name, help=help_text, parents=[common])

    command("auto", "API if set up, otherwise browser (the default)")
    command("api", "export through the official Google Ads API")
    command("check", "test API access and validate every query with Google")

    b = command("browser", "export through the Google Ads website (you sign in)")
    b.add_argument("--attach", nargs="?", const="http://127.0.0.1:9222",
                   help="connect to a Chrome you opened with open-chrome and signed in to yourself")
    b.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    b.add_argument("--base-url", help=argparse.SUPPRESS)
    b.add_argument("--no-prompts", action="store_true", help=argparse.SUPPRESS)

    i = command("import", "build the exports from CSVs you downloaded yourself")
    i.add_argument("--from", dest="sources", nargs="+", required=True, help="folder(s) or CSV file(s)")

    r = command("rebuild", "rebuild master + keyword/city files in an export folder")
    r.add_argument("folder")

    command("demo", "run end to end on synthetic data")
    command("status", "show what is configured and what is missing")

    t = command("refresh-token", "one-time Google sign-in to create an OAuth refresh token")
    t.add_argument("--print-only", action="store_true", help="print the token instead of saving it")

    u = command("upload", "send lead statuses back to Google Ads (validates only, unless --send)")
    u.add_argument("--file", help="lead results CSV (default: exports/lead_outcomes.csv)")
    u.add_argument("--send", action="store_true", help="record the conversions in Google Ads (default: validate only)")

    c = command("open-chrome", "open a normal Chrome window for --attach")
    c.add_argument("--port", type=int, default=9222)
    return p


COMMANDS = {
    None: cmd_auto,
    "auto": cmd_auto,
    "api": run_api,
    "check": cmd_check,
    "browser": run_browser,
    "import": cmd_import,
    "rebuild": cmd_rebuild,
    "demo": cmd_demo,
    "status": cmd_status,
    "refresh-token": cmd_refresh_token,
    "upload": cmd_upload,
    "open-chrome": cmd_open_chrome,
}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = config.load(args.config)
        if args.customer_id:
            settings["customer_id"] = args.customer_id
        start, end = config.date_range(settings, args.start, args.end, args.days)
        return COMMANDS[args.command](settings, args, start, end)
    except api_source.ApiNotConfigured as problem:
        log("The Google Ads API is not set up yet. Missing:")
        for item in problem.missing:
            log("  - " + item)
        log("Already have the values as GOOGLE_ADS_...=... lines? Paste them into ppc/.env (notepad ppc\\.env on Windows).")
        log("Setup steps: ppc/README.md (section 'Google Ads API setup'). Check with: python ppc/export.py status")
        return EXIT_SETUP
    except api_source.ApiAccessError as problem:
        log("Google refused the request:")
        log(str(problem))
        return EXIT_SETUP
    except config.SettingsError as problem:
        log(f"Settings problem: {problem}")
        return EXIT_SETUP
    except KeyboardInterrupt:
        log("\nStopped.")
        return EXIT_ERROR
    except Exception as problem:
        name = type(problem).__name__
        if name == "BrowserError":
            log(f"Browser export stopped: {problem}")
            return EXIT_ERROR
        raise


if __name__ == "__main__":
    sys.exit(main())
