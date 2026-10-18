"""
Deliverable 4 — Cleaning the Tenancy Services rental bond dataset
====================================================================
Source: "Detailed quarterly report, 2020-2026" rental bond data,
Tenancy Services (tenancy.govt.nz).

Note: this is the Deliverable 4 version. The final pipeline does the same
cleaning (plus a Christchurch-only filter) in prepare_bonds() in rental_pipeline.py.

Run from the main repository folder:  python clean_bond.py

Column meanings (for the README):
- TimeFrame            : quarter start date (Jan/Apr/Jul/Oct) the row covers
- Location Id          : 2018 Statistical Area 2 (SA2) code. Two special,
                          non-geographic codes appear alongside real SA2s:
                          -99 = national ("All NZ") rollup total, and
                          blank/NaN = bonds that couldn't be geocoded to an SA2.
- Dwelling Type        : House / Apartment / Flat / Room / Boarding House,
                          or "ALL" for the combined total across types
- Number Of Beds       : 0-9, "5+", or "ALL" for the combined total
- Total Bonds          : NEW bonds lodged that quarter (flow)
- Active Bonds         : bonds currently active at quarter-end (stock)
- Closed Bonds         : bonds closed/ended that quarter (flow)
- Rent statistics (all weekly rent in NZ$, for each TimeFrame x Location x
Dwelling Type x Beds combination, based on new bonds lodged that quarter):
- Median Rent          : the actual middle weekly rent when all rents are
                          sorted; half the new bonds are below it, half above.
- Geometric Mean Rent  : multiply the rents together and take the nth root
                          (= exp(mean(log(rent)))). Tenancy Services uses it as
                          a smoother stand-in for the median: rents cluster at
                          round numbers, so the median plateaus for months,
                          while the geometric mean closely approximates the
                          median when rents are log-normally distributed.
- Upper Quartile Rent  : 75% of new bonds have a weekly rent at or below this.
- Lower Quartile Rent  : 25% of new bonds have a weekly rent at or below this.
- Log Std Dev Weekly Rent : standard deviation of the log rents; a measure of
                          how spread out rents are in relative terms.
Median Rent and the two quartile columns are actual values from the data;
only Geometric Mean Rent and Log Std Dev are derived.
All five are NULL where Tenancy Services suppressed them for privacy (very
few bonds in that cell).
"""

import pandas as pd

df = pd.read_csv("data/Detailed-Quarterly-Tenancy-Q1-2020-Q3-2026.csv")
n_start, c_start = df.shape
print(f"Starting shape: {df.shape}")

# ---------------------------------------------------------------------------
# 1. Filter TimeFrame to match the Airbnb dataset's window
# ---------------------------------------------------------------------------
# The Airbnb data covers Oct 2025 - Jun 2026 (monthly). This report is
# quarterly, so the matching quarters are the ones whose 3-month window
# overlaps that period: Q4 2025 (Oct-Dec), Q1 2026 (Jan-Mar), Q2 2026 (Apr-Jun).
df["TimeFrame"] = pd.to_datetime(df["TimeFrame"])
overlap_quarters = ["2025-10-01", "2026-01-01", "2026-04-01"]
n_before_time = len(df)
df = df[df["TimeFrame"].isin(pd.to_datetime(overlap_quarters))]
print(f"Filtered TimeFrame to {overlap_quarters} "
      f"-> dropped {n_before_time - len(df)} rows outside this window "
      f"({len(df)} remaining)")

# ---------------------------------------------------------------------------
# 2. Drop rows where Location Id is not a usable, specific area
# ---------------------------------------------------------------------------
# -99 is a national rollup (would double-count if summed alongside real
# areas next week); NaN Location Id means the bond couldn't be geocoded at
# all. Neither can be linked to a Christchurch neighbourhood, and together
# they're a small share of rows, so dropping them is low-cost and avoids
# silently corrupting next week's area-level comparison.
n_before_loc = len(df)
n_national = (df["Location Id"] == -99).sum()
n_unmatched = df["Location Id"].isna().sum()
df = df[(df["Location Id"] != -99) & df["Location Id"].notna()]
print(f"Dropped {n_national} national-rollup rows (Location Id == -99) and "
      f"{n_unmatched} unmatched rows (Location Id missing) "
      f"-> {n_before_loc - len(df)} rows removed, {len(df)} remaining")

df["Location Id"] = df["Location Id"].astype("int32")

# ---------------------------------------------------------------------------
# 3. Missing rent statistics -> leave as NaN (suppressed, not absent)
# ---------------------------------------------------------------------------
# These are genuine privacy suppressions from Tenancy Services (small cell
# sizes), not data-quality errors, so imputing a value would misrepresent
# the market. Total/Active/Closed Bonds are still valid for these rows and
# are kept, so volume-based analysis (e.g. "number of available properties")
# isn't affected even where rent stats are blank.
rent_cols = ["Median Rent", "Geometric Mean Rent", "Upper Quartile Rent",
             "Lower Quartile Rent", "Log Std Dev Weekly Rent"]
n_missing_rent = df["Median Rent"].isna().sum()
print(f"{n_missing_rent} of {len(df)} rows have suppressed rent statistics "
      f"-> left as NaN (not imputed); Total/Active/Closed Bonds still usable for these rows")

# ---------------------------------------------------------------------------
# 4. Dtype cleanup for space efficiency
# ---------------------------------------------------------------------------
df["Dwelling Type"] = df["Dwelling Type"].astype("category")
df["Number Of Beds"] = df["Number Of Beds"].astype("category")
for c in ["Total Bonds", "Active Bonds", "Closed Bonds"]:
    df[c] = df[c].astype("int32")
for c in rent_cols:
    df[c] = df[c].astype("float32")

# ---------------------------------------------------------------------------
# 5. Save — space efficient
# ---------------------------------------------------------------------------
df.to_parquet("bond_data_clean.parquet", index=False)

print(f"\nFinal shape: {df.shape} (started at {(n_start, c_start)})")
print(f"Columns kept: {df.columns.tolist()}")
