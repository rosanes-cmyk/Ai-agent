"""The API path, run against a fake GoogleAdsService that returns real v25 rows.

No network and no credentials: the fake service answers each query with
genuine GoogleAdsRow protos, so row reading, unit conversion, fallback
variants, city lookup and error translation are all exercised for real.
"""

import types

import pytest

from conftest import END, START

pytest.importorskip("google.ads.googleads.v25")

from google.ads.googleads.errors import GoogleAdsException  # noqa: E402
from google.ads.googleads.v25.enums.types import (  # noqa: E402
    advertising_channel_type,
    campaign_status,
    conversion_action_category,
    geo_targeting_type,
    keyword_match_type,
    search_term_match_type,
    search_term_targeting_status,
)
from google.ads.googleads.v25.errors.types import authorization_error, errors, query_error  # noqa: E402
from google.ads.googleads.v25.services.types.google_ads_service import GoogleAdsRow  # noqa: E402

from ppc_exporter import api_source, master, schema  # noqa: E402

EXACT = keyword_match_type.KeywordMatchTypeEnum.KeywordMatchType.EXACT
PHRASE = keyword_match_type.KeywordMatchTypeEnum.KeywordMatchType.PHRASE
NEAR_EXACT = search_term_match_type.SearchTermMatchTypeEnum.SearchTermMatchType.NEAR_EXACT
NONE_STATUS = search_term_targeting_status.SearchTermTargetingStatusEnum.SearchTermTargetingStatus.NONE
ENABLED = campaign_status.CampaignStatusEnum.CampaignStatus.ENABLED
SEARCH = advertising_channel_type.AdvertisingChannelTypeEnum.AdvertisingChannelType.SEARCH
PRESENCE = geo_targeting_type.GeoTargetingTypeEnum.GeoTargetingType.LOCATION_OF_PRESENCE
CALL = conversion_action_category.ConversionActionCategoryEnum.ConversionActionCategory.PHONE_CALL_LEAD

OAKLAND = "geoTargetConstants/1014221"
HAYWARD = "geoTargetConstants/1014015"

CAMPAIGN = {"id": 111, "name": "THB | Search | East Bay"}
GROUP = {"id": 222, "name": "Sell My House Fast"}


def metrics(impressions, clicks, cost, conversions=0.0, value=0.0, **extra):
    return {"impressions": impressions, "clicks": clicks, "cost_micros": int(cost * 1_000_000),
            "conversions": conversions, "conversions_value": value, **extra}


ROWS = {
    "customer": [GoogleAdsRow(customer={"id": 1234567890, "descriptive_name": "Twin Home Buyer",
                                        "currency_code": "USD", "time_zone": "America/Los_Angeles"})],
    "search_term_view": [
        GoogleAdsRow(segments={"date": "2026-09-01", "keyword": {"info": {"text": "sell my house fast", "match_type": PHRASE}},
                               "search_term_match_type": NEAR_EXACT},
                     campaign=CAMPAIGN, ad_group=GROUP,
                     search_term_view={"search_term": "sell my house fast oakland", "status": NONE_STATUS},
                     metrics=metrics(120, 9, 180.5, 1, 100)),
    ],
    "keyword_view": [
        GoogleAdsRow(segments={"date": "2026-09-01"}, campaign=CAMPAIGN, ad_group=GROUP,
                     ad_group_criterion={"criterion_id": 333, "keyword": {"text": "sell my house fast", "match_type": PHRASE},
                                         "status": 2},
                     metrics=metrics(300, 20, 400.0, 2, 200)),
        GoogleAdsRow(segments={"date": "2026-09-02"}, campaign=CAMPAIGN, ad_group=GROUP,
                     ad_group_criterion={"criterion_id": 444, "keyword": {"text": "we buy houses", "match_type": EXACT},
                                         "status": 2},
                     metrics=metrics(100, 5, 100.0)),
    ],
    "campaign": [
        GoogleAdsRow(segments={"date": "2026-09-01"},
                     campaign={**CAMPAIGN, "status": ENABLED, "advertising_channel_type": SEARCH},
                     metrics=metrics(400, 25, 500.0, 2, 200, search_impression_share=0.42,
                                     search_budget_lost_impression_share=0.2, search_rank_lost_impression_share=0.38)),
        GoogleAdsRow(segments={"date": "2026-09-02"},
                     campaign={**CAMPAIGN, "status": ENABLED, "advertising_channel_type": SEARCH},
                     metrics=metrics(10, 0, 0.0)),
    ],
    "ad_group": [
        GoogleAdsRow(segments={"date": "2026-09-01"}, campaign=CAMPAIGN, ad_group={**GROUP, "status": 2},
                     metrics=metrics(400, 25, 500.0, 2, 200)),
    ],
    "geographic_view": [
        GoogleAdsRow(segments={"date": "2026-09-01", "geo_target_city": OAKLAND}, campaign=CAMPAIGN, ad_group=GROUP,
                     geographic_view={"location_type": PRESENCE}, metrics=metrics(300, 15, 300.0, 2, 200)),
        GoogleAdsRow(segments={"date": "2026-09-01", "geo_target_city": HAYWARD}, campaign=CAMPAIGN, ad_group=GROUP,
                     geographic_view={"location_type": PRESENCE}, metrics=metrics(100, 10, 200.0)),
    ],
    "conversions": [
        GoogleAdsRow(segments={"date": "2026-09-01", "conversion_action_name": "Calls from ads",
                               "conversion_action_category": CALL},
                     campaign=CAMPAIGN, metrics={"conversions": 2, "conversions_value": 200,
                                                 "all_conversions": 3, "all_conversions_value": 250}),
    ],
    "geo_target_constant": [
        GoogleAdsRow(geo_target_constant={"resource_name": OAKLAND, "id": 1014221, "name": "Oakland",
                                          "canonical_name": "Oakland,California,United States", "country_code": "US"}),
        GoogleAdsRow(geo_target_constant={"resource_name": HAYWARD, "id": 1014015, "name": "Hayward",
                                          "canonical_name": "Hayward,California,United States", "country_code": "US"}),
    ],
}


