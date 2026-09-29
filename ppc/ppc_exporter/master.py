"""Everything written once the six reports are in hand.

  <report>.csv                  the six canonical reports
  ppc_master_data.csv           every row of every report, stacked, for AI analysis
  keyword_city_performance.csv  Keyword + City + Spend + Clicks + Conversions,
                                with the lead-outcome columns joined on
  data_dictionary.md            what every column means
  manifest.json                 what ran, row counts, totals, warnings

Google Ads never reports keyword and city together: keyword reports have
no location, and location reports have no keyword. keyword_city splits each
keyword's numbers across the cities its ad group actually served, in
proportion to that ad group's city mix, and labels every row with how its
city was decided (city_method). Keyword totals are always Google's own.
"""

import csv
import datetime
import io
import json
import os
import re
import shutil
from collections import defaultdict

from . import normalize, schema, values
from .settings import PPC_DIR

BASE = ("impressions", "clicks", "cost", "conversions", "conversion_value")
OUTCOMES_FILE = "lead_outcomes.csv"
OUTCOMES_TEMPLATE = PPC_DIR / "lead_outcomes_template.csv"
UNKNOWN_KEYWORD = "(unknown keyword)"
NO_LOCATION = "(no location data)"


# ---------------------------------------------------------------- reports --


def _sort_key(row):
    return (
        row.get("date") or "",
        row.get("campaign") or "",
        row.get("ad_group") or "",
        -(row.get("cost") or row.get("conversions") or 0),
        row.get("keyword") or "",
        row.get("search_term") or "",
        row.get("city") or "",
        row.get("conversion_action") or "",
    )


# Zero-width and text-direction marks. Google's own location names carry
# some ("Nabeul\u200e"); they are invisible but make equal names unequal.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\ufeff"))


def finalize(report, rows):
    """Exactly the report's columns, ratios recomputed, in a stable order."""

    columns = schema.COLUMNS[report]
    clean_rows = []
    for row in rows:
        clean = {}
        for column in columns:
            value = row.get(column)
            if column in schema.NUMERIC:
                clean[column] = values.parse_number(value) if isinstance(value, str) else value
                # Money and (fractional, data-driven) conversions are kept to
                # two decimals, as the CSV shows them, so every total
                # (manifest, console, a rebuild, Excel's own SUM) is the same
                # number. Impression-billed rows carry sub-cent costs that
                # would otherwise make them differ by a few dollars a year.
                if column in (schema.MONEY | schema.DECIMAL) and clean[column] is not None:
                    clean[column] = round(clean[column], 2)
            else:
                clean[column] = "" if value is None else str(value).translate(_INVISIBLE).strip()
        if "impressions" in clean:
            values.add_ratios(clean)
        clean_rows.append(clean)
    clean_rows.sort(key=_sort_key)
    return clean_rows


def total(rows, metric):
    return sum(row.get(metric) or 0 for row in rows)


# ----------------------------------------------------------- lead outcomes --

_OUTCOME_ALIASES = {
    normalize.header_key(c): c for c in schema.LEAD_OUTCOME_COLUMNS
}
_OUTCOME_ALIASES.update(
    {
        "date": "lead_date",
        "lead created": "lead_date",
        "id": "lead_id",
        "qualified": "qualified_lead",
        "qualified leads": "qualified_lead",
        "appointments": "appointment",
        "appt": "appointment",
        "appointment set": "appointment",
        "offers": "offer",
        "offer made": "offer",
        "contracts": "contract",
        "under contract": "contract",
        "closed": "closed_deal",
        "closed deals": "closed_deal",
        "deal closed": "closed_deal",
        "profit usd": "profit",
        "net profit": "profit",
        "location": "city",
        "property city": "city",
        "email address": "email",
        "phone number": "phone",
        "seller phone": "phone",
        "reason": "not_qualified_reason",
        "not qualified reason": "not_qualified_reason",
        "disqualification reason": "not_qualified_reason",
        "lost reason": "not_qualified_reason",
    }
)


def ensure_outcomes_file(root):
    """exports/lead_outcomes.csv, created from the template the first time."""

    path = root / OUTCOMES_FILE
    if not path.exists():
        os.makedirs(root, exist_ok=True)
        shutil.copyfile(OUTCOMES_TEMPLATE, path)
    return path


