"""The export.py command line, run the way a person would run it."""

import filecmp
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT = os.path.join(HERE, "export.py")


def run(*args, env=None, stdin=subprocess.DEVNULL):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_ADS_")}
    clean.update(env or {})
    return subprocess.run([sys.executable, EXPORT, *args], capture_output=True, text=True, env=clean, stdin=stdin, timeout=120)


@pytest.fixture
def no_config(tmp_path):
    return ["--config", str(tmp_path / "none.yaml"), "--out", str(tmp_path / "exports"), "--run-date", "2026-09-28"]


def test_api_without_credentials_says_what_is_missing(no_config):
    result = run("api", *no_config)
    assert result.returncode == 2
    assert "customer_id" in result.stdout and "service-account key file" in result.stdout


def test_default_mode_does_not_open_a_browser_when_nobody_is_there(no_config):
    result = run(*no_config)
    assert result.returncode == 2
    assert "nobody is at the keyboard" in result.stdout


def test_status_never_prints_secrets(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text('customer_id: "123-456-7890"\napi:\n  client_id: "id-VALUE"\n  client_secret: "SECRET-VALUE"\n  refresh_token: "TOKEN-VALUE"\n')
    result = run("status", "--config", str(config))
    assert result.returncode == 0, result.stdout
    assert "SECRET-VALUE" not in result.stdout and "TOKEN-VALUE" not in result.stdout and "id-VALUE" not in result.stdout
    assert "1234567890" in result.stdout and "OAuth refresh token" in result.stdout


def test_environment_variables_override_the_file(tmp_path):
    result = run("status", "--config", str(tmp_path / "none.yaml"),
                 env={"GOOGLE_ADS_CUSTOMER_ID": "111-222-3333", "GOOGLE_ADS_JSON_KEY_FILE_PATH": "/k.json"})
    assert "1112223333" in result.stdout and "service-account key file" in result.stdout


def test_demo_then_rebuild_is_stable(no_config, tmp_path):
    result = run("demo", *no_config)
    assert result.returncode == 0, result.stdout + result.stderr
    folder = tmp_path / "exports" / "demo" / "2026-09-28"
    for name in ("search_terms.csv", "keywords.csv", "campaigns.csv", "ad_groups.csv", "locations.csv",
                 "conversions.csv", "ppc_master_data.csv", "keyword_city_performance.csv", "manifest.json",
                 "data_dictionary.md"):
        assert (folder / name).exists(), name
    before = (folder / "keyword_city_performance.csv").read_bytes()
    master_before = (folder / "ppc_master_data.csv").read_bytes()

    result = run("rebuild", str(folder), *no_config)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (folder / "keyword_city_performance.csv").read_bytes() == before
    assert (folder / "ppc_master_data.csv").read_bytes() == master_before


def test_import_round_trip_matches_the_original(no_config, tmp_path):
    run("demo", *no_config)
    source = tmp_path / "exports" / "demo" / "2026-09-28"
    result = run("import", "--from", str(source), "--start", "2026-08-29", "--end", "2026-09-27", *no_config)
    assert result.returncode == 0, result.stdout + result.stderr
    imported = tmp_path / "exports" / "2026-09-28"
    for name in ("search_terms.csv", "keywords.csv", "campaigns.csv", "ad_groups.csv", "locations.csv", "conversions.csv"):
        assert filecmp.cmp(source / name, imported / name, shallow=False), name
    manifest = json.loads((imported / "manifest.json").read_text())
    assert manifest["source"] == "import"
    assert (tmp_path / "exports" / "lead_outcomes.csv").exists()


def test_import_of_ui_downloads(no_config, tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "Search terms report.csv").write_text(
        "Search terms report\nSeptember 1, 2026 - September 27, 2026\n"
        "Search term,Match type,Campaign,Ad group,Keyword,Impr.,Clicks,Cost,Conversions\n"
        "we buy houses oakland,Phrase match,THB,Cash,\"\"\"we buy houses\"\"\",100,10,150.00,1\n"
        "Total: Account,,,,,100,10,150.00,1\n"
    )
    (downloads / "notes.csv").write_text("just,some,notes\n1,2,3\n")
    result = run("import", "--from", str(downloads), *no_config)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Date range taken from the files: 2026-09-01 to 2026-09-27" in result.stdout
    assert "skipped notes.csv" in result.stdout
    manifest = json.loads((tmp_path / "exports" / "2026-09-28" / "manifest.json").read_text())
    assert manifest["files"]["search_terms.csv"] == 1
    assert manifest["date_range"] == {"start": "2026-09-01", "end": "2026-09-27"}


def test_options_work_after_the_command(no_config):
    result = run("status", *no_config, "--days", "7")
    assert "Default date range: 2026-09-" in result.stdout


def test_pasted_env_file_next_to_config_is_used(tmp_path):
    (tmp_path / ".env").write_bytes(
        "﻿# pasted from the Google Ads setup\n"
        "GOOGLE_ADS_CLIENT_ID=id-VALUE.apps.googleusercontent.com\n"
        "set GOOGLE_ADS_CUSTOMER_ID=9897155298\n"
        'GOOGLE_ADS_CLIENT_SECRET = "SECRET-VALUE"\n'
        "GOOGLE_ADS_REFRESH_TOKEN=1//TOKEN-VALUE\n"
        "GOOGLE_ADS_DEVELOPER_TOKEN=DEV-VALUE\n".encode("utf-8")
    )
    result = run("status", "--config", str(tmp_path / "config.yaml"))
    assert result.returncode == 0, result.stdout
    assert "(found)" in result.stdout and "9897155298" in result.stdout
    assert "API export: ready" in result.stdout
    for secret in ("SECRET-VALUE", "TOKEN-VALUE", "id-VALUE", "DEV-VALUE"):
        assert secret not in result.stdout


def test_real_environment_beats_the_env_file(tmp_path):
    from ppc_exporter import settings as config

    (tmp_path / ".env").write_text("GOOGLE_ADS_CUSTOMER_ID=1111111111\nGOOGLE_ADS_CLIENT_ID=from-file\n")
    loaded = config.load(tmp_path / "config.yaml", environ={"GOOGLE_ADS_CUSTOMER_ID": "2222222222"})
    assert loaded["customer_id"] == "2222222222"
    assert loaded["api"]["client_id"] == "from-file"
    assert loaded["env_found"] is True


def test_missing_setup_message_mentions_the_env_file(no_config):
    result = run("api", *no_config)
    assert "ppc/.env" in result.stdout


def test_rebuild_keeps_every_total(no_config, tmp_path):
    run("demo", *no_config)
    folder = tmp_path / "exports" / "demo" / "2026-09-28"
    before = json.loads((folder / "manifest.json").read_text())["totals"]
    run("rebuild", str(folder), *no_config)
    assert json.loads((folder / "manifest.json").read_text())["totals"] == before
