"""Every GAQL field must exist in the API version the client library speaks.

This runs offline against the library's own proto definitions, so a typo in a
field name fails here instead of on the first real export.
"""

import pytest

from ppc_exporter import api_source, queries, schema

v25 = pytest.importorskip("google.ads.googleads.v25.services.types.google_ads_service")
ROW = v25.GoogleAdsRow.pb().DESCRIPTOR


def resolves(path):
    descriptor = ROW
    parts = path.split(".")
    for index, part in enumerate(parts):
        field = descriptor.fields_by_name.get(part)
        if field is None:
            return False
        if index < len(parts) - 1:
            if field.message_type is None:
                return False
            descriptor = field.message_type
    return True


@pytest.mark.parametrize("report", schema.REPORTS)
def test_every_field_exists_in_v25(report):
    definition = queries.REPORT_QUERIES[report]
    assert definition.resource in ROW.fields_by_name
    for variant in definition.variants:
        for column, path, _ in variant:
            assert resolves(path), f"{report}: {path} is not a v25 field"
            assert column in schema.COLUMNS[report], f"{report}: {column} is not an output column"


def test_geo_and_customer_fields_exist():
    for path in queries.GEO_FIELDS:
        assert resolves(path), path
    for path in ("customer.id", "customer.descriptive_name", "customer.currency_code", "customer.time_zone"):
        assert resolves(path), path


def test_query_has_date_filter_and_select():
    query = queries.build_query("keywords", "2026-08-29", "2026-09-27")
    assert query.startswith("SELECT\n  segments.date,")
    assert "FROM keyword_view" in query
    assert query.endswith("WHERE segments.date BETWEEN '2026-08-29' AND '2026-09-27'")


def test_fallback_variants_are_smaller():
    for report, definition in queries.REPORT_QUERIES.items():
        for bigger, smaller in zip(definition.variants, definition.variants[1:]):
            assert set(p for _, p, _ in smaller) < set(p for _, p, _ in bigger), report


def test_every_error_fix_names_a_real_v25_error():
    from google.ads.googleads.v25.errors.types import errors

    code = errors.ErrorCode.pb().DESCRIPTOR
    for kind, name in api_source.FIXES:
        field = code.fields_by_name.get(kind)
        assert field is not None, kind
        assert name in field.enum_type.values_by_name, f"{kind}.{name}"


def test_master_holds_every_report_column():
    for report, columns in schema.COLUMNS.items():
        assert set(columns) <= set(schema.MASTER_COLUMNS), report
