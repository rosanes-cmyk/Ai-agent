"""Synthetic THB-style data, for trying the pipeline before Google access exists.

Activity is simulated at the finest grain (day x search term x city x
conversion action) and then rolled up into each report, so the six reports
reconcile with each other the way Google's do. Every file is written under
exports/demo/ and stamped source=demo. None of it is real performance.
"""

import csv
import datetime
import math
import random
from collections import defaultdict

from . import schema

CITIES = [
    ("Oakland", 0.30), ("Hayward", 0.13), ("San Leandro", 0.10), ("Richmond", 0.09),
    ("Fremont", 0.09), ("Berkeley", 0.07), ("Castro Valley", 0.06), ("Alameda", 0.05),
    ("Union City", 0.05), ("San Lorenzo", 0.03), ("El Cerrito", 0.03),
]

EAST_BAY = "THB | Search | Sell House Fast | East Bay"
DISTRESSED = "THB | Search | Distressed & Inherited"
LOCAL = "THB | Search | Hayward & Fremont"

# campaign, ad group, city override, keywords:
#   (keyword, match type, impressions/day, CTR, CPC, conversion rate, search terms)
AD_GROUPS = [
    (EAST_BAY, "Sell My House Fast", None, [
        ("sell my house fast", "PHRASE", 55, 0.075, 21.0, 0.10,
         ["sell my house fast", "sell my house fast oakland", "sell my house fast for cash", "how to sell my house fast"]),
        ("sell my house fast oakland", "EXACT", 18, 0.11, 24.0, 0.14,
         ["sell my house fast oakland", "sell my house fast oakland ca"]),
        ("sell house fast east bay", "PHRASE", 9, 0.06, 19.0, 0.08,
         ["sell house fast east bay", "sell my house fast bay area"]),
    ]),
    (EAST_BAY, "Cash Home Buyers", None, [
        ("we buy houses", "PHRASE", 70, 0.055, 16.0, 0.07,
         ["we buy houses", "we buy houses oakland", "we buy ugly houses", "companies that buy houses"]),
        ("cash home buyers", "PHRASE", 40, 0.06, 18.0, 0.08,
         ["cash home buyers", "cash home buyers near me", "cash buyers for houses"]),
        ("cash for houses", "BROAD", 45, 0.035, 12.0, 0.03,
         ["cash for houses", "cash for houses near me", "house cash offer", "zillow cash offer"]),
    ]),
    (DISTRESSED, "Inherited / Probate", None, [
        ("sell inherited house", "PHRASE", 20, 0.08, 17.0, 0.12,
         ["sell inherited house", "how to sell an inherited house", "selling a house in probate california"]),
        ("probate home buyers", "PHRASE", 8, 0.09, 20.0, 0.13,
         ["probate home buyers", "probate real estate buyers"]),
    ]),
    (DISTRESSED, "As-Is / Repairs", None, [
        ("sell house as is", "PHRASE", 35, 0.06, 15.0, 0.07,
         ["sell house as is", "sell house as is oakland", "sell my house as is for cash"]),
        ("sell house that needs repairs", "BROAD", 25, 0.045, 13.0, 0.05,
         ["sell house that needs repairs", "sell house needing major repairs", "home repair loans"]),
    ]),
    (LOCAL, "Hayward", {"Hayward": 1.0}, [
        ("we buy houses hayward", "EXACT", 10, 0.10, 19.0, 0.12,
         ["we buy houses hayward", "we buy houses hayward ca"]),
        ("sell my house fast hayward", "PHRASE", 9, 0.09, 20.0, 0.11,
         ["sell my house fast hayward", "sell house fast hayward ca"]),
    ]),
    (LOCAL, "Fremont", {"Fremont": 1.0}, [
        ("we buy houses fremont", "EXACT", 8, 0.10, 21.0, 0.10,
         ["we buy houses fremont", "we buy houses fremont ca"]),
        ("sell house fast fremont", "PHRASE", 7, 0.08, 22.0, 0.09,
         ["sell house fast fremont", "sell my house fast fremont"]),
    ]),
]

# Search terms that attract clicks but not sellers: the kind of thing the
# search terms report exists to catch and add as negatives.
JUNK = {"we buy ugly houses", "zillow cash offer", "home repair loans", "how to sell my house fast",
        "how to sell an inherited house"}

