"""A stand-in for the Google Ads website, for testing the browser fallback.

It reproduces only what the exporter relies on: the sign-in redirect, the
account query string, a date-range picker, the Segment menu, and a
Download > .csv menu that returns a file shaped like a real UI download
(title line, date-range line, "Total:" rows). It proves the plumbing works;
it cannot prove the real site's buttons still have the same names.
"""

import datetime
import html
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ACCOUNT_QUERY = "ocid=111&euid=222&__u=333&uscid=111&__c=444&authuser=0"

TITLES = {
    "overview": "Overview",
    "campaigns": "Campaigns",
    "adgroups": "Ad groups",
    "keywords": "Search keywords",
    "searchterms": "Search terms",
    "userlocations": "User locations",
}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title} - Google Ads (mock)</title></head>
<body>
<div id="account">Twin Home Buyer 123-456-7890</div>
<h1>{title}</h1>
<button id="date" aria-label="Date range">Last 7 days</button>
<div id="date-menu" role="menu" hidden>
  <div role="menuitem" data-range="last7">Last 7 days</div>
  <div role="menuitem" data-range="last14">Last 14 days</div>
  <div role="menuitem" data-range="last30">Last 30 days</div>
  <input aria-label="Start date"><input aria-label="End date"><button id="apply">Apply</button>
</div>
<button id="segment" aria-label="Segment">Segment</button>
<div id="seg-menu" role="menu" hidden>
  <div role="menuitem" data-next="seg-time">Time</div>
  <div role="menuitem" data-next="seg-conv">Conversions</div>
