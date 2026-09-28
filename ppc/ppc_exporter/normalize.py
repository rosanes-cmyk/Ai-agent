"""Turn Google Ads UI downloads (and other people's CSVs) into canonical rows.

A UI download is not a clean table: it opens with a report title and a
date-range line, closes with "Total:" rows, writes "--" for empty cells,
formats numbers as "1,234.56" and "5.23%", and the "Excel .csv" option is
really UTF-16 tab-separated. Everything here exists to absorb that, so the
rest of the pipeline only ever sees canonical rows.
"""

import csv
import io
import os
import re

from . import schema, values

# Normalised header text -> canonical column. Headers are normalised by
# lower-casing and collapsing punctuation to spaces: "Avg. CPC" -> "avg cpc".
ALIASES = {
    "day": "date",
    "date": "date",
    "campaign": "campaign",
    "campaign name": "campaign",
    "campaign id": "campaign_id",
    "ad group": "ad_group",
    "ad group name": "ad_group",
    "ad group id": "ad_group_id",
    "keyword": "keyword",
    "search keyword": "keyword",
    "keyword text": "keyword",
    "keyword id": "keyword_id",
    "search keyword match type": "match_type",
    "keyword match type": "match_type",
    "search term": "search_term",
    "search terms": "search_term",
    "search term match type": "search_term_match_type",
    "added excluded": "search_term_status",
    "city": "city",
    "city user location": "city",
    "city matched location": "city",
    "city location of interest": "city",
    "city physical location": "city",
    "matched location": "location_full",
    "user location": "location_full",
    "location": "location_full",
    "locations": "location_full",
    "most specific location": "location_full",
    "most specific location user location": "location_full",
    "region": "region",
    "region user location": "region",
    "region matched location": "region",
    "state": "region",
    "country territory": "country",
    "country territory user location": "country",
    "country territory matched location": "country",
    "country": "country",
    "location type": "location_type",
    "impr": "impressions",
    "impressions": "impressions",
    "clicks": "clicks",
    "ctr": "ctr_pct",
    "avg cpc": "avg_cpc",
    "average cpc": "avg_cpc",
    "cost": "cost",
    "spend": "cost",
    "conversions": "conversions",
    "conv": "conversions",
    "conv rate": "conv_rate_pct",
    "conversion rate": "conv_rate_pct",
    "cost conv": "cost_per_conversion",
    "cost per conversion": "cost_per_conversion",
    "cost per conv": "cost_per_conversion",
    "conv value": "conversion_value",
    "conversion value": "conversion_value",
    "total conv value": "conversion_value",
    "conversions value": "conversion_value",
    "all conv": "all_conversions",
    "all conversions": "all_conversions",
    "all conv value": "all_conversion_value",
    "all conversions value": "all_conversion_value",
    "conversion action": "conversion_action",
    "conversion name": "conversion_action",
    "conversion action name": "conversion_action",
    "conversion category": "conversion_category",
    "conversion action category": "conversion_category",
    "action category": "conversion_category",
    "currency code": "currency",
    "currency": "currency",
    "campaign status": "campaign_status",
    "campaign state": "campaign_status",
    "ad group status": "ad_group_status",
    "ad group state": "ad_group_status",
    "keyword status": "keyword_status",
    "keyword state": "keyword_status",
    "campaign type": "channel_type",
    "advertising channel type": "channel_type",
    "search impr share": "search_impr_share_pct",
    "search impression share": "search_impr_share_pct",
    "search lost is budget": "search_lost_is_budget_pct",
    "search lost impr share budget": "search_lost_is_budget_pct",
    "search lost is rank": "search_lost_is_rank_pct",
    "search lost impr share rank": "search_lost_is_rank_pct",
}

# Headers whose meaning depends on the report ("Match type" in a search
# terms download is how the term matched, not the keyword's match type).
CONTEXT_ALIASES = {
    "match type": {"search_terms": "search_term_match_type", None: "match_type"},
    "status": {
        "campaigns": "campaign_status",
        "ad_groups": "ad_group_status",
        "keywords": "keyword_status",
    },
}