ACTIONS = [
    ("Calls from ads", "PHONE_CALL_LEAD", 0.50),
    ("Website lead form", "SUBMIT_LEAD_FORM", 0.35),
    ("Website phone call", "PHONE_CALL_LEAD", 0.15),
]
LEAD_VALUE = 100.0


def _ids():
    campaigns = {name: str(21000000000 + i) for i, name in enumerate(dict.fromkeys(g[0] for g in AD_GROUPS), 1)}
    ad_groups = {(g[0], g[1]): str(131000000000 + i) for i, g in enumerate(AD_GROUPS, 1)}
    keywords, n = {}, 0
    for campaign, group, _, words in AD_GROUPS:
        for spec in words:
            n += 1
            keywords[(campaign, group, spec[0])] = str(395000000000 + n)
    return campaigns, ad_groups, keywords


def _poisson(rng, lam):
    if lam < 30:
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1
    return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))


def _pick(rng, weighted):
    total = sum(w for _, w in weighted)
    x = rng.random() * total
    for item, weight in weighted:
        x -= weight
        if x <= 0:
            return item
    return weighted[-1][0]


def _term_match(keyword, match, term):
    if term == keyword:
        return "EXACT"
    if match == "EXACT":
        return "NEAR_EXACT"
    if match == "PHRASE":
        return "PHRASE" if keyword in term else "NEAR_PHRASE"
    return "BROAD"


def simulate(start, end, seed=7):
    """Event-level simulation. Returns {cell_key: metrics} at the finest grain."""

    rng = random.Random(seed)
    cells = defaultdict(lambda: {"impressions": 0, "clicks": 0, "cost": 0.0, "conv": defaultdict(int)})
    day = start
    while day <= end:
        weekday_factor = 0.8 if day.weekday() >= 5 else 1.0
        for campaign, group, city_override, words in AD_GROUPS:
            for keyword, match, per_day, ctr, cpc, cvr, terms in words:
                term_weights = [(t, 3.0 if i == 0 else 1.0) for i, t in enumerate(terms)]
                for _ in range(_poisson(rng, per_day * weekday_factor)):
                    term = _pick(rng, term_weights)
                    if city_override:
                        weights = list(city_override.items())
                    else:
                        # People who name a city mostly live in (or own in) it.
                        weights = [(c, w * (5.0 if c.lower() in term else 1.0)) for c, w in CITIES]
                    city = _pick(rng, weights)
                    cell = cells[(day, campaign, group, keyword, match, term, city)]
                    cell["impressions"] += 1
                    junk = term in JUNK
                    if rng.random() < ctr * (1.2 if junk else 1.0):
                        cell["clicks"] += 1
                        cell["cost"] += cpc * rng.lognormvariate(0, 0.35)
                        if rng.random() < cvr * (0.1 if junk else 1.0):
                            cell["conv"][_pick(rng, [(a, a[2]) for a in ACTIONS])] += 1
        day += datetime.timedelta(days=1)
    return cells


