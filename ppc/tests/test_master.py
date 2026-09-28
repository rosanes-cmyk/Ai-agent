"""The master file, the Keyword + City rollup and the lead-outcome merge."""

import csv
import json
from collections import defaultdict

import pytest

from conftest import END, START
from ppc_exporter import demo, master, schema, values


@pytest.fixture(scope="module")
def demo_bundle(tmp_path_factory):
    folder = tmp_path_factory.mktemp("demo")
    reports, cells = demo.reports(START, END)
    outcomes = folder / "lead_outcomes.csv"
    leads = demo.write_demo_outcomes(outcomes, cells)
    manifest = master.write_bundle(str(folder / "out"), reports, start=START, end=END, source="demo",
                                   outcomes_path=outcomes, log=lambda *_: None)
    return folder / "out", manifest, cells, leads


def read(path):
    return values.read_csv(path)


def test_every_file_has_its_canonical_header(demo_bundle):
    out, manifest, _, _ = demo_bundle
    expected = {schema.FILENAMES[r]: schema.COLUMNS[r] for r in schema.REPORTS}
    expected["ppc_master_data.csv"] = schema.MASTER_COLUMNS
    expected["keyword_city_performance.csv"] = schema.KEYWORD_CITY_COLUMNS
    for name, columns in expected.items():
        with open(out / name, newline="", encoding="utf-8") as handle:
            assert next(csv.reader(handle)) == columns, name
    assert (out / "data_dictionary.md").read_text().startswith("# PPC export data dictionary")
    assert json.loads((out / "manifest.json").read_text())["source"] == "demo"


def test_master_stacks_every_report_and_the_leads(demo_bundle):
    out, manifest, _, leads = demo_bundle
    rows = read(out / "ppc_master_data.csv")
    counts = defaultdict(int)
    for row in rows:
        counts[row["report"]] += 1
        assert row["range_start"] == "2026-08-29" and row["range_end"] == "2026-09-27"
    for report in schema.REPORTS:
        assert counts[report] == manifest["files"][schema.FILENAMES[report]]
    assert counts["lead_outcomes"] == leads


def test_keyword_city_reconciles_to_keyword_totals(demo_bundle):
    out, manifest, _, _ = demo_bundle
    keywords = read(out / "keywords.csv")
    rollup = read(out / "keyword_city_performance.csv")
    for metric, column in (("cost", "spend"), ("clicks", "clicks"), ("conversions", "conversions"), ("impressions", "impressions")):
        assert sum(r[column] or 0 for r in rollup) == pytest.approx(sum(r[metric] or 0 for r in keywords), abs=0.05), metric

    by_keyword = defaultdict(float)
    for row in rollup:
        by_keyword[row["keyword"]] += row["share_of_keyword_spend_pct"] or 0
    for keyword, share in by_keyword.items():
        if keyword != "(unknown keyword)":
            assert share == pytest.approx(100, abs=0.05), keyword


def test_single_city_ad_groups_are_exact(demo_bundle):
    out, _, _, _ = demo_bundle
    rows = {(r["keyword"], r["city"]): r for r in read(out / "keyword_city_performance.csv")}
    hayward = rows[("we buy houses hayward", "Hayward")]
    assert hayward["city_method"] == "exact" and hayward["share_of_keyword_spend_pct"] == pytest.approx(100)
    assert rows[("sell my house fast", "Oakland")]["city_method"] == "estimated"


def test_estimate_is_close_to_the_simulated_truth_for_broad_keywords(demo_bundle):
    """The split is proportional to the ad group's city mix, so it tracks the
    real mix for keywords that do not name a city."""

    out, _, cells, _ = demo_bundle
    truth = defaultdict(float)
    for (_, _, _, keyword, _, _, city), m in cells.items():
        if keyword == "we buy houses":
            truth[city] += m["cost"]
    total = sum(truth.values())
    rows = [r for r in read(out / "keyword_city_performance.csv") if r["keyword"] == "we buy houses"]
    for row in rows:
        assert row["spend"] / total == pytest.approx(truth[row["city"]] / total, abs=0.08), row["city"]


def test_lead_outcomes_are_counted_once(demo_bundle):
    out, _, _, _ = demo_bundle
    with open(out.parent / "lead_outcomes.csv", newline="") as handle:
        leads = list(csv.DictReader(handle))
    rollup = read(out / "keyword_city_performance.csv")
    for flag, count in schema.OUTCOME_FLAGS.items():
        expected = sum(values.parse_flag(l[flag]) or 0 for l in leads)
        assert sum(r[count] or 0 for r in rollup) == expected, count
    expected_profit = sum(values.parse_number(l["profit"]) or 0 for l in leads)
    assert sum(r["profit"] or 0 for r in rollup) == pytest.approx(expected_profit)


