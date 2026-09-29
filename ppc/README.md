# THB PPC exporter

Pulls the Google Ads reports we analyse and builds one AI-ready master file,
instead of downloading the Overview cards by hand.

It exports six reports: **search terms, search keywords, campaigns, ad groups,
city / location, and conversions by action**. Each includes date, campaign, ad
group, keyword, match type, search term, city, impressions, clicks, CTR,
average CPC, cost, conversions, cost per conversion and conversion value, where
Google has them. It then builds `ppc_master_data.csv` and the
**Keyword + City + Spend + Clicks + Conversions** table, with empty columns
ready for Qualified Leads, Appointments, Offers, Contracts, Closed Deals and
Profit.

```
exports/2026-09-28/
  search_terms.csv
  keywords.csv
  campaigns.csv
  ad_groups.csv
  locations.csv
  conversions.csv
  ppc_master_data.csv            every row of every report, stacked
  keyword_city_performance.csv   Keyword + City + Spend + Clicks + Conversions (+ lead outcomes)
  data_dictionary.md             what every column means (hand it to the AI with the CSV)
  manifest.json                  what ran, row counts, totals, warnings
  raw/                           the original browser downloads (browser mode only)
exports/lead_outcomes.csv        your lead results, one row per lead (you fill this in)
```

`exports/`, `ppc/config.yaml` and `ppc/.env` are git-ignored: account data and
credentials never get committed.

## Three ways to get the data

| | How | Needs | Runs unattended |
|---|---|---|---|
| **1. API** (preferred) | `python ppc/export.py api` | Google Cloud project with Google Ads API access (below) | Yes |
| **2. Browser** (fallback) | `python ppc/export.py browser` | You, to sign in | No, you sign in |
| **3. Import** | `python ppc/export.py import --from <folder>` | CSVs you downloaded yourself | n/a |

`python ppc/export.py` with no command does what the plan asked for: it uses
the API if it is set up, and otherwise says what is missing and falls back to
the browser.

## Install (once)

Python 3.10 or newer.

macOS:

```bash
cd Ai-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r ppc/requirements.txt
cp ppc/config.example.yaml ppc/config.yaml
python ppc/export.py demo      # synthetic data, proves the pipeline works; writes exports/demo/
python ppc/export.py status    # what is configured and what is missing
```

Windows (PowerShell):

```powershell
cd Ai-agent
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r ppc\requirements.txt
copy ppc\config.example.yaml ppc\config.yaml
python ppc\export.py demo
python ppc\export.py status
```

The browser mode uses your installed **Google Chrome**. If Chrome is not
installed, run `python -m playwright install chromium` once.

## 1. Google Ads API setup

Google changed how access works: **developer tokens were retired on
2026-09-09**. Access now belongs to the Google Cloud project that owns your
credentials, and no manager (MCC) account is needed. About 20 minutes of
clicking, done once.