def read_outcome_rows(path):
    """Every real lead row in a lead-outcomes file, with dates and flags parsed.

    Example rows and empty rows are left out; nothing is filtered by date.
    """

    if not path or not os.path.exists(path):
        return []

    # Excel's plain "CSV" is Windows-1252, "CSV UTF-8" has a BOM, Sheets is UTF-8.
    with open(path, "rb") as handle:
        text = normalize.decode(handle.read())
    reader = csv.DictReader(io.StringIO(text, newline=""))
    mapping = {h: _OUTCOME_ALIASES.get(normalize.header_key(h)) for h in reader.fieldnames or []}

    leads = []
    for raw in reader:
        lead = {column: "" for column in schema.LEAD_OUTCOME_COLUMNS}
        for header, column in mapping.items():
            if column:
                lead[column] = (raw.get(header) or "").strip()
        if lead["lead_id"].upper().startswith("EXAMPLE"):
            continue
        if not any(lead[c] for c in schema.LEAD_OUTCOME_COLUMNS if c != "notes"):
            continue
        lead["lead_date"] = values.parse_date(lead["lead_date"])
        for flag in schema.OUTCOME_FLAGS:
            lead[flag] = values.parse_flag(lead[flag]) or 0
        lead["profit"] = values.parse_number(lead["profit"])
        leads.append(lead)
    return leads


def load_outcomes(path, start, end):
    """(leads in range, warnings). Example rows and undated rows are left out."""

    warnings = []
    leads, undated, outside = [], 0, 0
    first, last = start.isoformat(), end.isoformat()
    for lead in read_outcome_rows(path):
        if not lead["lead_date"]:
            undated += 1
            continue
        if not first <= lead["lead_date"] <= last:
            outside += 1
            continue
        leads.append(lead)

    if undated:
        warnings.append(
            f"{undated} lead(s) in {path} have no lead_date and were left out. "
            "Fill in the date the lead first came in."
        )
    if outside:
        warnings.append(
            f"{outside} lead(s) fall outside {first}..{last} and belong to other date ranges."
        )
    return leads, warnings


# ------------------------------------------------------------ master file --


def master_rows(reports, start, end, source, leads=()):
    empty = {c: (None if c in schema.NUMERIC else "") for c in schema.MASTER_COLUMNS}
    rows = []
    for report in schema.REPORTS:
        for row in reports.get(report, []):
            stacked = dict(empty)
            stacked.update({k: v for k, v in row.items() if k in stacked})
            stacked.update(
                report=report,
                range_start=start.isoformat(),
                range_end=end.isoformat(),
                source=source,
            )
            rows.append(stacked)

    for lead in leads:
        stacked = dict(empty)
        stacked.update(
            report="lead_outcomes",
            range_start=start.isoformat(),
            range_end=end.isoformat(),
            date=lead["lead_date"],
            campaign=lead["campaign"],
            ad_group=lead["ad_group"],
            keyword=normalize.keyword_and_match(lead["keyword"])[0],
            search_term=lead["search_term"],
            city=lead["city"],
            lead_id=lead["lead_id"],
            source="lead_outcomes",
            profit=lead["profit"],
        )
        for flag, count in schema.OUTCOME_FLAGS.items():
            stacked[count] = lead[flag]
        rows.append(stacked)
    return rows


# --------------------------------------------------------- keyword x city --


def keyword_key(text):
    keyword = normalize.keyword_and_match(text or "")[0]
    return re.sub(r"\s+", " ", keyword.lower()).strip()


def city_key(text):
    return re.sub(r"\s+", " ", (text or "").split(",")[0].strip().lower())


def _keyword_rows(reports):
    """Keyword totals to split: the keywords report, else search terms."""

    rows = reports.get("keywords") or []
    if rows:
        return rows, "keywords"
    derived = [r for r in reports.get("search_terms") or [] if r.get("keyword")]
    return derived, "search_terms"


