"""Google Ads UI downloads, in the shapes the website actually produces."""

import pytest

from ppc_exporter import normalize, values

SEARCH_TERMS_UI = (
    "Search terms report\n"
    "September 1, 2026 - September 27, 2026\n"
    "Search term,Match type,Added/Excluded,Campaign,Ad group,Keyword,Currency code,Impr.,Clicks,CTR,Avg. CPC,Cost,Conversions,Cost / conv.,Conv. value\n"
    "sell my house fast oakland,Exact match,None,THB Search,Sell Fast,[sell my house fast oakland],USD,\"1,204\",87,7.23%,18.40,\"1,600.80\",9.00,177.87,0.00\n"
    "we buy houses,Phrase match (close variant),Added,THB Search,Cash,\"\"\"we buy houses\"\"\",USD,300,12,4.00%,15.00,180.00,--,--,--\n"
    "Total: Search terms,,,,,,,\"1,504\",99,6.58%,18.00,\"1,780.80\",9.00,197.87,0.00\n"
    "Total: Account,,,,,,,\"1,504\",99,6.58%,18.00,\"1,780.80\",9.00,197.87,0.00\n"
)


def test_ui_search_terms_download():
    headers, rows, preamble = normalize.read_table(SEARCH_TERMS_UI)
    assert normalize.preamble_range(preamble) == ("2026-09-01", "2026-09-27")
    assert len(rows) == 2  # both Total rows dropped
    parsed = normalize.normalize_rows("search_terms", headers, rows)
    first, second = parsed
    assert first["keyword"] == "sell my house fast oakland" and first["match_type"] == "EXACT"
    assert first["search_term_match_type"] == "EXACT"  # "Match type" means the term's match here
    assert first["impressions"] == 1204 and first["cost"] == pytest.approx(1600.80)
    assert first["ctr_pct"] == pytest.approx(87 / 1204 * 100)
    assert second["keyword"] == "we buy houses" and second["match_type"] == "PHRASE"
    assert second["search_term_match_type"] == "NEAR_PHRASE"
    assert second["search_term_status"] == "ADDED"
    assert second["conversions"] is None and second["cost_per_conversion"] is None


def test_excel_csv_is_utf16_tab_separated(tmp_path):
    text = (
        "Search keyword report\n"
        "Aug 29, 2026 - Sep 27, 2026\n"
        "Day\tSearch keyword\tSearch keyword match type\tCampaign\tAd group\tImpr.\tClicks\tCost\tConversions\n"
        "2026-09-01\tcash home buyers\tPhrase match\tTHB Search\tCash\t40\t3\t54.12\t1.00\n"
        "Sep 2, 2026\tcash home buyers\tPhrase match\tTHB Search\tCash\t35\t2\t33.00\t0.00\n"
        "Total: Account\t\t\t\t\t75\t5\t87.12\t1.00\n"
    )
    path = tmp_path / "Search keyword report.csv"
    path.write_bytes(text.encode("utf-16"))
    report, rows, found = normalize.load_file(path)
    assert report == "keywords"
    assert found == ("2026-08-29", "2026-09-27")
    assert [r["date"] for r in rows] == ["2026-09-01", "2026-09-02"]
    assert rows[0]["match_type"] == "PHRASE" and rows[0]["avg_cpc"] == pytest.approx(18.04)


def test_utf8_bom_locations_with_full_location_names(tmp_path):
    text = (
        "﻿Matched locations report\n"
        "\"September 1, 2026 - September 27, 2026\"\n"
        "Matched location,Location type,Campaign,Impr.,Clicks,Cost,Conversions\n"
        "\"Oakland, California, United States\",Location of presence,THB Search,500,30,600.00,3\n"
        "\"California, United States\",Area of interest,THB Search,50,2,40.00,0\n"
    )
    path = tmp_path / "locations.csv"
    path.write_bytes(text.encode("utf-8"))
    report, rows, found = normalize.load_file(path)
    assert report == "locations" and found == ("2026-09-01", "2026-09-27")
    oakland, state_only = rows
    assert (oakland["city"], oakland["region"], oakland["country"]) == ("Oakland", "California", "United States")
    assert oakland["location_type"] == "LOCATION_OF_PRESENCE"
    assert state_only["city"] == "(unknown)" and state_only["region"] == "California"
    assert state_only["location_type"] == "AREA_OF_INTEREST"


def test_day_segmented_download_drops_unsplit_subtotals():
    text = (
        "Campaign,Day,Impr.,Clicks,Cost\n"
        "THB Search,,300,20,400.00\n"  # the campaign's own total row
        "THB Search,2026-09-01,100,5,100.00\n"
        "THB Search,2026-09-02,200,15,300.00\n"
    )
    headers, rows, _ = normalize.read_table(text)
    parsed = normalize.normalize_rows("campaigns", headers, rows)
    assert [r["date"] for r in parsed] == ["2026-09-01", "2026-09-02"]
    assert sum(r["cost"] for r in parsed) == pytest.approx(400.0)


def test_conversion_action_segment():
    text = (
        "Campaign,Conversion action,Conversion category,Conversions,All conv.,All conv. value\n"
        "THB Search,,,5,6,600\n"
        "THB Search,Calls from ads,Phone call lead,3,3,300\n"
        "THB Search,Website lead form,Submit lead form,2,3,300\n"
    )
    headers, rows, _ = normalize.read_table(text)
    parsed = normalize.normalize_rows("conversions", headers, rows)
    assert [(r["conversion_action"], r["conversion_category"]) for r in parsed] == [
        ("Calls from ads", "PHONE_CALL_LEAD"), ("Website lead form", "SUBMIT_LEAD_FORM"),
    ]


@pytest.mark.parametrize(
    "filename, headers, expected",
    [
        ("Search terms report.csv", [], "search_terms"),
        ("Campaign report (2).csv", [], "campaigns"),
        ("Ad group report.csv", [], "ad_groups"),
        ("User locations report.csv", [], "locations"),
        ("Conversion action report.csv", [], "conversions"),
        ("download.csv", ["Search term", "Clicks"], "search_terms"),
        ("download.csv", ["City (User location)", "Clicks"], "locations"),
        ("download.csv", ["Keyword", "Clicks"], "keywords"),
        ("download.csv", ["Ad group", "Campaign", "Clicks"], "ad_groups"),
    ],
)
def test_detect_report(filename, headers, expected):
    assert normalize.detect_report(filename, headers) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("1,234.56", 1234.56), ("$1,234.56", 1234.56), ("5.23%", 5.23), ("--", None), ("", None),
     ("< 10%", 9.99), ("> 90%", 90.01), ("(12.00)", -12.0), (" 0.00 ", 0.0), ("USD 7", 7.0)],
)
def test_parse_number(text, expected):
    assert values.parse_number(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("[sell my house fast]", ("sell my house fast", "EXACT")),
     ('"we buy houses"', ("we buy houses", "PHRASE")),
     ("+cash +home +buyers", ("cash home buyers", "BROAD")),
     ("cash for houses", ("cash for houses", ""))],
)
def test_keyword_punctuation(text, expected):
    assert normalize.keyword_and_match(text) == expected


def test_dates_and_flags():
    assert values.parse_date("Sep 3, 2026") == "2026-09-03"
    assert values.parse_date("9/3/2026") == "2026-09-03"
    assert values.parse_date("Thursday, September 3, 2026") == "2026-09-03"
    assert values.parse_date("--") == ""
    assert [values.parse_flag(v) for v in ("yes", "Y", "1", "x", "no", "0", "", "2")] == [1, 1, 1, 1, 0, 0, None, 1]