def reports(start, end, seed=7):
    """The six canonical reports built from one simulation."""

    campaign_ids, group_ids, keyword_ids = _ids()
    cells = simulate(start, end, seed)
    grouped = {r: defaultdict(lambda: {"impressions": 0, "clicks": 0, "cost": 0.0, "conversions": 0.0}) for r in schema.REPORTS}
    conversions = defaultdict(float)

    for (day, campaign, group, keyword, match, term, city), m in cells.items():
        d = day.isoformat()
        conv = float(sum(m["conv"].values()))
        keys = {
            "search_terms": (d, campaign, group, keyword, match, term),
            "keywords": (d, campaign, group, keyword, match),
            "ad_groups": (d, campaign, group),
            "campaigns": (d, campaign),
            "locations": (d, campaign, group, city),
        }
        for report, key in keys.items():
            g = grouped[report][key]
            g["impressions"] += m["impressions"]
            g["clicks"] += m["clicks"]
            g["cost"] += m["cost"]
            g["conversions"] += conv
        for action, count in m["conv"].items():
            conversions[(d, campaign, action)] += count

    def perf(g):
        return {
            "impressions": g["impressions"], "clicks": g["clicks"], "cost": round(g["cost"], 2),
            "conversions": g["conversions"], "conversion_value": g["conversions"] * LEAD_VALUE,
            "currency": "USD",
        }

    out = {r: [] for r in schema.REPORTS}
    for (d, campaign, group, keyword, match, term), g in grouped["search_terms"].items():
        out["search_terms"].append({
            "date": d, "campaign_id": campaign_ids[campaign], "campaign": campaign,
            "ad_group_id": group_ids[(campaign, group)], "ad_group": group, "keyword": keyword,
            "match_type": match, "search_term": term, "search_term_match_type": _term_match(keyword, match, term),
            "search_term_status": "ADDED" if term == keyword else "NONE", **perf(g),
        })
    for (d, campaign, group, keyword, match), g in grouped["keywords"].items():
        out["keywords"].append({
            "date": d, "campaign_id": campaign_ids[campaign], "campaign": campaign,
            "ad_group_id": group_ids[(campaign, group)], "ad_group": group,
            "keyword_id": keyword_ids[(campaign, group, keyword)], "keyword": keyword, "match_type": match,
            "keyword_status": "ENABLED", **perf(g),
        })
    for (d, campaign, group), g in grouped["ad_groups"].items():
        out["ad_groups"].append({
            "date": d, "campaign_id": campaign_ids[campaign], "campaign": campaign,
            "ad_group_id": group_ids[(campaign, group)], "ad_group": group, "ad_group_status": "ENABLED", **perf(g),
        })
    share_rng = random.Random(seed + 1)
    for (d, campaign), g in grouped["campaigns"].items():
        share = share_rng.uniform(38, 62)
        budget = share_rng.uniform(8, 30)
        out["campaigns"].append({
            "date": d, "campaign_id": campaign_ids[campaign], "campaign": campaign, "campaign_status": "ENABLED",
            "channel_type": "SEARCH", **perf(g), "search_impr_share_pct": share,
            "search_lost_is_budget_pct": budget, "search_lost_is_rank_pct": 100 - share - budget,
        })
    for (d, campaign, group, city), g in grouped["locations"].items():
        out["locations"].append({
            "date": d, "campaign_id": campaign_ids[campaign], "campaign": campaign,
            "ad_group_id": group_ids[(campaign, group)], "ad_group": group, "city": city,
            "region": "California", "country": "United States", "location_type": "LOCATION_OF_PRESENCE",
            "geo_target_id": "", **perf(g),
        })
    for (d, campaign, action), count in conversions.items():
        name, category, _ = action
        out["conversions"].append({
            "date": d, "campaign_id": campaign_ids[campaign], "campaign": campaign, "conversion_action": name,
            "conversion_category": category, "conversions": count, "conversion_value": count * LEAD_VALUE,
            "all_conversions": count, "all_conversion_value": count * LEAD_VALUE, "currency": "USD",
        })
    return out, cells


def write_demo_outcomes(path, cells, seed=11):
    """A demo lead_outcomes.csv: every simulated conversion becomes a lead
    that moves down a typical seller funnel. About a third are phone leads
    whose keyword nobody recorded, as happens in practice."""

    rng = random.Random(seed)
    rows, n = [], 0
    for (day, campaign, group, keyword, match, term, city), m in sorted(cells.items(), key=lambda kv: kv[0]):
        for (action, category, _), count in m["conv"].items():
            for _ in range(count):
                n += 1
                qualified = rng.random() < 0.45
                appointment = qualified and rng.random() < 0.55
                offer = appointment and rng.random() < 0.7
                contract = offer and rng.random() < 0.3
                closed = contract and rng.random() < 0.8
                phone_unknown = category == "PHONE_CALL_LEAD" and rng.random() < 0.5
                rows.append({
                    "lead_date": day.isoformat(), "lead_id": f"DEMO-{n:04d}", "campaign": campaign,
                    "ad_group": "" if phone_unknown else group, "keyword": "" if phone_unknown else keyword,
                    "search_term": "" if phone_unknown else term, "city": city, "gclid": "",
                    "qualified_lead": "yes" if qualified else "no", "appointment": "yes" if appointment else "no",
                    "offer": "yes" if offer else "no", "contract": "yes" if contract else "no",
                    "closed_deal": "yes" if closed else "no",
                    "profit": f"{rng.uniform(14000, 42000):.0f}" if closed else "",
                    "notes": "synthetic demo lead",
                })
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=schema.LEAD_OUTCOME_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