def keyword_city(reports, leads=(), outcomes_tracked=False):
    """(rows, stats) for keyword_city_performance.csv."""

    keyword_rows, keyword_source = _keyword_rows(reports)
    locations = reports.get("locations") or []
    level = "ad_group" if any(r.get("ad_group") for r in locations) else "campaign"

    def group_of(row):
        if level == "ad_group":
            return (row.get("campaign") or "", row.get("ad_group") or "")
        return (row.get("campaign") or "",)

    # Each ad group's (or campaign's) city mix.
    mix = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(BASE, 0.0)))
    region_of = {}
    for row in locations:
        city = row.get("city") or "(unknown)"
        place = mix[group_of(row)][city_key(city)]
        region_of.setdefault(city_key(city), (city, row.get("region") or ""))
        for metric in BASE:
            place[metric] += row.get(metric) or 0

    # Each keyword's totals, per group.
    keyword_totals = defaultdict(lambda: dict.fromkeys(BASE, 0.0))
    keyword_info = {}
    for row in keyword_rows:
        key = (group_of(row), keyword_key(row.get("keyword")))
        for metric in BASE:
            keyword_totals[key][metric] += row.get(metric) or 0
        info = keyword_info.setdefault(
            key, {"keyword": normalize.keyword_and_match(row.get("keyword"))[0], "match_types": set(), "campaigns": set(), "ad_groups": set()}
        )
        if row.get("match_type"):
            info["match_types"].add(row["match_type"])
        if row.get("campaign"):
            info["campaigns"].add(row["campaign"])
        if row.get("ad_group"):
            info["ad_groups"].add(row["ad_group"])

    def blank():
        return {
            "metrics": dict.fromkeys(BASE, 0.0),
            "methods": set(),
            "match_types": set(),
            "campaigns": set(),
            "ad_groups": set(),
            "outcomes": dict.fromkeys(schema.OUTCOME_FLAGS.values(), 0),
            "profit": None,
            "keyword": "",
            "city": "",
            "region": "",
        }

    cells = defaultdict(blank)
    exact_spend = 0.0
    for (group, word), metrics in keyword_totals.items():
        places = mix.get(group)
        if places:
            totals = {m: sum(p[m] for p in places.values()) for m in BASE}
            method = "exact" if len(places) == 1 else "estimated"
            shares = []
            for place_key, place in places.items():
                share = {m: (place[m] / totals[m] if totals[m] > 0 else None) for m in BASE}
                fallback = next(
                    (share[m] for m in ("cost", "clicks", "impressions") if share[m] is not None),
                    1 / len(places),
                )
                shares.append((place_key, {m: fallback if s is None else s for m, s in share.items()}))
        else:
            method = "no location data"
            shares = [(city_key(NO_LOCATION), dict.fromkeys(BASE, 1.0))]
            region_of.setdefault(city_key(NO_LOCATION), (NO_LOCATION, ""))

        info = keyword_info[(group, word)]
        for place_key, share in shares:
            cell = cells[(word or city_key(UNKNOWN_KEYWORD), place_key)]
            for metric in BASE:
                cell["metrics"][metric] += metrics[metric] * share[metric]
            if method == "exact":
                exact_spend += metrics["cost"] * share["cost"]
            cell["methods"].add(method)
            cell["match_types"] |= info["match_types"]
            cell["campaigns"] |= info["campaigns"]
            cell["ad_groups"] |= info["ad_groups"]
            cell["keyword"] = cell["keyword"] or info["keyword"] or UNKNOWN_KEYWORD
            city, region = region_of.get(place_key, (place_key, ""))
            cell["city"], cell["region"] = city, region

    for lead in leads:
        word = keyword_key(lead["keyword"]) or city_key(UNKNOWN_KEYWORD)
        place_key = city_key(lead["city"]) or "(unknown)"
        cell = cells[(word, place_key)]
        if not cell["methods"]:
            cell["methods"].add("outcomes only")
            cell["keyword"] = normalize.keyword_and_match(lead["keyword"])[0] or UNKNOWN_KEYWORD
            known = region_of.get(place_key)
            cell["city"] = known[0] if known else (lead["city"].split(",")[0].strip() or "(unknown)")
            cell["region"] = known[1] if known else ""
        if lead["campaign"]:
            cell["campaigns"].add(lead["campaign"])
        for flag, count in schema.OUTCOME_FLAGS.items():
            cell["outcomes"][count] += lead[flag]
        if lead["profit"] is not None:
            cell["profit"] = (cell["profit"] or 0) + lead["profit"]

    keyword_spend = defaultdict(float)
    for (word, _), cell in cells.items():
        keyword_spend[word] += cell["metrics"]["cost"]

    currency = next((r.get("currency") for r in keyword_rows if r.get("currency")), "")
    rows = []
    for (word, _), cell in cells.items():
        m = cell["metrics"]
        methods = cell["methods"] - {"outcomes only"} or cell["methods"]
        if methods == {"exact"}:
            method = "exact"
        elif len(methods) == 1:
            method = next(iter(methods))
        else:
            method = "estimated"

        row = {
            "keyword": cell["keyword"],
            "city": cell["city"],
            "region": cell["region"],
            "spend": m["cost"],
            "clicks": m["clicks"],
            "conversions": m["conversions"],
            "impressions": m["impressions"],
            "conversion_value": m["conversion_value"],
            "share_of_keyword_spend_pct": values.pct(m["cost"], keyword_spend[word]),
            "city_method": method,
            "match_types": "; ".join(sorted(cell["match_types"])),
            "campaigns": "; ".join(sorted(cell["campaigns"])),
            "ad_groups": "; ".join(sorted(cell["ad_groups"])),
            "currency": currency,
        }
        ratios = values.add_ratios({"impressions": m["impressions"], "clicks": m["clicks"], "cost": m["cost"], "conversions": m["conversions"]})
        for column in ("ctr_pct", "avg_cpc", "conv_rate_pct", "cost_per_conversion"):
            row[column] = ratios.get(column)

        if outcomes_tracked:
            for count in schema.OUTCOME_FLAGS.values():
                row[count] = cell["outcomes"][count]
            row["profit"] = cell["profit"] if cell["profit"] is not None else 0.0
            for count, cost_column in zip(schema.OUTCOME_FLAGS.values(), schema.FUNNEL_COSTS):
                # A row with no spend of its own (leads whose keyword nobody
                # recorded) has no cost per lead: its spend sits on other rows.
                row[cost_column] = values.safe_div(m["cost"], row[count]) if m["cost"] > 0 else None
            row["profit_minus_spend"] = row["profit"] - m["cost"]
            row["roi_pct"] = values.pct(row["profit"] - m["cost"], m["cost"])
        rows.append(row)

    rows.sort(key=lambda r: (-(r["spend"] or 0), -(r["conversions"] or 0), r["keyword"], r["city"]))

    spend = sum(r["spend"] or 0 for r in rows)
    stats = {
        "keyword_source": keyword_source,
        "location_level": level if locations else None,
        "keyword_spend": total(keyword_rows, "cost"),
        "keyword_city_spend": spend,
        "exact_city_spend_pct": values.pct(exact_spend, spend),
        "rows": len(rows),
    }
    return rows, stats