def ads_exception(kind, enum_value, message="rejected"):
    failure = errors.GoogleAdsFailure(errors=[errors.GoogleAdsError(error_code=errors.ErrorCode(**{kind: enum_value}), message=message)])
    return GoogleAdsException(None, None, failure, "req-123")


class FakeService:
    def __init__(self, reject=None):
        self.reject = reject or (lambda query: None)
        self.queries = []
        self.validated = []

    def _rows(self, query):
        problem = self.reject(query)
        if problem:
            raise problem
        resource = query.split("FROM", 1)[1].split()[0]
        if resource == "campaign" and "conversion_action_name" in query:
            return ROWS["conversions"]
        return ROWS[resource]

    def search_stream(self, customer_id, query):
        assert customer_id == "1234567890"
        self.queries.append(query)
        return [types.SimpleNamespace(results=self._rows(query))]

    def search(self, request):
        assert request.validate_only is True
        self.validated.append(request.query)
        self._rows(request.query)
        return []


class FakeClient:
    def __init__(self, service):
        self.service = service

    def get_service(self, name):
        assert name == "GoogleAdsService"
        return self.service

    def get_type(self, name):
        return types.SimpleNamespace()


def settings_for(tmp_path):
    return {
        "customer_id": "123-456-7890",
        "api": {"json_key_file_path": "", "client_id": "a", "client_secret": "b", "refresh_token": "c",
                "login_customer_id": "", "developer_token": ""},
    }


def test_export_reads_every_report(monkeypatch, tmp_path):
    service = FakeService()
    monkeypatch.setattr(api_source, "build_client", lambda settings: FakeClient(service))
    reports, meta = api_source.export(settings_for(tmp_path), START, END, log=lambda *_: None)

    assert meta["account"] == {"customer_id": "1234567890", "name": "Twin Home Buyer", "currency": "USD",
                               "time_zone": "America/Los_Angeles"}
    term = reports["search_terms"][0]
    assert term["keyword"] == "sell my house fast" and term["match_type"] == "PHRASE"
    assert term["search_term"] == "sell my house fast oakland"
    assert term["search_term_match_type"] == "NEAR_EXACT" and term["search_term_status"] == "NONE"
    assert term["cost"] == pytest.approx(180.5) and term["currency"] == "USD"

    keyword = reports["keywords"][0]
    assert keyword["keyword_id"] == "333" and keyword["keyword_status"] == "ENABLED"

    campaigns = reports["campaigns"]
    assert campaigns[0]["search_impr_share_pct"] == pytest.approx(42.0)
    assert campaigns[0]["channel_type"] == "SEARCH"
    assert campaigns[1]["search_impr_share_pct"] is None  # unset, not 0 %

    cities = {r["city"]: r for r in reports["locations"]}
    assert set(cities) == {"Oakland", "Hayward"}
    assert cities["Oakland"]["region"] == "California" and cities["Oakland"]["country"] == "United States"
    assert cities["Oakland"]["geo_target_id"] == "1014221"
    assert cities["Oakland"]["location_type"] == "LOCATION_OF_PRESENCE"

    conversion = reports["conversions"][0]
    assert conversion["conversion_action"] == "Calls from ads"
    assert conversion["conversion_category"] == "PHONE_CALL_LEAD"
    assert conversion["all_conversions"] == 3

    assert all(info["status"] == "ok" and info["variant"] == 0 for info in meta["reports"].values())


def test_rejected_query_falls_back_to_smaller_variant(monkeypatch, tmp_path):
    rejected = query_error.QueryErrorEnum.QueryError.PROHIBITED_FIELD_COMBINATION_IN_SELECT_CLAUSE

    def reject(query):
        if "segments.keyword.info.text" in query:
            return ads_exception("query_error", rejected, "keyword segment not allowed")
        return None

    service = FakeService(reject)
    monkeypatch.setattr(api_source, "build_client", lambda settings: FakeClient(service))
    reports, meta = api_source.export(settings_for(tmp_path), START, END, log=lambda *_: None)

    info = meta["reports"]["search_terms"]
    assert info["status"] == "ok" and info["variant"] == 1
    assert "PROHIBITED_FIELD_COMBINATION_IN_SELECT_CLAUSE" in info["errors"][0]
    assert reports["search_terms"][0]["search_term"] == "sell my house fast oakland"
    assert reports["search_terms"][0].get("keyword", "") == ""


