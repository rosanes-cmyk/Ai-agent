"""Google Ads Query Language (GAQL) for the six reports.

Each report lists its fields once, as (column, GAQL field, conversion).
The SELECT clause is built from that list and API rows are read back with
the same list, so the query and the CSV columns cannot drift apart.

A report can carry fallback variants. If Google rejects the full query
(a field combination it no longer allows), the exporter retries with the
next, smaller variant instead of losing the whole report, and records in
the manifest which variant ran.
"""

from dataclasses import dataclass, field

TEXT = "text"
ID = "id"
INT = "int"
FLOAT = "float"
MICROS = "micros"  # money in millionths of the currency unit
RATIO = "ratio"  # 0.25 -> 25.0 percent
ENUM = "enum"
GEO = "geo"  # geoTargetConstants/<id>, resolved to a name after the query

PERFORMANCE_FIELDS = [
    ("impressions", "metrics.impressions", INT),
    ("clicks", "metrics.clicks", INT),
    ("cost", "metrics.cost_micros", MICROS),
    ("conversions", "metrics.conversions", FLOAT),
    ("conversion_value", "metrics.conversions_value", FLOAT),
]

DATE = ("date", "segments.date", TEXT)
CAMPAIGN = [
    ("campaign_id", "campaign.id", ID),
    ("campaign", "campaign.name", TEXT),
]
AD_GROUP = [
    ("ad_group_id", "ad_group.id", ID),
    ("ad_group", "ad_group.name", TEXT),
]


@dataclass
class Report:
    name: str
    resource: str
    variants: list = field(default_factory=list)

    @property
    def fields(self):
        return self.variants[0]


REPORT_QUERIES = {
    "search_terms": Report(
        "search_terms",
        "search_term_view",
        [
            [
                DATE,
                *CAMPAIGN,
                *AD_GROUP,
                ("keyword", "segments.keyword.info.text", TEXT),
                ("match_type", "segments.keyword.info.match_type", ENUM),
                ("search_term", "search_term_view.search_term", TEXT),
                ("search_term_match_type", "segments.search_term_match_type", ENUM),
                ("search_term_status", "search_term_view.status", ENUM),
                *PERFORMANCE_FIELDS,
            ],
            # Without the triggering-keyword segment.
            [
                DATE,
                *CAMPAIGN,
                *AD_GROUP,
                ("search_term", "search_term_view.search_term", TEXT),
                ("search_term_status", "search_term_view.status", ENUM),
                *PERFORMANCE_FIELDS,
            ],
        ],
    ),
    "keywords": Report(
        "keywords",
        "keyword_view",
        [
            [
                DATE,
                *CAMPAIGN,
                *AD_GROUP,
                ("keyword_id", "ad_group_criterion.criterion_id", ID),
                ("keyword", "ad_group_criterion.keyword.text", TEXT),
                ("match_type", "ad_group_criterion.keyword.match_type", ENUM),
                ("keyword_status", "ad_group_criterion.status", ENUM),
                *PERFORMANCE_FIELDS,
            ],
        ],
    ),
    "campaigns": Report(
        "campaigns",
        "campaign",
        [
            [
                DATE,
                *CAMPAIGN,
                ("campaign_status", "campaign.status", ENUM),
                ("channel_type", "campaign.advertising_channel_type", ENUM),
                *PERFORMANCE_FIELDS,
                ("search_impr_share_pct", "metrics.search_impression_share", RATIO),
                (
                    "search_lost_is_budget_pct",
                    "metrics.search_budget_lost_impression_share",
                    RATIO,
                ),
                (
                    "search_lost_is_rank_pct",
                    "metrics.search_rank_lost_impression_share",
                    RATIO,
                ),
            ],
            # Without impression share.
            [
                DATE,
                *CAMPAIGN,
                ("campaign_status", "campaign.status", ENUM),
                ("channel_type", "campaign.advertising_channel_type", ENUM),
                *PERFORMANCE_FIELDS,
            ],
        ],
    ),
    "ad_groups": Report(
        "ad_groups",
        "ad_group",
        [
            [
                DATE,
                *CAMPAIGN,
                *AD_GROUP,
                ("ad_group_status", "ad_group.status", ENUM),
                *PERFORMANCE_FIELDS,
            ],
        ],
    ),
    "locations": Report(
        "locations",
        "geographic_view",
        [
            [
                DATE,
                *CAMPAIGN,
                *AD_GROUP,
                ("location_type", "geographic_view.location_type", ENUM),
                ("geo_target_id", "segments.geo_target_city", GEO),
                *PERFORMANCE_FIELDS,
            ],
            # Campaign level only. keyword_city_performance then splits by
            # the campaign's city mix instead of the ad group's.
            [
                DATE,
                *CAMPAIGN,
                ("location_type", "geographic_view.location_type", ENUM),
                ("geo_target_id", "segments.geo_target_city", GEO),
                *PERFORMANCE_FIELDS,
            ],
        ],
    ),
    "conversions": Report(
        "conversions",
        "campaign",
        [
            [
                DATE,
                *CAMPAIGN,
                ("conversion_action", "segments.conversion_action_name", TEXT),
                ("conversion_category", "segments.conversion_action_category", ENUM),
                ("conversions", "metrics.conversions", FLOAT),
                ("conversion_value", "metrics.conversions_value", FLOAT),
                ("all_conversions", "metrics.all_conversions", FLOAT),
                ("all_conversion_value", "metrics.all_conversions_value", FLOAT),
            ],
        ],
    ),
}

CUSTOMER_QUERY = (
    "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
    "customer.time_zone FROM customer LIMIT 1"
)

GEO_FIELDS = [
    "geo_target_constant.resource_name",
    "geo_target_constant.id",
    "geo_target_constant.name",
    "geo_target_constant.canonical_name",
    "geo_target_constant.target_type",
    "geo_target_constant.country_code",
]


def build_query(report, start, end, variant=0):
    """The GAQL for one report variant over [start, end], dates as YYYY-MM-DD."""

    fields = REPORT_QUERIES[report].variants[variant]
    select = ",\n  ".join(gaql for _, gaql, _ in fields)
    return (
        "SELECT\n  "
        + select
        + "\nFROM "
        + REPORT_QUERIES[report].resource
        + "\nWHERE segments.date BETWEEN '"
        + start
        + "' AND '"
        + end
        + "'"
    )


def geo_query(resource_names):
    quoted = ", ".join("'" + name + "'" for name in resource_names)
    return (
        "SELECT "
        + ", ".join(GEO_FIELDS)
        + " FROM geo_target_constant WHERE geo_target_constant.resource_name IN ("
        + quoted
        + ")"
    )