def test_rows_without_spend_have_no_cost_per_lead(demo_bundle):
    out, _, _, _ = demo_bundle
    unknown = [r for r in read(out / "keyword_city_performance.csv") if r["keyword"] == "(unknown keyword)"]
    assert unknown, "demo leads include phone calls with no recorded keyword"
    for row in unknown:
        assert row["city_method"] == "outcomes only" and row["spend"] == 0
        assert all(row[c] is None for c in schema.FUNNEL_COSTS)
        assert row["roi_pct"] is None


def test_outcome_columns_blank_until_tracked(tmp_path):
    reports, _ = demo.reports(START, START)
    master.write_bundle(str(tmp_path), reports, start=START, end=START, source="demo", log=lambda *_: None)
    with open(tmp_path / "keyword_city_performance.csv", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert all(row[c] == "" for c in schema.OUTCOMES + schema.FUNNEL_COSTS)


def test_outcomes_file_rules(tmp_path):
    path = tmp_path / "lead_outcomes.csv"
    path.write_text(
        "Lead Date,Lead ID,Keyword,City,Qualified Lead,Appointment,Offer,Contract,Closed Deal,Profit ($)\n"
        "2026-09-15,EXAMPLE-1,sell my house fast,Oakland,yes,yes,yes,no,no,\n"
        "9/10/2026,L-1,[sell my house fast],\"Oakland, CA\",yes,yes,no,no,no,\n"
        "2026-09-12,L-2,,Hayward,y,n,n,n,n,\n"
        ",L-3,we buy houses,Oakland,yes,,,,,\n"
        "2026-07-01,L-4,we buy houses,Oakland,yes,,,,,\n"
        "2026-09-20,L-5,we buy houses,Oakland,yes,yes,yes,yes,yes,\"$31,500\"\n"
    )
    leads, warnings = master.load_outcomes(path, START, END)
    assert [l["lead_id"] for l in leads] == ["L-1", "L-2", "L-5"]
    assert leads[2]["profit"] == 31500 and leads[2]["closed_deal"] == 1
    assert any("no lead_date" in w for w in warnings) and any("outside" in w for w in warnings)

    rows, _ = master.keyword_city({"keywords": [], "locations": []}, leads, outcomes_tracked=True)
    keyed = {(r["keyword"], r["city"]): r for r in rows}
    assert keyed[("sell my house fast", "Oakland")]["qualified_leads"] == 1
    assert keyed[("(unknown keyword)", "Hayward")]["qualified_leads"] == 1
    assert keyed[("we buy houses", "Oakland")]["profit"] == 31500


def test_ensure_outcomes_file_copies_the_template(tmp_path):
    path = master.ensure_outcomes_file(tmp_path)
    with open(path, newline="") as handle:
        assert next(csv.reader(handle)) == schema.LEAD_OUTCOME_COLUMNS
    assert master.load_outcomes(path, START, END) == ([], [])  # the example row is ignored


def test_campaign_level_locations_still_split(tmp_path):
    keywords = [
        {"campaign": "C", "ad_group": "A", "keyword": "kw", "cost": 100.0, "clicks": 10, "impressions": 100, "conversions": 1.0},
    ]
    locations = [
        {"campaign": "C", "ad_group": "", "city": "Oakland", "cost": 75.0, "clicks": 5, "impressions": 60, "conversions": 1.0},
        {"campaign": "C", "ad_group": "", "city": "Fremont", "cost": 25.0, "clicks": 5, "impressions": 40, "conversions": 0.0},
    ]
    rows, stats = master.keyword_city({"keywords": keywords, "locations": locations})
    keyed = {r["city"]: r for r in rows}
    assert stats["location_level"] == "campaign"
    assert keyed["Oakland"]["spend"] == pytest.approx(75.0) and keyed["Fremont"]["clicks"] == pytest.approx(5.0)
    assert keyed["Oakland"]["conversions"] == pytest.approx(1.0)


def test_no_location_data_is_labelled(tmp_path):
    keywords = [{"campaign": "C", "ad_group": "A", "keyword": "kw", "cost": 50.0, "clicks": 2, "impressions": 20, "conversions": 0.0}]
    rows, _ = master.keyword_city({"keywords": keywords, "locations": []})
    assert rows[0]["city"] == "(no location data)" and rows[0]["city_method"] == "no location data"
    assert rows[0]["spend"] == 50.0


def test_outcomes_saved_by_excel_as_windows_1252(tmp_path):
    path = tmp_path / "lead_outcomes.csv"
    path.write_bytes(
        "lead_date,lead_id,keyword,city,qualified_lead,notes\n"
        "2026-09-10,L-9,we buy houses,Oakland,yes,Seller\u2019s aunt called\n".encode("cp1252")
    )
    leads, _ = master.load_outcomes(path, START, END)
    assert leads[0]["notes"] == "Seller\u2019s aunt called" and leads[0]["qualified_lead"] == 1
