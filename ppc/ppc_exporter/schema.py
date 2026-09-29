"""The canonical columns every export file uses, whatever the source.

API rows, browser downloads and manual imports are all mapped onto these
names before anything is written. That is what lets every CSV from every
source share one header, and what lets the master file stack them.
"""

REPORTS = (
    "search_terms",
    "keywords",
    "campaigns",
    "ad_groups",
    "locations",
    "conversions",
)

FILENAMES = {report: report + ".csv" for report in REPORTS}

TITLES = {
    "search_terms": "Search terms",
    "keywords": "Search keywords",
    "campaigns": "Campaign performance",
    "ad_groups": "Ad group performance",
    "locations": "Geographic / city performance",
    "conversions": "Conversion performance (by conversion action)",
}

# The five numbers Google reports, plus the four ratios derived from them.
# The ratios are always recomputed from the base numbers (see
# metrics.add_ratios) so they agree across sources and stay correct when
# rows are summed.
PERFORMANCE = [
    "impressions",
    "clicks",
    "ctr_pct",
    "avg_cpc",
    "cost",
    "conversions",
    "conv_rate_pct",
    "cost_per_conversion",
    "conversion_value",
]

COLUMNS = {
    "search_terms": [
        "date",
        "campaign_id",
        "campaign",
        "ad_group_id",
        "ad_group",
        "keyword",
        "match_type",
        "search_term",
        "search_term_match_type",
        "search_term_status",
        *PERFORMANCE,
        "currency",
    ],
    "keywords": [
        "date",
        "campaign_id",
        "campaign",
        "ad_group_id",
        "ad_group",
        "keyword_id",
        "keyword",
        "match_type",
        "keyword_status",
        *PERFORMANCE,
        "currency",
    ],
    "campaigns": [
        "date",
        "campaign_id",
        "campaign",
        "campaign_status",
        "channel_type",
        *PERFORMANCE,
        "search_impr_share_pct",
        "search_lost_is_budget_pct",
        "search_lost_is_rank_pct",
        "currency",
    ],
    "ad_groups": [
        "date",
        "campaign_id",
        "campaign",
        "ad_group_id",
        "ad_group",
        "ad_group_status",
        *PERFORMANCE,
        "currency",
    ],
    "locations": [
        "date",
        "campaign_id",
        "campaign",
        "ad_group_id",
        "ad_group",
        "city",
        "region",
        "country",
        "location_type",
        "geo_target_id",
        *PERFORMANCE,
        "currency",
    ],
    "conversions": [
        "date",
        "campaign_id",
        "campaign",
        "conversion_action",
        "conversion_category",
        "conversions",
        "conversion_value",
        "all_conversions",
        "all_conversion_value",
        "currency",
    ],
}

# Business results the team adds later, from the CRM / Live Call Claims
# sheet. The columns exist from day one so nothing downstream has to change
# when they start being filled in.
OUTCOMES = [
    "qualified_leads",
    "appointments",
    "offers",
    "contracts",
    "closed_deals",
    "profit",
]

# One row per lead in exports/lead_outcomes.csv. The yes/no columns are
# summed into the OUTCOMES counts above.
OUTCOME_FLAGS = {
    "qualified_lead": "qualified_leads",
    "appointment": "appointments",
    "offer": "offers",
    "contract": "contracts",
    "closed_deal": "closed_deals",
}

# gclid / gbraid / wbraid, email and phone are what let a lead's statuses be
# sent back to Google (ppc/ppc_exporter/feedback.py). Email and phone are
# hashed before they leave the computer and never go into the master file.
LEAD_OUTCOME_COLUMNS = [
    "lead_date",
    "lead_id",
    "campaign",
    "ad_group",
    "keyword",
    "search_term",
    "city",
    "gclid",
    "gbraid",
    "wbraid",
    "email",
    "phone",
    "qualified_lead",
    "appointment",
    "offer",
    "contract",
    "closed_deal",
    "not_qualified_reason",
    "profit",
    "notes",
]

MASTER_COLUMNS = [
    "report",
    "range_start",
    "range_end",
    "date",
    "campaign_id",
    "campaign",
    "campaign_status",
    "channel_type",
    "ad_group_id",
    "ad_group",
    "ad_group_status",
    "keyword_id",
    "keyword",
    "match_type",
    "keyword_status",
    "search_term",
    "search_term_match_type",
    "search_term_status",
    "city",
    "region",
    "country",
    "location_type",
    "geo_target_id",
    "conversion_action",
    "conversion_category",
    *PERFORMANCE,
    "all_conversions",
    "all_conversion_value",
    "search_impr_share_pct",
    "search_lost_is_budget_pct",
    "search_lost_is_rank_pct",
    "currency",
    "source",
    "lead_id",
    *OUTCOMES,
]

FUNNEL_COSTS = [
    "cost_per_qualified_lead",
    "cost_per_appointment",
    "cost_per_offer",
    "cost_per_contract",
    "cost_per_closed_deal",
]

KEYWORD_CITY_COLUMNS = [
    "keyword",
    "city",
    "region",
    "spend",
    "clicks",
    "conversions",
    "impressions",
    "conversion_value",
    "ctr_pct",
    "avg_cpc",
    "conv_rate_pct",
    "cost_per_conversion",
    "share_of_keyword_spend_pct",
    "city_method",
    "match_types",
    "campaigns",
    "ad_groups",
    *OUTCOMES,
    *FUNNEL_COSTS,
    "profit_minus_spend",
    "roi_pct",
    "currency",
]

