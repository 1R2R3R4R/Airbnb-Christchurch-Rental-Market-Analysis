# Christchurch Housing Analysis — Data Documentation

This README documents the data sources, cleaning decisions, and analysis workflows behind the project, covering Deliverable 2 (initial KNIME exploration of the national Airbnb dataset) through Deliverable 4 (Python-based cleaning of the Christchurch-specific Airbnb panel and Tenancy Services bond data).

## Contents

1. [Deliverable 2 — Inside Airbnb New Zealand Analysis (KNIME)](#deliverable-2--inside-airbnb-new-zealand-analysis-knime)
2. [Deliverable 4 — Data Cleaning](#deliverable-4--data-cleaning)
   - [Christchurch Airbnb listings](#1-christchurch-airbnb-listings-clean_airbnbpy)
   - [Rental bond data](#2-rental-bond-data-clean_bondpy)
3. [Next Steps (Deliverable 5)](#next-steps-deliverable-5)

---

## Deliverable 2 — Inside Airbnb New Zealand Analysis (KNIME)

### Dataset Source

- **Provider:** [Inside Airbnb](https://insideairbnb.com/get-the-data/)
- **Region:** New Zealand
- **Snapshot date:** 19 June 2026
- **File used:** `listings.csv` (the summarised/"visualisations" file — 18 columns, uncompressed), **not** `listings.csv.gz` (the detailed, gzipped file with ~75 columns)
- **Direct source URL:** `https://data.insideairbnb.com/new-zealand/2026-06-19/visualisations/listings.csv`
- **Rows:** 50,932 listings

> Note: the dataset is stored locally on each team member's machine and is **not** committed to this GitHub repository (see `.gitignore`), as instructed.

Inside Airbnb collects (scrapes) publicly available data from the Airbnb website on a given date — this is the "scrape date," which appears in the source URL and file path (`2026-06-19` above). Because this summarised file has no per-row scrape timestamp, we use this fixed date as the reference point for all "how recent" calculations (e.g. days since last review).

### Column Documentation

| Column | Type | Description |
|---|---|---|
| `id` | Integer | Unique identifier for the listing |
| `name` | String | Listing title as shown on Airbnb |
| `host_id` | Integer | Unique identifier for the host |
| `host_name` | String | Host's first name |
| `neighbourhood_group` | String | Broader region/district/city name (e.g. "Christchurch City", "Auckland") — used as our primary geographic filter |
| `neighbourhood` | String | Finer-grained suburb/ward within the district (e.g. "East Ward") |
| `latitude` | Float | Listing's latitude coordinate |
| `longitude` | Float | Listing's longitude coordinate |
| `room_type` | String | Entire home/apt, Private room, Shared room, or Hotel room |
| `price` | Integer | Nightly price in NZD. Already numeric in this file (no currency symbol, unlike the detailed listings.csv) |
| `minimum_nights` | Integer | Minimum nights required per booking |
| `number_of_reviews` | Integer | Total number of reviews the listing has received |
| `last_review` | Date (string, `yyyy-MM-dd`) | Date of the most recent review. Missing for listings with zero reviews |
| `reviews_per_month` | Float | Average number of reviews received per month |
| `calculated_host_listings_count` | Integer | Number of listings the host has active on the platform |
| `availability_365` | Integer | Number of days available for booking in the next 365 days |
| `number_of_reviews_ltm` | Integer | Number of reviews received in the last 12 months |
| `license` | String | Registration/license number, where applicable. Mostly missing for NZ listings, likely reflecting the absence of a universal short-term rental registration requirement |

### KNIME Workflow

The full pipeline consists of four branches, all starting from a single **CSV Reader** node:

```
CSV Reader
  │
  ├─► String to Date&Time (last_review)
  │      └─► Constant Value Column Appender (scrape_date = 2026-06-19)
  │             └─► String to Date&Time (scrape_date)
  │                    └─► Date&Time Difference (days_since_last_review)
  │                           └─► Histogram — Days Since Last Review
  │
  ├─► Row Filter (price ≤ 1000)
  │      ├─► Histogram — Price, All of New Zealand
  │      └─► Rule Engine (region = "Christchurch" / "Rest of NZ")
  │             └─► Box Plot — Price, Christchurch vs Rest of NZ
  │
  ├─► Row Filter (neighbourhood_group = "Christchurch City")
  │      └─► Histogram — Price, Christchurch City only
  │
  └─► Rank (number_of_reviews, descending)
         └─► Row Filter (top 10% by rank)
                └─► GroupBy (neighbourhood_group, count of id)
```

#### Step-by-step

1. **CSV Reader** — loads `listings.csv` (comma-delimited, quoted strings, header row, missing values on empty quoted strings).
2. **Date processing branch:**
   - `String to Date&Time` converts `last_review` (string) → proper Date type.
   - `Constant Value Column Appender` adds a fixed `scrape_date` column = `2026-06-19` (the snapshot date) to every row.
   - `String to Date&Time` converts `scrape_date` (string) → Date type.
   - `Date&Time Difference` computes `days_since_last_review` = `scrape_date − last_review`, in days.
   - `Histogram` plots the distribution of `days_since_last_review`.
3. **Price distribution branch:**
   - `Row Filter` keeps listings with `price ≤ 1000` NZD (excludes extreme outliers for a readable distribution).
   - `Histogram` plots price distribution for all of New Zealand.
   - `Rule Engine` labels each row `region = "Christchurch"` (where `neighbourhood_group = "Christchurch City"`) or `"Rest of NZ"` (otherwise).
   - `Box Plot` (conditioned on `region`) plots both price distributions side by side in a single chart — this satisfies the "plot both in the same plot" bonus task.
4. **Christchurch-only price branch:**
   - A separate `Row Filter` (`neighbourhood_group = "Christchurch City"`) branches off the price-capped data.
   - `Histogram` plots price distribution for Christchurch City only, using the same bin count and axis range as the NZ-wide histogram for direct comparability.
5. **Most-reviewed listings branch:**
   - `Rank` node ranks all listings by `number_of_reviews`, descending.
   - `Row Filter` keeps the top 10% by rank.
   - `GroupBy` (grouped by `neighbourhood_group`, counting `id`) shows how many top-10% listings fall in each district.

### Key Findings

- **Price distribution:** Both the NZ-wide and Christchurch-only price distributions are right-skewed, peaking around **$150–200/night**, with a long tail out to $1,000+. Christchurch's distribution closely mirrors the national pattern in shape.
- **Missing prices:** ~5,223 listings (≈10%) have no listed price and were excluded from the price analyses.
- **Christchurch vs Rest of NZ (Box Plot):** Christchurch's typical Airbnb prices run slightly lower and more tightly clustered than the rest of NZ (median ≈$200 vs ≈$250, narrower interquartile range), but Christchurch shows a higher share of high-priced outlier listings relative to its own distribution.
- **Days since last review:** The majority of listings (36,337) were reviewed relatively recently, with a long tail extending out to ~4,856 days (~13 years) for a small number of stale listings. A further 5,128 listings (≈10%) have never received a review.
- **Top 10% most-reviewed listings:** Of the 5,234 listings in the top 10% nationally by review count, **515 are in Christchurch City** — the second-highest count of any district after Auckland (561), representing roughly **9.8%** of all top-10% listings nationwide.

### Limitations / Notes

- The summarised `listings.csv` file does not include a per-row scrape timestamp, so a fixed reference date (the snapshot date from the source URL) was used for all "days since" calculations.
- The top-10% cutoff resulted in 5,234 rows rather than exactly 5,093 (10% of 50,932) due to tied `number_of_reviews` values at the rank boundary.

---

## Deliverable 4 — Data Cleaning

### 1. Christchurch Airbnb listings (`clean_airbnb.py`)

**Source:** `Airbnb_Oct25_Jun26.csv` — Christchurch listings scraped monthly, Oct 2025 – Jun 2026 (built in Deliverable 3). One row = one listing in one month (panel data).

**Columns kept** and what they mean:

| Column | Meaning |
|---|---|
| `id` | Unique listing ID (repeats across months) |
| `host_id` | Unique host ID |
| `neighbourhood` | Christchurch ward the listing is in |
| `latitude`, `longitude` | Listing coordinates |
| `room_type` | Entire home/apt, Private room, Shared room, Hotel room |
| `price` | Nightly price (NZD) |
| `minimum_nights` | Minimum nights per booking |
| `number_of_reviews` | Total reviews to date |
| `last_review` | Date of most recent review |
| `reviews_per_month` | Review frequency |
| `calculated_host_listings_count` | How many listings this host runs |
| `availability_365` | Days available for booking in the next year |
| `number_of_reviews_ltm` | Reviews in the last 12 months |
| `month_year` | Which monthly snapshot this row is from |
| `price_missing` | *(added)* `True` where `price` was NULL in the source data |

**Cleaning decisions:**

| Decision | Reason | Rows/cols affected |
|---|---|---|
| Dropped `license` | 100% missing | 1 column, 0 rows |
| Dropped `neighbourhood_group` | Constant ("Christchurch City" every row) — zero information | 1 column |
| Dropped `host_name`, `name` | Free-text, not needed for price/location analysis; privacy | 2 columns |
| Kept `price` missing values, added `price_missing` flag | ~37% missing; likely means "unavailable/no set price" rather than a data error — dropping these rows would badly bias price analysis | 10,667 rows flagged, 0 rows dropped |
| Filled `reviews_per_month` NaN with 0 | Confirmed these all have `number_of_reviews == 0` — i.e. genuinely "no reviews yet" | ~2,627 rows |
| Parsed `last_review`, `month_year` to real dates | Enables date-based filtering/joins | — |
| Dropped duplicate `(id, month_year)` rows | Data integrity check | 0 rows found |

**Result:** 28,795 rows in, 28,795 rows out (no rows dropped), 19 → 18 columns (+1 flag column).

**Output:** `airbnb_christchurch_clean.parquet` (Parquet chosen over CSV for space efficiency and to preserve dtypes across reruns).

---

### 2. Rental bond data (`clean_bond.py`)

**Source:** "Detailed quarterly report, 2020–2026", Tenancy Services / Ministry of Business, Innovation & Employment (tenancy.govt.nz). National data, one row per quarter × area × dwelling type × bed count combination, Jan 2020 – Apr 2026.

**Columns kept** and what they mean:

| Column | Meaning |
|---|---|
| `TimeFrame` | Quarter start date (Jan/Apr/Jul/Oct) |
| `Location Id` | 2018 Statistical Area 2 (SA2) code identifying the area |
| `Dwelling Type` | House / Apartment / Flat / Room / Boarding House, or "ALL" for the combined total |
| `Number Of Beds` | 0–9, "5+", or "ALL" for the combined total |
| `Total Bonds` | **New** bonds lodged that quarter (flow) |
| `Active Bonds` | Bonds currently active at quarter-end (stock — this is your best proxy for "number of available/rented properties") |
| `Closed Bonds` | Bonds closed/ended that quarter (flow) |
| `Median Rent`, `Geometric Mean Rent`, `Upper Quartile Rent`, `Lower Quartile Rent`, `Log Std Dev Weekly Rent` | Weekly-rent statistics for that combination — see note below on how Tenancy Services calculates these |

**A note on the rent statistics — geometric mean and synthetic quartiles:**

Tenancy Services doesn't report a plain arithmetic mean/median or simple empirical quartiles for weekly rent. Instead:

- **Geometric mean (in place of the median):** calculated by multiplying the values together and taking the *n*th root of the result. Weekly rent — like many variables that must be strictly greater than 0 — tends to follow a log-normal distribution, and for a log-normally distributed variable, the geometric mean closely approximates the median. This makes it a more robust "typical value" than an arithmetic mean, which would be pulled upward by the right-skew that's typical of rent data (a small number of very expensive properties).
- **Synthetic quartiles (in place of empirical quartiles):** the `Upper Quartile Rent` and `Lower Quartile Rent` columns are *synthetic* — they estimate the 75th and 25th percentiles respectively by assuming the underlying rent data is log-normally distributed, then calculating the distribution's mean and variance from the actual data (rather than assuming fixed values) and deriving the quartiles from that fitted distribution. This is consistent with using the geometric mean to approximate the median — both methods lean on the same log-normal assumption rather than reading percentiles directly off the raw data.

Practically, this means these columns should be read as **model-based estimates under a log-normal assumption**, not raw empirical statistics — worth flagging in any write-up that directly compares these rent figures to Airbnb nightly prices (which are raw, not distribution-fitted).

**Cleaning decisions:**

| Decision | Reason | Rows/cols affected |
|---|---|---|
| Filtered `TimeFrame` to Oct 2025 / Jan 2026 / Apr 2026 | Matches the Airbnb dataset's Oct 2025–Jun 2026 window (quarterly vs. monthly granularity) | 226,080 → 27,212 rows (198,868 dropped) |
| Dropped `Location Id == -99` | National ("All NZ") rollup — not a real area, would double-count in area-level comparisons | 127 rows |
| Dropped `Location Id` missing | Bonds that couldn't be geocoded to an SA2 — unusable for area-based analysis | 94 rows |
| Filtered `Location Id` to confirmed Christchurch SA2 codes | Isolates Christchurch City for next week's comparison; see limitation below | 24,821 rows (only 2,170 of the 26,991 timeframe-filtered rows are Christchurch) |
| Left rent columns as NaN where suppressed | Tenancy Services suppresses rent stats for privacy in small cells (<5 bonds); this is a genuine "unknown," not zero — imputing would misrepresent the market. `Total`/`Active`/`Closed Bonds` remain valid for these rows | 0 rows in our filtered window (all suppression happened outside Oct 2025–Apr 2026) |

**Result:** 226,080 rows in, 2,170 rows out, 12 columns (all kept, per the brief).

**Christchurch filter — known limitation:** `Location Id` uses 2018-vintage SA2 codes, but the only Stats NZ SA2↔Territorial Authority concordance available through Ariā uses 2023-vintage SA2 codes (built by joining `Meshblock 2024 to Statistical Area 2 2023` and `Meshblock 2024 to Territorial Authority 2023`). Most Christchurch SA2s kept the same code across both versions, and those 131 "confirmed" codes (see `christchurch_sa2_lookup.csv`) are what this script filters on. However:
- **24 `Location Id` values** in the Christchurch numeric range (2,949 rows before the timeframe filter) have no confirmed match and are **excluded**: `316000, 316100, 316200, 317200, 317300, 317500, 317700, 318400, 318500, 318900, 320500, 321100, 321300, 321700, 321900, 324000, 324500, 325300, 325600, 326300, 326700, 327300, 327900, 328000`
- **10 Christchurch SA2s** from the 2023 concordance (`316500, 316700, 320400, 324700, 324900, 330700, 331600, 333000, 333300, 333400`) never appear in the bond data at all — likely renamed/renumbered between 2018 and 2023
- If your team wants full precision, look up an official 2018 SA2 → Territorial Authority concordance (not available via Ariā's UI at the time of writing) and re-run the filter — otherwise, this documented gap is the accepted trade-off for this deliverable.

**Output:** `bond_data_clean.parquet`, `christchurch_sa2_lookup.csv` (131 confirmed SA2 code → name pairs, needed to rerun this script).

---

## Next Steps (Deliverable 5)

Combine both datasets via `Location Id` ↔ Christchurch `neighbourhood`/coordinates (needs an SA2 → suburb/ward lookup) to compare rental prices and property availability across Airbnb and the long-term rental market.

Two design decisions need to be resolved before this join can be written correctly:
- **Time granularity:** Airbnb is monthly, bond data is quarterly — decide whether to aggregate Airbnb up to quarters or broadcast each bond-quarter across its 3 corresponding months.
- **Geographic granularity:** Airbnb uses ward names (`neighbourhood`), bond data uses SA2 codes (`Location Id`) — decide whether to map wards to SA2s or aggregate bond data up to ward level.