# ------------------------------------------------------------ dictionary --

FILE_NOTES = {
    "search_terms": "One row per day x campaign x ad group x keyword x search term: what people actually typed.",
    "keywords": "One row per day x campaign x ad group x keyword.",
    "campaigns": "One row per day x campaign. The full account spend lives here.",
    "ad_groups": "One row per day x campaign x ad group.",
    "locations": "One row per day x campaign x ad group x city (Google's matched location).",
    "conversions": "One row per day x campaign x conversion action. Google does not report clicks or cost per conversion action.",
}


def dictionary_markdown(manifest):
    out = [
        "# PPC export data dictionary",
        "",
        f"Date range: {manifest['date_range']['start']} to {manifest['date_range']['end']}"
        f" | Source: {manifest['source']} | Currency: {manifest.get('account', {}).get('currency') or 'see currency column'}",
        "",
    ]
    if manifest["source"] == "demo":
        out += ["**DEMO DATA. Every number in these files is synthetic. Do not analyse it as real results.**", ""]
    out += [
        "## How to read these files",
        "",
        "- `ppc_master_data.csv` stacks every report. **Filter on `report` before adding anything up**: "
        "each report is a different cut of the same spend, so summing across reports double counts.",
        "- `keyword_city_performance.csv` answers Keyword + City + Spend + Clicks + Conversions. Google never reports "
        "keyword and city together, so `city_method` says how each row's city was decided. Estimated rows split a "
        "keyword's clicks across cities, so clicks and impressions there carry decimals; they still add up to "
        "Google's keyword totals.",
        "- Ratios (CTR, CPC, conversion rate, cost per conversion) are recomputed from the base numbers, "
        "so re-derive them after grouping rather than averaging them.",
        "- Lead outcomes come from `exports/lead_outcomes.csv` (one row per lead). Blank outcome columns mean "
        "outcomes are not being tracked yet, not zero.",
        "- Leads whose keyword nobody recorded (common for phone calls) sit on `(unknown keyword)` rows in their "
        "city, with no spend of their own. For cost per lead by city, add up spend and leads across every row "
        "for that city.",
        "",
    ]
    files = [(schema.FILENAMES[r], FILE_NOTES[r], schema.COLUMNS[r]) for r in schema.REPORTS]
    files.append(("ppc_master_data.csv", "All reports stacked, plus lead_outcomes rows.", schema.MASTER_COLUMNS))
    files.append(("keyword_city_performance.csv", "Keyword x city rollup with lead outcomes.", schema.KEYWORD_CITY_COLUMNS))
    for name, note, columns in files:
        out += [f"## {name}", "", note, "", "| column | meaning |", "|---|---|"]
        for column in columns:
            out.append(f"| `{column}` | {schema.DESCRIPTIONS.get(column, '')} |")
        out.append("")
    return "\n".join(out)