1. **Cloud project.** Create or pick one at
   <https://console.cloud.google.com/projectcreate>. Put it in the
   twinhomebuyer.com organization if you can. **Turn billing on**
   (<https://console.cloud.google.com/billing>). The API is free, but Google does
   not upgrade Free Trial or billing-disabled projects past Test access.
2. **Enable the Google Ads API:**
   <https://console.cloud.google.com/flows/enableapi?apiid=googleads.googleapis.com>
3. **Get production access.** Open the Google Ads API Overview page,
   <https://console.cloud.google.com/google/ads-apis/overview>. It will say
   **Test**, which only reaches test accounts. Expand **Upgrade access level**
   and click **Apply for access** for **Explorer**. Explorer allows 2,880
   operations a day; one export uses about 8. Google may approve it automatically.
   Basic (15,000 a day) also needs brand verification, which we do not need.
4. **Credentials.** Choose one.

   **A. Service account (Google's recommended setup).**
   1. <https://console.cloud.google.com/iam-admin/serviceaccounts>, then
      **Create service account**, e.g. `thb-ads-reporting`. It needs no
      Cloud roles.
   2. Open it, then **Keys > Add key > Create new key > JSON**. Save the file
      **outside this repo**, e.g. `~/.thb/google-ads-key.json`. It is the only
      copy; treat it like a password.
   3. In **Google Ads**: **Admin > Access and security > Users > +**, paste the
      service account's email (`...@....iam.gserviceaccount.com`), choose
      **Read only**, and click **Add account**.
   4. In `ppc/config.yaml`, set `api.json_key_file_path: "~/.thb/google-ads-key.json"`.

   If the console says key creation is disabled (an organization policy),
   either ask the Workspace / Cloud admin to allow keys for this one project,
   or use B.

   **B. OAuth (sign in as yourself).**
   1. <https://console.cloud.google.com/auth/overview>: configure the consent
      screen and set **Audience** to **Internal**. With External + Testing,
      Google expires the token every 7 days.
   2. <https://console.cloud.google.com/auth/clients>, then **Create client >
      Desktop app**. Copy the client ID and secret into `ppc/config.yaml`
      (`api.client_id`, `api.client_secret`).
   3. Run `python ppc/export.py refresh-token`. Your browser opens, you sign in
      with the Google account that can open THB's Google Ads (password and
      2-step verification are yours to do), and the token is saved into
      `config.yaml`. The Google account needs 2-step verification turned on.
5. **Account ID.** In `ppc/config.yaml`, set `customer_id` to the 10-digit ID
   at the top of Google Ads (dashes are fine). Only if you reach THB through a
   manager account (e.g. an agency MCC), also set `api.login_customer_id` to
   the manager's ID.
6. **Test it:** `python ppc/export.py check`. This signs in, confirms the
   account, and has Google validate all six queries without running them.
   Then run `python ppc/export.py api`.

**Shortcut if you already have the values** as `GOOGLE_ADS_...=...` lines:
paste them, as they are, into `ppc/.env` instead of editing `config.yaml`.
On Windows run `notepad ppc\.env`, answer Yes to create the file, paste,
save and close. For example:

```
GOOGLE_ADS_CUSTOMER_ID=1234567890
GOOGLE_ADS_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_ADS_CLIENT_SECRET=...
GOOGLE_ADS_REFRESH_TOKEN=...
```

Settings are read from `config.yaml`, then `ppc/.env`, then real environment
variables, each overriding the one before. They use the client library's
usual names: `GOOGLE_ADS_CUSTOMER_ID`, `GOOGLE_ADS_JSON_KEY_FILE_PATH`,
`GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`
and `GOOGLE_ADS_LOGIN_CUSTOMER_ID`. `ppc/.env` is git-ignored.

### When Google refuses

The exporter prints the cause and the fix. The common ones:

| Google says | Fix |
|---|---|
| `CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION` | The project only has Test access. Do step 3 (and turn billing on). |
| `USER_PERMISSION_DENIED` | Add the service account (or your Google account) under Admin > Access and security in Google Ads, or set `login_customer_id` if you go through a manager account. |
| `PROJECT_DISABLED` / "has not been used in project" | Do step 2. |
| `REQUESTED_METRICS_FOR_MANAGER` | `customer_id` is a manager account. Use THB's own account ID there and put the manager's ID in `login_customer_id`. |
| `invalid_grant` (OAuth) | The refresh token expired or was revoked. Set the consent screen to Internal and run `refresh-token` again. |
| `invalid_grant: account not found` (service account) | The service account or key was deleted. Create a new key. |
| `invalid_client` | `client_id` / `client_secret` are wrong. |
| `TWO_STEP_VERIFICATION_NOT_ENROLLED` | Turn on 2-step verification for the Google account used. |

If Google rejects one report's query (it tightens field rules from time to
time), the exporter retries that report with a smaller query and says so in
`manifest.json`. The other reports still run.

### Running it every day

Only API mode runs without a person. macOS/Linux cron, 6:15 every morning:

```
15 6 * * * cd /path/to/Ai-agent && .venv/bin/python ppc/export.py api >> exports/export.log 2>&1
```

On Windows, use Task Scheduler with `python ppc\export.py api` in the repo folder.

## 2. Browser fallback

```bash
python ppc/export.py browser
```

What happens:

1. A Chrome window opens with its own profile (`~/.thb-ppc-browser`), not
   your everyday Chrome.
2. **You sign in to Google Ads**: password, 2-step verification and any
   security check. The script never types on or clicks Google's sign-in pages,
   and never touches a CAPTCHA. It just waits, for up to 15 minutes.
