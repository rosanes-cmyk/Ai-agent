"""Reading, writing and deriving numbers the same way for every source."""

import csv
import datetime
import os
import re
import tempfile

from . import schema

_BLANKS = {"", "--", "-", "—", "n/a", "na", "null", "none", "nan", " --"}


def parse_number(text):
    """A number from an export cell, or None when the cell means "no data".

    Handles what Google Ads UI downloads contain: thousands separators,
    currency symbols, percent signs, "--" for empty, and the "< 10%" /
    "> 90%" impression-share buckets (read the way the API reports them,
    9.99 and 90.01).
    """

    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)

    s = str(text).strip()
    if s.lower() in _BLANKS:
        return None

    bucket = re.fullmatch(r"([<>])\s*([\d.]+)\s*%?", s)
    if bucket:
        edge = float(bucket.group(2))
        return round(edge - 0.01, 2) if bucket.group(1) == "<" else round(edge + 0.01, 2)

    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    if s in ("", ".", "-"):
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def safe_div(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def pct(numerator, denominator):
    ratio = safe_div(numerator, denominator)
    return None if ratio is None else ratio * 100


def add_ratios(row):
    """Recompute CTR, CPC, conversion rate and cost per conversion.

    Only overwrites a ratio when its inputs are present, so a browser
    download that lacks e.g. impressions keeps Google's own CTR column.
    """

    impressions = row.get("impressions")
    clicks = row.get("clicks")
    cost = row.get("cost")
    conversions = row.get("conversions")

    if clicks is not None and impressions is not None:
        row["ctr_pct"] = pct(clicks, impressions)
    if cost is not None and clicks is not None:
        row["avg_cpc"] = safe_div(cost, clicks)
    if conversions is not None and clicks is not None:
        row["conv_rate_pct"] = pct(conversions, clicks)
    if cost is not None and conversions is not None:
        row["cost_per_conversion"] = safe_div(cost, conversions)
    return row


def fmt(column, value, fractional=()):
    if value is None or value == "":
        return ""
    if column in schema.NUMERIC:
        if isinstance(value, str):
            value = parse_number(value)
            if value is None:
                return ""
        if column in schema.INTEGER and column not in fractional:
            return str(int(round(value)))
        return "%.2f" % value
    return str(value)


def typed(column, text):
    """A cell read back from one of our own CSVs, as its proper type."""

    if column in schema.NUMERIC:
        number = parse_number(text)
        if column in schema.INTEGER and number is not None and number.is_integer():
            return int(number)
        return number
    return "" if text is None else text


def write_csv(path, columns, rows, fractional=()):
    """Write rows to path atomically, so a crash never leaves half a file.

    fractional names count columns that hold estimates (a keyword's clicks
    split across cities), written with decimals so they still add up.
    """

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        # utf-8-sig writes the byte-order mark Excel on Windows needs to read
        # UTF-8; without it "Sell My House Fast – Exact" opens as "â€“".
        with os.fdopen(handle, "w", newline="", encoding="utf-8-sig") as out:
            writer = csv.writer(out)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([fmt(c, row.get(c), fractional) for c in columns])
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        return [
            {column: typed(column, value) for column, value in row.items()}
            for row in reader
        ]


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%a, %b %d, %Y",
    "%A, %B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y%m%d",
    "%Y/%m/%d",
)


def parse_date(text):
    """ISO date string from the formats Google Ads and spreadsheets use."""

    if text is None:
        return ""
    if isinstance(text, (datetime.date, datetime.datetime)):
        return text.strftime("%Y-%m-%d")
    s = re.sub(r"\s+", " ", str(text).strip())
    if not s or s.lower() in _BLANKS:
        return ""
    for form in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, form).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def parse_flag(text):
    """1 for yes-like cells, 0 for no-like cells, None for blank."""

    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    if s in ("1", "y", "yes", "true", "x", "✓", "✔", "done"):
        return 1
    if s in ("0", "n", "no", "false"):
        return 0
    number = parse_number(s)
    return None if number is None else (1 if number > 0 else 0)