</div>
<div id="seg-time" role="menu" hidden><div role="menuitem" data-seg="day">Day</div><div role="menuitem" data-seg="week">Week</div></div>
<div id="seg-conv" role="menu" hidden><div role="menuitem" data-seg="conversion_action">Conversion action</div></div>
<button id="dl" aria-label="{download_label}">&#8595;</button>
<div id="dl-menu" role="menu" hidden><div role="menuitem" id="csv">.csv</div><div role="menuitem">.xlsx</div></div>
<script>
const page = "{page}";
let segment = "";
const range = () => localStorage.getItem("range") || "last7";
const label = () => ({{last7: "Last 7 days", last14: "Last 14 days", last30: "Last 30 days"}})[range()] || "Custom";
const byId = (id) => document.getElementById(id);
const hideMenus = () => document.querySelectorAll("[role=menu]").forEach((m) => (m.hidden = true));
byId("date").textContent = label();
byId("date").onclick = () => (byId("date-menu").hidden = false);
document.querySelectorAll("[data-range]").forEach((item) => (item.onclick = () => {{
  localStorage.setItem("range", item.dataset.range); byId("date").textContent = label(); hideMenus();
}}));
byId("apply").onclick = () => {{
  const inputs = document.querySelectorAll("#date-menu input");
  localStorage.setItem("range", "custom:" + inputs[0].value + "|" + inputs[1].value); hideMenus();
}};
byId("segment").onclick = () => (byId("seg-menu").hidden = false);
document.querySelectorAll("[data-next]").forEach((item) => (item.onclick = () => (byId(item.dataset.next).hidden = false)));
document.querySelectorAll("[data-seg]").forEach((item) => (item.onclick = () => {{ segment = item.dataset.seg; hideMenus(); }}));
byId("dl").onclick = () => (byId("dl-menu").hidden = false);
byId("csv").onclick = () => {{
  const link = document.createElement("a");
  link.href = "/download?" + new URLSearchParams({{page, range: range(), segment}});
  link.download = "";
  document.body.appendChild(link); link.click(); hideMenus();
}};
</script>
</body></html>"""

SIGN_IN = """<!doctype html><html><head><meta charset="utf-8"><title>Sign in - Google Accounts (mock)</title></head>
<body><h1>Sign in</h1><p>A person would type their password and 2-step code here.</p>
<script>
// Stands in for the human finishing sign-in; the exporter only waits.
setTimeout(() => {{ document.cookie = "mock_session=1; path=/"; location.href = "/aw/overview?{query}"; }}, 1200);
</script></body></html>"""


def _range(value, today):
    if value.startswith("custom:"):
        first, last = value[7:].split("|")
        parse = lambda s: datetime.datetime.strptime(s.strip(), "%b %d, %Y").date()  # noqa: E731
        return parse(first), parse(last)
    days = {"last7": 7, "last14": 14, "last30": 30}.get(value, 7)
    end = today - datetime.timedelta(days=1)
    return end - datetime.timedelta(days=days - 1), end


def _long(day):
    return f"{day:%B} {day.day}, {day.year}"


def report_csv(page, range_value, segment, today):
    start, end = _range(range_value, today)
    days = [start, start + datetime.timedelta(days=1)]
    lines = []
    if segment == "conversion_action":
        lines += [
            "Campaign report",
            f'"{_long(start)} - {_long(end)}"',
            "Campaign,Conversion action,Conversion category,Conversions,Conv. value,All conv.,All conv. value",
            "THB | Search | East Bay,,,5.00,500.00,6.00,600.00",
            "THB | Search | East Bay,Calls from ads,Phone call lead,3.00,300.00,3.00,300.00",
            "THB | Search | East Bay,Website lead form,Submit lead form,2.00,200.00,3.00,300.00",
            "Total: Account,,,5.00,500.00,6.00,600.00",
        ]
        return "\n".join(lines) + "\n"

    day = (lambda d: f"{d:%Y-%m-%d}") if segment == "day" else (lambda d: "")
    title = {"campaigns": "Campaign report", "adgroups": "Ad group report", "keywords": "Search keyword report",
             "searchterms": "Search terms report", "userlocations": "User locations report"}[page]
    lines += [title, f'"{_long(start)} - {_long(end)}"']
    if page == "campaigns":
        lines.append("Campaign,Day,Campaign status,Campaign type,Currency code,Impr.,Clicks,CTR,Avg. CPC,Cost,Conversions,Cost / conv.,Conv. value")
        lines.append("THB | Search | East Bay,,Enabled,Search,USD,\"1,000\",60,6.00%,20.00,\"1,200.00\",5.00,240.00,500.00")
        for d, (imp, clk, cost, conv) in zip(days, ((400, 25, 500.0, 2), (600, 35, 700.0, 3))):
            lines.append(f"THB | Search | East Bay,{day(d)},Enabled,Search,USD,{imp},{clk},--,--,\"{cost:,.2f}\",{conv}.00,--,{conv * 100}.00")
    elif page == "adgroups":
        lines.append("Ad group,Campaign,Day,Ad group status,Impr.,Clicks,Cost,Conversions")
        for d in days:
            lines.append(f"Sell My House Fast,THB | Search | East Bay,{day(d)},Enabled,300,20,400.00,2.00")
            lines.append(f"Cash Home Buyers,THB | Search | East Bay,{day(d)},Enabled,200,10,200.00,0.50")
    elif page == "keywords":
        lines.append("Keyword,Match type,Campaign,Ad group,Day,Impr.,Clicks,Cost,Conversions")
        for d in days:
            lines.append(f"[sell my house fast],Exact match,THB | Search | East Bay,Sell My House Fast,{day(d)},300,20,400.00,2.00")
            lines.append(f'"""we buy houses""",Phrase match,THB | Search | East Bay,Cash Home Buyers,{day(d)},200,10,200.00,0.50')
    elif page == "searchterms":
        lines.append("Search term,Match type,Added/Excluded,Campaign,Ad group,Keyword,Day,Impr.,Clicks,Cost,Conversions")
        for d in days:
            lines.append(f"sell my house fast oakland,Phrase match (close variant),None,THB | Search | East Bay,Sell My House Fast,[sell my house fast],{day(d)},120,9,180.00,1.00")
            lines.append(f"we buy ugly houses,Broad match,None,THB | Search | East Bay,Cash Home Buyers,\"\"\"we buy houses\"\"\",{day(d)},80,6,90.00,0.00")
    elif page == "userlocations":
        lines.append("City (User location),Region (User location),Country/Territory (User location),Campaign,Ad group,Day,Impr.,Clicks,Cost,Conversions")
        for d in days:
            lines.append(f"Oakland,California,United States,THB | Search | East Bay,Sell My House Fast,{day(d)},200,12,240.00,2.00")
            lines.append(f"Hayward,California,United States,THB | Search | East Bay,Sell My House Fast,{day(d)},100,8,160.00,0.00")
            lines.append(f"Oakland,California,United States,THB | Search | East Bay,Cash Home Buyers,{day(d)},200,10,200.00,0.50")
    lines.append("Total: Account,,,,,,,,,")
    return "\n".join(lines) + "\n"


class MockAds(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, today, download_label="Download"):
        super().__init__(("127.0.0.1", 0), Handler)
        self.today = today
        self.download_label = download_label
        self.requests = []

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", headers=()):
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        server = self.server
        server.requests.append(self.path)
        url = urllib.parse.urlparse(self.path)
        signed_in = "mock_session=1" in (self.headers.get("Cookie") or "")

        if url.path == "/signin":
            self._send(200, SIGN_IN.format(query=ACCOUNT_QUERY).encode(), [("Content-Type", "text/html")])
        elif url.path.startswith("/aw/"):
            if not signed_in:
                target = urllib.parse.quote(url.path)
                self._send(302, headers=[("Location", f"/signin?continue={target}")])
                return
            page = url.path[4:].strip("/")
            if page not in TITLES:
                self._send(302, headers=[("Location", f"/aw/overview?{ACCOUNT_QUERY}")])
                return
            body = PAGE.format(title=html.escape(TITLES[page]), page=page, download_label=server.download_label)
            self._send(200, body.encode(), [("Content-Type", "text/html")])
        elif url.path == "/download":
            query = dict(urllib.parse.parse_qsl(url.query))
            text = report_csv(query["page"], query.get("range", "last7"), query.get("segment", ""), server.today)
            name = {"campaigns": "Campaign report", "adgroups": "Ad group report", "keywords": "Search keyword report",
                    "searchterms": "Search terms report", "userlocations": "User locations report"}[query["page"]]
            # Real "Excel .csv" downloads are UTF-16; use that for keywords to cover it.
            body = text.encode("utf-16") if query["page"] == "keywords" else ("﻿" + text).encode("utf-8")
            self._send(200, body, [("Content-Type", "text/csv"),
                                   ("Content-Disposition", f'attachment; filename="{name}.csv"')])
        else:
            self._send(404, b"not found")