3. It opens each report, sets the date range (default: Google's own "Last
   30 days"), splits by day, and clicks **Download > .csv**. It checks each
   file's own date-range line against the range you asked for.
4. If the Google Ads website has changed and a button is not where the script
   expects, the terminal says exactly what to click. Your click is captured
   and saved under the right name.

The next run reuses the profile, so you stay signed in until Google signs you
out. **Watch the first run.** The website changes without notice, and the
script was tested against a stand-in page, not the live site.

**If Google says "This browser or app may not be secure", do not try to get
around it.** Use attach mode. You sign in inside a normal Chrome window you
opened yourself, and the script connects only after you press Enter:

```bash
python ppc/export.py open-chrome        # opens Chrome with a separate profile; sign in there
python ppc/export.py browser --attach   # then press Enter when signed in
```

While that window is open, programs on your computer can control it through
its debugging port. Close it when the export is done.

**Most reliable:** build each report once in Google Ads **Report editor**
with the columns you want plus **Day**, save it, and paste each saved
report's URL into `browser.saved_reports` in `config.yaml`. The script then
opens those exact reports instead of finding its way around the site.

Known limits of the browser path:

- Conversions come from the Campaigns table segmented by conversion action.
  The website allows one segment at a time, so that file has range totals,
  not daily rows.
- A table only downloads the columns it shows. If Keyword or Match type is
  missing from a download, add the column in Google Ads once; the site
  remembers it.

## 3. Import files you downloaded

Download the reports any way you like (Report editor, a table's Download
button, or scheduled email reports) into one folder, then:

```bash
python ppc/export.py import --from ~/Downloads/thb-ads
```

It recognises Google's UI formats: title and date-range lines, "Total" rows,
`--` for empty, `1,234.56`, `5.23%`, and UTF-16 "Excel .csv" files. It works
out which report each file is from its name or columns, and takes the date
range from the files.

## Keyword + City

`keyword_city_performance.csv` has one row per keyword and city: spend,
clicks, conversions, CTR, CPC, conversion rate and cost per conversion.

**Google never reports keyword and city together.** Keyword reports have no
location, and location reports have no keyword. So each keyword's numbers are
split across the cities its **ad group** actually served, in proportion to
that ad group's city mix. `city_method` on every row says how its city was
decided:

- `exact`: the ad group served only this city, so the numbers are Google's own.
  An ad group per city (as in "THB Hayward") makes everything exact.
- `estimated`: split by the ad group's city mix. Every keyword in one ad group
  gets the same city split, even one that names a city.
- `no location data`: Google returned no location rows for that ad group.
- `outcomes only`: leads logged for a keyword/city with no spend in the range.

Keyword totals always equal Google's. Estimated rows carry decimal clicks so
they still add up. `manifest.json` reports what share of spend has an exact
city, and flags spend that has no keyword at all (Performance Max, Display).

## Lead outcomes: Qualified Leads to Profit

`exports/lead_outcomes.csv` is created the first time you export. Add **one
row per lead**, from the CRM or the Live Call Claims sheet:

| column | |
|---|---|
| `lead_date` | the day the lead first came in (required) |
| `lead_id` | your CRM / sheet ID (no names or phone numbers) |
| `campaign`, `ad_group`, `keyword`, `search_term`, `city`, `gclid` | whatever is known. Blank keyword is fine, e.g. most phone calls. |
| `qualified_lead`, `appointment`, `offer`, `contract`, `closed_deal` | yes / no |
| `profit` | for closed deals |

Then refresh the numbers without downloading again:

```bash
python ppc/export.py rebuild exports/2026-09-28
```

`keyword_city_performance.csv` then fills qualified_leads, appointments,
offers, contracts, closed_deals and profit. It adds cost per qualified lead,
appointment, offer, contract and closed deal, plus profit minus spend and ROI.
Leads fall into the export whose date range contains their `lead_date`. Leads
with no keyword land on `(unknown keyword)` rows in their city. For cost per
lead by city, add up spend and leads across all of that city's rows. Until the
first lead is logged, those columns stay blank (not zero).

## Dates

The default is the last 30 complete days ending yesterday, on the office clock
(America/Los_Angeles). That is the same as Google Ads' "Last 30 days". The
folder is named for the day you ran it. Use `--days 7`, or
`--start 2026-09-01 --end 2026-09-27` for a specific range.

## Tests

```bash
python -m pytest ppc/tests -q
```

The tests check every query field against the API's own definitions (v25),
run the API path against a fake service returning real API rows, parse
UI-format downloads, check that Keyword + City reconciles to Google's
totals, and drive the browser path against a local stand-in for the Google Ads
website. For the browser tests, set `PPC_TEST_CHROME` to a Chromium or Chrome
binary if Playwright's own browser is not installed.

## Files

| File | What it does |
|---|---|
| `export.py` | Command line: `api`, `check`, `browser`, `import`, `rebuild`, `demo`, `status`, `refresh-token`, `open-chrome` |
| `ppc_exporter/queries.py` | The GAQL for each report, with fallback variants |
| `ppc_exporter/api_source.py` | API client, error explanations, OAuth helper |
| `ppc_exporter/browser_source.py` | Browser fallback (Playwright) |
| `ppc_exporter/normalize.py` | Reads Google Ads UI downloads |
| `ppc_exporter/master.py` | Master file, Keyword + City, lead outcomes, manifest, dictionary |
| `ppc_exporter/schema.py` | Every column and what it means |
| `ppc_exporter/demo.py` | Synthetic data for `demo` |
| `config.example.yaml` | Settings template (copy to `config.yaml`) |
| `lead_outcomes_template.csv` | Starting point for `exports/lead_outcomes.csv` |