MATCH_TYPES = {
    "exact match": "EXACT",
    "phrase match": "PHRASE",
    "broad match": "BROAD",
    "exact match close variant": "NEAR_EXACT",
    "phrase match close variant": "NEAR_PHRASE",
    "exact close variant": "NEAR_EXACT",
    "phrase close variant": "NEAR_PHRASE",
    "near exact": "NEAR_EXACT",
    "near phrase": "NEAR_PHRASE",
}

LOCATION_TYPES = {
    "area of interest": "AREA_OF_INTEREST",
    "location of interest": "AREA_OF_INTEREST",
    "interest": "AREA_OF_INTEREST",
    "physical location": "LOCATION_OF_PRESENCE",
    "location of presence": "LOCATION_OF_PRESENCE",
    "presence": "LOCATION_OF_PRESENCE",
}

ENUM_COLUMNS = {
    "campaign_status",
    "ad_group_status",
    "keyword_status",
    "channel_type",
    "conversion_category",
    "search_term_status",
}

DIMENSIONS = {
    "date", "campaign", "campaign_id", "ad_group", "ad_group_id", "keyword", "keyword_id",
    "search_term", "city", "region", "country", "location_full", "conversion_action",
}


def header_key(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


# Our own canonical names map to themselves, so re-importing an export works.
# An exact snake_case name wins over any alias: our "match_type" is always the
# keyword's match type, even inside a search terms file.
CANONICAL_NAMES = set(schema.MASTER_COLUMNS)
for _column in CANONICAL_NAMES:
    ALIASES.setdefault(header_key(_column), _column)


def canonical(header, report=None):
    exact = str(header or "").strip()
    if exact in CANONICAL_NAMES:
        return exact
    key = header_key(header)
    if key in CONTEXT_ALIASES:
        options = CONTEXT_ALIASES[key]
        return options.get(report) or options.get(None)
    return ALIASES.get(key)


# ------------------------------------------------------------------ files --


def decode(raw):
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    if b"\x00" in raw[:200]:
        return raw.decode("utf-16-le")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def _delimiter(lines):
    for line in lines[:30]:
        if line.count("\t") >= 2:
            return "\t"
    return ","


def _is_total(cells):
    for cell in cells:
        text = cell.strip()
        if text:
            return text.lower().startswith("total")
    return False


def read_table(text):
    """(headers, rows, preamble). Finds the real header row under any title lines."""

    lines = text.splitlines()
    delimiter = _delimiter(lines)
    records = list(csv.reader(io.StringIO(text), delimiter=delimiter))

    header_at = None
    for index, cells in enumerate(records[:40]):
        known = sum(1 for cell in cells if canonical(cell) or header_key(cell) in CONTEXT_ALIASES)
        if known >= 2:
            header_at = index
            break
    if header_at is None:
        raise ValueError("no header row with recognisable Google Ads columns found")

    headers = [cell.strip() for cell in records[header_at]]
    preamble = [delimiter.join(cells).strip() for cells in records[:header_at]]
    rows = []
    for cells in records[header_at + 1:]:
        if not any(cell.strip() for cell in cells) or _is_total(cells):
            continue
        rows.append(dict(zip(headers, cells)))
    return headers, rows, preamble


_RANGE = re.compile(r"(.+?)\s+[-–—]\s+(.+)")


def preamble_range(preamble):
    """(start, end) ISO dates from a "September 1, 2026 - September 27, 2026" line."""

    preamble = [re.sub(r"\s+", " ", line).strip().strip('"') for line in preamble]
    for line in preamble:
        match = _RANGE.fullmatch(line)
        if not match:
            continue
        first, last = values.parse_date(match.group(1)), values.parse_date(match.group(2))
        if first and last:
            return first, last
    for line in preamble:
        single = values.parse_date(line)
        if single:
            return single, single
    return None


# ------------------------------------------------------------- detection --

FILENAME_HINTS = [
    ("search_terms", ("search_term", "search term", "searchterm")),
    ("conversions", ("conversion",)),
    ("locations", ("location", "geographic", "geo", "city", "cities")),
    ("ad_groups", ("ad_group", "ad group", "adgroup")),
    ("keywords", ("keyword",)),
    ("campaigns", ("campaign",)),
]


def detect_report(filename, headers):
    """Which of the six reports a file is, from its name first, then its columns."""

    name = filename.lower().replace("-", "_")
    if name.endswith((".csv", ".tsv", ".txt")):
        name = name.rsplit(".", 1)[0]
    for report, hints in FILENAME_HINTS:
        if any(hint in name for hint in hints):
            return report

    columns = {canonical(h) for h in headers} - {None}
    if "search_term" in columns:
        return "search_terms"
    if "conversion_action" in columns:
        return "conversions"
    if columns & {"city", "location_full", "region", "country"}:
        return "locations"
    if "keyword" in columns:
        return "keywords"
    if "ad_group" in columns:
        return "ad_groups"
    if "campaign" in columns:
        return "campaigns"
    return None


# ---------------------------------------------------------------- values --


def keyword_and_match(text):
    """("sell my house fast", "EXACT") from "[sell my house fast]"."""

    s = (text or "").strip()
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        return s[1:-1].strip(), "EXACT"
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].strip(), "PHRASE"
    if "+" in s and re.search(r"(^|\s)\+\S", s):
        return re.sub(r"(^|\s)\+", r"\1", s).strip(), "BROAD"
    return s, ""


