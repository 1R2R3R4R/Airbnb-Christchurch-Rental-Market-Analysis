# Christchurch Airbnb vs Long-Term Rentals

## Introduction

This project compares short-term rentals (Airbnb) with long-term rentals in Christchurch, New Zealand. It matches monthly Airbnb listings from October 2025 to August 2026 with Tenancy Services rental bond data by neighbourhood. It then compares prices, the number of rentals and property sizes. The headline finding: in Christchurch Central, Airbnb listings outnumber long-term rentals by about three to one.

To reproduce the results, add the raw data to `data/` and run `python update_pipeline.py`. Full details are below.

---

## Contents

- [What it answers](#what-it-answers)
- [Step-by-step setup](#step-by-step-setup)
- [Data](#data)
- [How it works](#how-it-works)
- [Main results](#main-results)
- [Good to know](#good-to-know)
- [Adding new months](#adding-new-months)
- [What's in this repository](#whats-in-this-repository)
- [Data sources](#data-sources)
- [Team](#team)

## What it answers

- How Airbnb nightly prices are spread, and how they change from month to month
- What the median Airbnb price is in Christchurch Central
- Where Airbnb charges the biggest premium over long-term rent (weekly rent ÷ 7)
- How many Airbnb listings each area has compared with active long-term rentals
- How property sizes (bedrooms) roughly compare between the two

Areas are Stats NZ **SA2** areas (Statistical Area 2, roughly suburb-sized), because that is how the bond data is reported.

## Step-by-step setup

You need Python 3.12 or newer. The code has been tested on Python 3.12 and 3.13, with pandas 2.2 and 3.0.

1. **Get the code and install the packages**

   ```sh
   git clone https://github.com/1R2R3R4R/Airbnb-Christchurch-Rental-Market-Analysis.git
   cd Airbnb-Christchurch-Rental-Market-Analysis
   python -m pip install -r requirements.txt
   ```

2. **Add the raw data** to the `data/` folder. It is not stored in this repository; see [Data](#data) for what to download.

3. **Run everything**

   ```sh
   python update_pipeline.py
   ```

   It takes a few seconds. You should see `Finished (complete): 35,796 records.` at the end. The results go into `output/`; start with `output/REPORT.md`.


**Google Colab:** run the same commands in a code cell, putting `!` in front of each one and using `%cd` instead of `cd`. Before step 3, upload the raw data files into `data/` using the Files panel.

## Data

Save these files in `data/` with exactly these names. The same list is in `config.json`.

| File | Where to get it |
|---|---|
| `listings_2025-10.csv` … `listings_2026-08.csv` (11 files, one per month) | [Inside Airbnb](https://insideairbnb.com/get-the-data/) → New Zealand → the summary **`listings.csv`** (not `listings.csv.gz`). Direct links look like `https://data.insideairbnb.com/new-zealand/2026-06-19/visualisations/listings.csv` |
| `bond_raw.csv` | [Tenancy Services rental bond data](https://www.tenancy.govt.nz/about-tenancy-services/data-and-statistics/rental-bond-data/) → the "Detailed quarterly report" CSV, renamed |

These files are already in the repository:

| File | What it is |
|---|---|
| `christchurch_sa2_lookup.csv` | Christchurch SA2 area codes and names |
| `sa2_cache.csv` | The SA2 area code for every listing location. Because of this file, **no API key is needed** to rerun the project |
| `Detailed-Quarterly-Tenancy-Q1-2020-Q3-2026.csv` | Tenancy Services bond data (quarters up to April–June 2026), used by `clean_bond.py` |
| `Airbnb_Oct25_Jun26.csv` | Combined Christchurch Airbnb listings, Oct 2025 – Jun 2026, used by notebooks 02 and 03 |
| `christchurch_listings_2025-10_to_2026-06_final.csv` | Cleaned version of the combined listings from the earlier notebook stage |

> **Older Airbnb files:** Inside Airbnb's public archive generally covers about the last 12 months, mostly quarterly. Older monthly files may need an archived-data request through their website, or you can ask the project team for a copy.
>
> **Newer bond files:** the results below use the bond file that covers January 2020 to April 2026. A newer file with later quarters will also match July and August 2026, so some numbers will change.

## How it works

`update_pipeline.py` runs these steps, with help from `rental_pipeline.py`:

1. **Load** each monthly Airbnb file and keep the Christchurch City listings. Listing IDs are kept as text, so long IDs are never rounded.
2. **Clean** the listings:
   - remove listing titles and host names (privacy)
   - drop columns that are empty or have the same value in every row
   - keep missing prices, but flag them in a `price_missing` column
   - set reviews per month to 0 only for listings that have no reviews
3. **Add an area code** to each listing from its latitude and longitude, using `data/sa2_cache.csv`. Only locations that aren't in the cache are looked up online (Koordinates API, Stats NZ SA2 2026 layer).
4. **Clean the bond data**: keep Christchurch areas and the quarters that overlap the Airbnb months.
5. **Join** the Airbnb and bond data on area and quarter (for example, October–December 2025 is 2025Q4).
6. **Analyse**:
   - price charts
   - the price gap by area
   - Airbnb listings vs active bonds
   - the bedroom comparison

   The join is repeated in SQLite as a cross-check, and `output/REPORT.md` is written.

If a run fails, the previous `output/` folder is left untouched.

## Main results

| Result | Value |
|---|---|
| Airbnb listing-month records, Oct 2025 – Aug 2026 | 35,796 |
| Records matched to bond data, Oct 2025 – Jun 2026 | 21,946 |
| Median Airbnb price in Christchurch Central (SA2 326600), prices $20–$800 | $244 per night (937 listing-months, 157 listings) |
| Biggest Airbnb premium over long-term rent (areas with 20+ records) | Holmwood, about $210 per night |
| Christchurch Central in a typical quarter | 140 Airbnb listings vs 42 active bonds |

Christchurch Central has about three times more Airbnb listings than long-term rentals. The neighbouring central areas are the other way round; for example, Central-North has 172 listings vs 1,131 bonds.

## Good to know

- **Short-term vs long-term** is decided by the data source, not by the length of stay. A row from Airbnb counts as short-term, and a rental bond counts as long-term.
- **Rent per night** is the weekly median rent divided by 7.
- **Missing prices:** the December 2025, January 2026 and February 2026 Airbnb files have no prices at all in the original downloads. Those rows are kept and labelled, not filled in.
- **No bond data for July–August 2026 yet.** Those two months appear in the Airbnb-only charts but not in the comparisons.
- **Area code versions:** the bond data, the area lookup and the online lookup use Stats NZ boundaries from different years (2018, 2023 and 2026). A few areas therefore don't match, and they are shown with their code instead of a name.
- **Bedrooms:** the Airbnb data has no bedroom count, so room type stands in for it (an entire home counts as about 2 bedrooms, a room as 1). Treat that comparison as rough.
- **Review dates:** 1,824 records have a last review dated after that month's snapshot date. They are saved to `output/reviews_after_reference_date.csv` for checking, and they are left out of the review-recency chart.

## Adding new months

1. Download the new month's `listings.csv` and save it as `data/listings_YYYY-MM.csv`.
2. In `config.json`, add the file under `"snapshots"`. Under `"reference_dates"`, add the date that month's file was collected; it is used to work out days since the last review.
3. Run `python update_pipeline.py` again.

New listing locations need a [Koordinates](https://koordinates.com/) API key. Either set the environment variable `KOORDINATES_API_KEY`, or put the key in a file called `koordinates_key.txt` in the main folder (never commit this file).

To run without a key, use `python update_pipeline.py --offline`. Listings that still need an area code are then listed in `output/pending_or_failed_area_queries.csv`, and the run is marked `partial`.

## What's in this repository

| Path | Purpose |
|---|---|
| `update_pipeline.py` | Main script; runs the whole project |
| `rental_pipeline.py` | Area codes, bond data cleaning, joins and comparisons (used by the main script) |
| `clean_bond.py` | Deliverable 4 bond data cleaning script (the final pipeline does this in `rental_pipeline.py`) |
| `config.json` | Input files, dates and analysis settings such as price limits and minimum counts |
| `requirements.txt` | Python packages for the pipeline and the notebooks |
| `data/` | Area lookup, area-code cache, the bond file and the combined Oct 2025 – Jun 2026 Airbnb files (see [Data](#data)). The monthly `listings_YYYY-MM.csv` downloads go here too; they aren't committed || `01_explore_listings.ipynb`, `02_clean_data.ipynb`, `03_join_airbnb_bond.ipynb` | Earlier step-by-step notebooks (see below) |
| `TEAM.md` | Team members and who did what |

`output/` is created when you run the pipeline and isn't committed.

### About the notebooks

The notebooks are the earlier, step-by-step version of the analysis, covering October 2025 to June 2026. They read in-between files from the main folder that aren't in the repository, so they don't run from a fresh clone. The pipeline covers the same steps, plus July and August.

If you do run them, be aware of two things:
- notebook 02 expects review dates in day/month/year format
- notebook 03 needs your own API key typed into `API_KEY`

## Data sources

- Airbnb listings: [Inside Airbnb](https://insideairbnb.com/get-the-data/), New Zealand
- Rental bonds: [Tenancy Services](https://www.tenancy.govt.nz/about-tenancy-services/data-and-statistics/rental-bond-data/), Ministry of Business, Innovation & Employment
- Area boundaries: Stats NZ Statistical Area 2 2026, via [Koordinates](https://koordinates.com/) (layer 123515)

## Team

See [`TEAM.md`](TEAM.md).