# ----------------------------------------------------------------- write --


def write_bundle(folder, reports, *, start, end, source, meta=None, outcomes_path=None, log=print):
    """Write every output file into folder. Returns the manifest."""

    meta = meta or {}
    os.makedirs(folder, exist_ok=True)
    reports = {r: finalize(r, reports.get(r) or []) for r in schema.REPORTS}

    leads, warnings = load_outcomes(outcomes_path, start, end)
    tracked = bool(leads)
    for message in warnings:
        log("  Note: " + message)

    files = {}
    for report in schema.REPORTS:
        values.write_csv(os.path.join(folder, schema.FILENAMES[report]), schema.COLUMNS[report], reports[report])
        files[schema.FILENAMES[report]] = len(reports[report])

    stacked = master_rows(reports, start, end, source, leads)
    values.write_csv(os.path.join(folder, "ppc_master_data.csv"), schema.MASTER_COLUMNS, stacked)
    files["ppc_master_data.csv"] = len(stacked)

    rollup, stats = keyword_city(reports, leads, tracked)
    values.write_csv(
        os.path.join(folder, "keyword_city_performance.csv"),
        schema.KEYWORD_CITY_COLUMNS,
        rollup,
        fractional=("clicks", "impressions"),
    )
    files["keyword_city_performance.csv"] = len(rollup)

    report_meta = meta.get("reports", {})
    all_warnings = list(meta.get("warnings", [])) + warnings
    for report in schema.REPORTS:
        info = report_meta.setdefault(report, {})
        info["rows"] = len(reports[report])
        info.setdefault("status", "ok" if reports[report] else "empty")
        if not reports[report] and info["status"] != "failed":
            all_warnings.append(f"{schema.FILENAMES[report]} has no rows for this date range.")
        if info["status"] == "failed":
            all_warnings.append(f"{schema.FILENAMES[report]} FAILED: " + " | ".join(info.get("errors", [])))

    totals = {
        "campaigns_cost": total(reports["campaigns"], "cost"),
        "ad_groups_cost": total(reports["ad_groups"], "cost"),
        "keywords_cost": total(reports["keywords"], "cost"),
        "search_terms_cost": total(reports["search_terms"], "cost"),
        "locations_cost": total(reports["locations"], "cost"),
        "campaigns_clicks": total(reports["campaigns"], "clicks"),
        "campaigns_conversions": total(reports["campaigns"], "conversions"),
        "keyword_city_spend": stats["keyword_city_spend"],
        "exact_city_spend_pct": stats["exact_city_spend_pct"],
    }
    if totals["campaigns_cost"] and totals["keywords_cost"] < totals["campaigns_cost"] * 0.98:
        gap = totals["campaigns_cost"] - totals["keywords_cost"]
        all_warnings.append(
            f"{gap:,.2f} of campaign spend has no keyword (e.g. Performance Max or Display), "
            "so it appears in campaigns.csv but not in keyword_city_performance.csv."
        )

    account = dict(meta.get("account") or {})
    if not account.get("currency"):
        found = next((r["currency"] for rows in reports.values() for r in rows if r.get("currency")), "")
        if found:
            account["currency"] = found

    manifest = {
        "created_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "account": account,
        "files": files,
        "reports": report_meta,
        "keyword_city": stats,
        "totals": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in totals.items()},
        "lead_outcomes": {
            "file": str(outcomes_path) if outcomes_path else None,
            "leads_in_range": len(leads),
            "tracked": tracked,
        },
        "warnings": all_warnings,
    }
    if meta.get("notes"):
        manifest["notes"] = meta["notes"]

    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with open(os.path.join(folder, "data_dictionary.md"), "w", encoding="utf-8") as handle:
        handle.write(dictionary_markdown(manifest))
    return manifest


def read_bundle(folder):
    """The six canonical reports back from a folder this tool wrote."""

    reports = {}
    for report in schema.REPORTS:
        path = os.path.join(folder, schema.FILENAMES[report])
        reports[report] = values.read_csv(path) if os.path.exists(path) else []
    return reports