def enum_value(text):
    s = header_key(text)
    return s.upper().replace(" ", "_") if s else ""


def match_value(text):
    s = header_key(text)
    if not s:
        return ""
    return MATCH_TYPES.get(s) or enum_value(s).replace("_MATCH", "")


def split_location(text):
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[0], parts[-2], parts[-1]
    if len(parts) == 2:
        return "", parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], "", ""
    return "", "", ""


def normalize_rows(report, headers, raw_rows):
    columns = {}
    for header in headers:
        column = canonical(header, report)
        if column and column not in columns.values():
            columns[header] = column

    wanted = schema.COLUMNS[report]
    rows = []
    for raw in raw_rows:
        row = {column: "" for column in wanted}
        extra = {}
        for header, column in columns.items():
            cell = raw.get(header, "")
            cell = "" if cell is None else str(cell).strip()
            if column in schema.NUMERIC:
                value = values.parse_number(cell)
            elif column == "date":
                value = values.parse_date(cell)
            else:
                value = "" if cell == "--" else cell
            if column in row:
                row[column] = value
            else:
                extra[column] = value

        if report in ("search_terms", "keywords") and row.get("keyword"):
            text, implied = keyword_and_match(row["keyword"])
            row["keyword"] = text
            if implied and not row.get("match_type"):
                row["match_type"] = implied
        if "match_type" in row:
            row["match_type"] = match_value(row["match_type"])
        if "search_term_match_type" in row:
            row["search_term_match_type"] = match_value(row["search_term_match_type"])
        for column in ENUM_COLUMNS & set(row):
            row[column] = enum_value(row[column])
        if "location_type" in row:
            key = header_key(row["location_type"])
            row["location_type"] = LOCATION_TYPES.get(key, enum_value(key))
        if report == "locations":
            full = extra.get("location_full", "")
            if full and not row["city"]:
                row["city"], region, country = split_location(full)
                row["region"] = row["region"] or region
                row["country"] = row["country"] or country
            if not row["city"]:
                row["city"] = "(unknown)"

        if all(row.get(c) in ("", None) for c in wanted if c in DIMENSIONS):
            continue
        for column in wanted:
            if row[column] == "" and column in schema.NUMERIC:
                row[column] = None
        if "impressions" in row:
            values.add_ratios(row)
        rows.append(row)

    # A download split by day (or by conversion action) can also carry the
    # unsplit total row for each campaign. Keeping those would count the
    # same spend twice, so once any row is split, unsplit rows go.
    for column in ("date", "conversion_action"):
        if column in wanted and any(r.get(column) for r in rows):
            rows = [r for r in rows if r.get(column)]
    return rows


def load_file(path, report=None):
    """(report, rows, preamble_range) for one CSV / TSV file."""

    with open(path, "rb") as handle:
        text = decode(handle.read())
    headers, raw_rows, preamble = read_table(text)
    report = report or detect_report(os.path.basename(str(path)), headers)
    if report is None:
        raise ValueError(f"could not tell which report {path} is")
    return report, normalize_rows(report, headers, raw_rows), preamble_range(preamble)