def test_test_access_project_stops_with_the_fix(monkeypatch, tmp_path):
    not_approved = authorization_error.AuthorizationErrorEnum.AuthorizationError.CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION

    def reject(query):
        return ads_exception("authorization_error", not_approved, "The project is not approved for production.")

    monkeypatch.setattr(api_source, "build_client", lambda settings: FakeClient(FakeService(reject)))
    with pytest.raises(api_source.ApiAccessError) as caught:
        api_source.export(settings_for(tmp_path), START, END, log=lambda *_: None)
    message = str(caught.value)
    assert "CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION" in message
    assert "Explorer" in message and "console.cloud.google.com/google/ads-apis/overview" in message
    assert "req-123" in message


def test_permission_denied_names_the_account(monkeypatch, tmp_path):
    denied = authorization_error.AuthorizationErrorEnum.AuthorizationError.USER_PERMISSION_DENIED
    monkeypatch.setattr(
        api_source, "build_client",
        lambda settings: FakeClient(FakeService(lambda q: ads_exception("authorization_error", denied))),
    )
    with pytest.raises(api_source.ApiAccessError) as caught:
        api_source.export(settings_for(tmp_path), START, END, log=lambda *_: None)
    assert "1234567890" in str(caught.value) and "Access and security" in str(caught.value)


def test_manager_account_as_customer_id_is_fatal(monkeypatch, tmp_path):
    manager = query_error.QueryErrorEnum.QueryError.REQUESTED_METRICS_FOR_MANAGER

    def reject(query):
        return ads_exception("query_error", manager) if "metrics." in query else None

    monkeypatch.setattr(api_source, "build_client", lambda settings: FakeClient(FakeService(reject)))
    with pytest.raises(api_source.ApiAccessError) as caught:
        api_source.export(settings_for(tmp_path), START, END, log=lambda *_: None)
    assert "manager (MCC) account" in str(caught.value)


def test_check_validates_every_query(monkeypatch, tmp_path):
    service = FakeService()
    monkeypatch.setattr(api_source, "build_client", lambda settings: FakeClient(service))
    account, results = api_source.check(settings_for(tmp_path), START, END, log=lambda *_: None)
    assert account["name"] == "Twin Home Buyer"
    assert [(r, ok) for r, _, ok, _ in results] == [(r, True) for r in schema.REPORTS]
    assert len(service.validated) == len(schema.REPORTS)


def test_api_rows_flow_into_the_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(api_source, "build_client", lambda settings: FakeClient(FakeService()))
    reports, meta = api_source.export(settings_for(tmp_path), START, END, log=lambda *_: None)
    manifest = master.write_bundle(str(tmp_path / "out"), reports, start=START, end=END, source="api", meta=meta,
                                   log=lambda *_: None)
    assert manifest["files"]["keywords.csv"] == 2
    assert manifest["totals"]["keywords_cost"] == pytest.approx(500.0)
    # 500 of keyword spend split 60/40 by the ad group's Oakland/Hayward cost mix.
    rows = {(r["keyword"], r["city"]): r for r in master.values.read_csv(tmp_path / "out" / "keyword_city_performance.csv")}
    assert rows[("sell my house fast", "Oakland")]["spend"] == pytest.approx(240.0)
    assert rows[("sell my house fast", "Hayward")]["spend"] == pytest.approx(160.0)
    assert rows[("sell my house fast", "Oakland")]["conversions"] == pytest.approx(2.0)  # all conversions were in Oakland
    assert rows[("sell my house fast", "Oakland")]["city_method"] == "estimated"


def test_missing_settings(blank_settings):
    assert len(api_source.missing_settings(blank_settings)) == 2
    blank_settings["customer_id"] = "123-456-7890"
    blank_settings["api"].update(client_id="x", client_secret="y")
    assert api_source.missing_settings(blank_settings) == ["OAuth credentials are incomplete, missing: refresh_token"]
    blank_settings["api"].update(refresh_token="z", login_customer_id="12")
    assert "login_customer_id" in api_source.missing_settings(blank_settings)[0]
    blank_settings["api"].update(login_customer_id="", json_key_file_path="/nope/key.json")
    assert "no file at /nope/key.json" in api_source.missing_settings(blank_settings)[0]


def test_refresh_errors_are_explained(blank_settings):
    class RefreshError(Exception):
        pass

    oauth = api_source.explain(RefreshError("invalid_grant: Token has been expired or revoked."), blank_settings)
    assert "7 days" in oauth and "refresh-token" in oauth
    blank_settings["api"]["json_key_file_path"] = "/k.json"
    key = api_source.explain(RefreshError("invalid_grant: Invalid grant: account not found"), blank_settings)
    assert "service-account key" in key
    client = api_source.explain(RefreshError("invalid_client: The OAuth client was not found."), blank_settings)
    assert "client_id / client_secret" in client