INTEGER = {
    "impressions",
    "clicks",
    "qualified_leads",
    "appointments",
    "offers",
    "contracts",
    "closed_deals",
}

MONEY = {
    "cost",
    "spend",
    "avg_cpc",
    "cost_per_conversion",
    "conversion_value",
    "all_conversion_value",
    "profit",
    "profit_minus_spend",
    *FUNNEL_COSTS,
}

DECIMAL = {"conversions", "all_conversions"}

PERCENT = {
    "ctr_pct",
    "conv_rate_pct",
    "search_impr_share_pct",
    "search_lost_is_budget_pct",
    "search_lost_is_rank_pct",
    "share_of_keyword_spend_pct",
    "roi_pct",
}

NUMERIC = INTEGER | MONEY | DECIMAL | PERCENT

DESCRIPTIONS = {
    "report": "Which export the row came from. Never add up numbers across different report values: each report is a different cut of the same spend.",
    "range_start": "First day of the export's date range (inclusive).",
    "range_end": "Last day of the export's date range (inclusive).",
    "date": "Day the activity happened (account time zone). Blank when the source was not split by day.",
    "campaign_id": "Google Ads campaign ID.",
    "campaign": "Campaign name.",
    "campaign_status": "ENABLED, PAUSED or REMOVED.",
    "channel_type": "Campaign type, e.g. SEARCH, PERFORMANCE_MAX, DISPLAY.",
    "ad_group_id": "Google Ads ad group ID.",
    "ad_group": "Ad group name.",
    "ad_group_status": "ENABLED, PAUSED or REMOVED.",
    "keyword_id": "Google Ads keyword (criterion) ID.",
    "keyword": "The keyword you bid on, without match-type punctuation.",
    "match_type": "Keyword match type: EXACT, PHRASE or BROAD.",
    "keyword_status": "ENABLED, PAUSED or REMOVED.",
    "search_term": "What the person actually typed into Google.",
    "search_term_match_type": "How the search term matched the keyword: EXACT, PHRASE, BROAD, NEAR_EXACT (close variant), NEAR_PHRASE (close variant).",
    "search_term_status": "Whether the search term was already added as a keyword or excluded as a negative: ADDED, EXCLUDED, ADDED_EXCLUDED, NONE.",
    "city": "City. In locations.csv this is Google's matched location; in keyword_city_performance.csv see city_method.",
    "region": "State / region of the city.",
    "country": "Country of the city.",
    "location_type": "LOCATION_OF_PRESENCE = the person was physically there. AREA_OF_INTEREST = they searched about that place from elsewhere.",
    "geo_target_id": "Google's ID for the location (geoTargetConstants/<id>).",
    "conversion_action": "Name of the conversion action (e.g. a call from an ad, a website form).",
    "conversion_category": "Conversion action category, e.g. PHONE_CALL_LEAD, SUBMIT_LEAD_FORM.",
    "impressions": "Times an ad was shown.",
    "clicks": "Clicks on ads.",
    "ctr_pct": "Click-through rate in percent: clicks / impressions x 100.",
    "avg_cpc": "Average cost per click: cost / clicks.",
    "cost": "Ad spend in the account currency.",
    "spend": "Ad spend in the account currency (same as Google's Cost).",
    "conversions": "Conversions as Google counts them (primary conversion actions). Can be fractional under data-driven attribution.",
    "conv_rate_pct": "Conversion rate in percent: conversions / clicks x 100.",
    "cost_per_conversion": "cost / conversions.",
    "conversion_value": "Total conversion value Google recorded.",
    "all_conversions": "All conversions, including secondary conversion actions.",
    "all_conversion_value": "Value of all conversions.",
    "search_impr_share_pct": "Search impression share in percent (impressions received / impressions eligible).",
    "search_lost_is_budget_pct": "Search impression share lost to budget, in percent.",
    "search_lost_is_rank_pct": "Search impression share lost to ad rank, in percent.",
    "currency": "Account currency code, e.g. USD.",
    "source": "api, browser, import or demo. demo rows are synthetic and must never be analysed as real results.",
    "lead_id": "Your CRM / sheet ID for the lead (lead_outcomes rows only).",
    "qualified_leads": "Qualified seller leads (from exports/lead_outcomes.csv).",
    "appointments": "Appointments set.",
    "offers": "Offers made.",
    "contracts": "Contracts signed.",
    "closed_deals": "Deals closed.",
    "profit": "Profit from closed deals, in the account currency.",
    "share_of_keyword_spend_pct": "This city's share of the keyword's total spend, in percent.",
    "city_method": "exact = every ad group behind this row served only this city, so the city split is Google's own number. estimated = the keyword's numbers were split across cities in proportion to its ad group's city mix (Google never reports keyword and city together). no location data = the ad group had no location rows. outcomes only = leads logged for a keyword/city with no ad spend in this range, including (unknown keyword) rows for leads whose keyword was not recorded.",
    "match_types": "Match types of the keyword that contributed to this row.",
    "campaigns": "Campaigns that contributed to this row.",
    "ad_groups": "Ad groups that contributed to this row.",
    "cost_per_qualified_lead": "spend / qualified_leads.",
    "cost_per_appointment": "spend / appointments.",
    "cost_per_offer": "spend / offers.",
    "cost_per_contract": "spend / contracts.",
    "cost_per_closed_deal": "spend / closed_deals.",
    "profit_minus_spend": "profit - spend.",
    "roi_pct": "Return on ad spend in percent: (profit - spend) / spend x 100.",
}
