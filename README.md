# Deliverable 2 — Inside Airbnb New Zealand Analysis (KNIME)

## Dataset Source

- **Provider:** [Inside Airbnb](https://insideairbnb.com/get-the-data/)
- **Region:** New Zealand
- **Snapshot date:** 19 June 2026
- **File used:** `listings.csv` (the summarised/"visualisations" file — 18 columns, uncompressed), **not** `listings.csv.gz` (the detailed, gzipped file with ~75 columns)
- **Direct source URL:** `https://data.insideairbnb.com/new-zealand/2026-06-19/visualisations/listings.csv`
- **Rows:** 50,932 listings

> Note: the dataset is stored locally on each team member's machine and is **not** committed to this GitHub repository (see `.gitignore`), as instructed.

Inside Airbnb collects (scrapes) publicly available data from the Airbnb website on a given date — this is the "scrape date," which appears in the source URL and file path (`2026-06-19` above). Because this summarised file has no per-row scrape timestamp, we use this fixed date as the reference point for all "how recent" calculations (e.g. days since last review).

## Column Documentation

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

## KNIME Workflow

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

### Step-by-step

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

## Key Findings

- **Price distribution:** Both the NZ-wide and Christchurch-only price distributions are right-skewed, peaking around **$150–200/night**, with a long tail out to $1,000+. Christchurch's distribution closely mirrors the national pattern in shape.
- **Missing prices:** ~5,223 listings (≈10%) have no listed price and were excluded from the price analyses.
- **Christchurch vs Rest of NZ (Box Plot):** Christchurch's typical Airbnb prices run slightly lower and more tightly clustered than the rest of NZ (median ≈$200 vs ≈$250, narrower interquartile range), but Christchurch shows a higher share of high-priced outlier listings relative to its own distribution.
- **Days since last review:** The majority of listings (36,337) were reviewed relatively recently, with a long tail extending out to ~4,856 days (~13 years) for a small number of stale listings. A further 5,128 listings (≈10%) have never received a review.
- **Top 10% most-reviewed listings:** Of the 5,234 listings in the top 10% nationally by review count, **515 are in Christchurch City** — the second-highest count of any district after Auckland (561), representing roughly **9.8%** of all top-10% listings nationwide.

## Limitations / Notes

- The summarised `listings.csv` file does not include a per-row scrape timestamp, so a fixed reference date (the snapshot date from the source URL) was used for all "days since" calculations.
- The top-10% cutoff resulted in 5,234 rows rather than exactly 5,093 (10% of 50,932) due to tied `number_of_reviews` values at the rank boundary.
