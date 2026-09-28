"""Settings from ppc/config.yaml, with environment variables taking priority.

Nothing secret has a default and nothing secret is ever printed: status
output shows whether a value is set, never the value.
"""

import copy
import datetime
import os
import re
import zoneinfo
from pathlib import Path

import yaml

PPC_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PPC_DIR.parent
DEFAULT_CONFIG = PPC_DIR / "config.yaml"

# Environment variable -> (section, key). The GOOGLE_ADS_* names are the
# ones the official client library documents, so an existing setup works.
ENV_OVERRIDES = {
    "GOOGLE_ADS_CUSTOMER_ID": (None, "customer_id"),
    "GOOGLE_ADS_JSON_KEY_FILE_PATH": ("api", "json_key_file_path"),
    "GOOGLE_ADS_CLIENT_ID": ("api", "client_id"),
    "GOOGLE_ADS_CLIENT_SECRET": ("api", "client_secret"),
    "GOOGLE_ADS_REFRESH_TOKEN": ("api", "refresh_token"),
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID": ("api", "login_customer_id"),
    "GOOGLE_ADS_DEVELOPER_TOKEN": ("api", "developer_token"),
    "PPC_CHROME_PATH": ("browser", "chrome_path"),
    "PPC_BROWSER_PROFILE": ("browser", "profile_dir"),
}

DEFAULTS = {
    "customer_id": "",
    "timezone": "America/Los_Angeles",
    "default_days": 30,
    "output_dir": "exports",
    "api": {
        "json_key_file_path": "",
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
        "login_customer_id": "",
        "developer_token": "",
    },
    "browser": {
        "profile_dir": "~/.thb-ppc-browser",
        "chrome_path": "",
        "home_url": "",
        "login_timeout_minutes": 15,
        "saved_reports": {},
    },
}


class SettingsError(Exception):
    pass


def _merge(base, extra):
    merged = dict(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


def load(config_path=None, environ=None):
    environ = os.environ if environ is None else environ
    path = Path(config_path) if config_path else DEFAULT_CONFIG

    data = {}
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as problem:
            raise SettingsError(f"{path} is not valid YAML: {problem}") from None
        if not isinstance(data, dict):
            raise SettingsError(f"{path} must be a YAML mapping of settings.")

    settings = _merge(copy.deepcopy(DEFAULTS), data)

    for variable, (section, key) in ENV_OVERRIDES.items():
        value = environ.get(variable, "").strip()
        if not value:
            continue
        if section:
            settings[section][key] = value
        else:
            settings[key] = value

    for section in ("api", "browser"):
        for key, value in list(settings[section].items()):
            if isinstance(value, str):
                settings[section][key] = value.strip()
    settings["customer_id"] = str(settings.get("customer_id") or "").strip()
    settings["config_path"] = str(path)
    settings["config_found"] = path.exists()
    return settings


def digits(value):
    """A customer ID with the dashes Google shows in the UI removed."""

    return re.sub(r"\D", "", str(value or ""))


def office_zone(settings):
    try:
        return zoneinfo.ZoneInfo(settings.get("timezone") or "America/Los_Angeles")
    except zoneinfo.ZoneInfoNotFoundError:
        raise SettingsError(
            f"Unknown time zone {settings.get('timezone')!r} in config.yaml."
        ) from None


def today(settings):
    return datetime.datetime.now(office_zone(settings)).date()


def date_range(settings, start=None, end=None, days=None):
    """(start, end) as dates. Default: the last N complete days, ending yesterday.

    That default is exactly Google Ads' own "Last 30 days" preset, which
    also ends yesterday, so API and browser exports cover the same days.
    """

    parse = datetime.date.fromisoformat
    try:
        if start and end:
            first, last = parse(start), parse(end)
        elif start or end:
            raise SettingsError("Give both --start and --end, or neither.")
        else:
            span = int(days or settings.get("default_days") or 30)
            if span < 1:
                raise SettingsError("--days must be at least 1.")
            last = today(settings) - datetime.timedelta(days=1)
            first = last - datetime.timedelta(days=span - 1)
    except ValueError as problem:
        raise SettingsError(f"Dates must look like 2026-09-01 ({problem}).") from None

    if first > last:
        raise SettingsError(f"--start {first} is after --end {last}.")
    return first, last


def output_root(settings, override=None):
    root = Path(os.path.expanduser(override or settings.get("output_dir") or "exports"))
    return root if root.is_absolute() else REPO_ROOT / root


def describe_secret(value):
    return "set" if value else "missing"
