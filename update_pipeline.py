"""Rebuild Christchurch Airbnb cleaning, enrichment, analyses and reports in one call."""

from pathlib import Path
import argparse
import json
import shutil
import tempfile
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def prepare_data(config):
    """Read every original snapshot with identifiers preserved as strings."""
    required = {
        "id",
        "host_id",
        "neighbourhood_group",
        "latitude",
        "longitude",
        "room_type",
        "price",
        "last_review",
        "number_of_reviews",
        "reviews_per_month",
        "minimum_nights",
        "availability_365",
        "calculated_host_listings_count",
        "number_of_reviews_ltm",
    }
    frames = []
    seen_months = set()
    audit = []
    for item in config["snapshots"]:
        month = item["month"]
        pd.to_datetime(month, format="%Y-%m", errors="raise")
        if month in seen_months:
            raise ValueError(f"Duplicate snapshot month: {month}")
        seen_months.add(month)
        raw = pd.read_csv(
            ROOT / item["file"], dtype={"id": "string", "host_id": "string"}
        )
        missing = required - set(raw.columns)
        if missing:
            raise ValueError(f"Missing columns in {item['file']}: {sorted(missing)}")
        frame = raw.loc[raw.neighbourhood_group.eq(config["analysis"]["city"])].copy()
        if frame.empty:
            raise ValueError(f"No Christchurch rows in {item['file']}")
        for col in ["id", "host_id"]:
            if frame[col].isna().any() or not frame[col].str.fullmatch(r"[0-9]+").all():
                raise ValueError(f"{month}: {col} must contain intact integer text IDs")
        frame["month_year"] = month
        audit.append(
            {
                "month_year": month,
                "file": item["file"],
                "raw_rows": len(raw),
                "christchurch_rows": len(frame),
            }
        )
        frames.append(frame)
        print(f"Prepared {month}: {len(frame):,} Christchurch rows", flush=True)
    df = pd.concat(frames, ignore_index=True)
    if df.duplicated(["id", "month_year"]).any():
        raise ValueError("Duplicate id/month_year keys; check input snapshots.")
    numeric = [
        "price",
        "latitude",
        "longitude",
        "minimum_nights",
        "number_of_reviews",
        "reviews_per_month",
        "calculated_host_listings_count",
        "availability_365",
        "number_of_reviews_ltm",
    ]
    for col in numeric:
        text = (
            df[col]
            .astype("string")
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
        )
        converted = pd.to_numeric(text, errors="coerce")
        if (df[col].notna() & converted.isna()).any():
            raise ValueError(f"{col}: nonnumeric values require review")
        df[col] = converted
    if df[["latitude", "longitude"]].isna().any().any():
        raise ValueError("Missing coordinates require review before spatial enrichment")
    if (
        not df.latitude.between(-90, 90).all()
        or not df.longitude.between(-180, 180).all()
    ):
        raise ValueError("Invalid coordinates")
    original = df.last_review.astype("string")
    df["last_review"] = pd.to_datetime(
        original, format="%Y-%m-%d", errors="coerce"
    ).fillna(pd.to_datetime(original, format="%d/%m/%Y", errors="coerce"))
    if (original.notna() & df.last_review.isna()).any():
        raise ValueError("Invalid last_review dates require review")
    missing_dates = seen_months - set(config["reference_dates"])
    if missing_dates:
        raise ValueError(f"Missing reference dates: {sorted(missing_dates)}")
    df = df.sort_values(["month_year", "id"]).reset_index(drop=True)
    return df, pd.DataFrame(audit)


def clean_data(df):
    """Apply D4 cleaning while preserving coordinates at full precision."""
    clean = df.drop(
        columns=["name", "host_name", "license", "neighbourhood_group"], errors="ignore"
    ).copy()
    clean["price_missing"] = clean.price.isna()
    # Fill only when the observed review count supports the zero-review interpretation.
    no_reviews = clean.reviews_per_month.isna() & clean.number_of_reviews.eq(0)
    clean.loc[no_reviews, "reviews_per_month"] = 0
    return clean


def save_plot(path):
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def analyse(df, config, out):
    settings = config["analysis"]
    df.describe(include="all").to_csv(out / "summary_statistics.csv")
    df.isna().sum().rename("missing_count").to_csv(out / "missing_counts.csv")
    monthly = df.groupby("month_year").agg(
        listing_records=("id", "size"),
        distinct_listings=("id", "nunique"),
        available_prices=("price", "count"),
        missing_prices=("price_missing", "sum"),
    )
    monthly.to_csv(out / "monthly_counts.csv")
    ceiling = settings["plot_price_max"]
    prices = df.loc[df.price.le(ceiling)]
    plt.figure(figsize=(9, 5))
    plt.hist(prices.price.dropna(), bins=40, edgecolor="black", color="steelblue")
    plt.title(f"Price Distribution (Christchurch ≤ ${ceiling})")
    plt.xlabel("Price (NZD)")
    plt.ylabel("Number of listing-month records")
    save_plot(out / "01_price_distribution.png")
    means = prices.groupby("month_year").price.mean().reindex(monthly.index)
    means.rename("mean_price").to_csv(out / "monthly_mean_price.csv")
    plt.figure(figsize=(10, 5))
    means.plot(kind="bar", color="darkorange")
    plt.title(f"Average Price by Month (prices ≤ ${ceiling})")
    for i, value in enumerate(means):
        if pd.isna(value):
            plt.text(i, 5, "No price data", rotation=90, ha="center", fontsize=9)
    plt.xlabel("Month-Year")
    plt.ylabel("Average Price (NZD)")
    plt.xticks(rotation=45)
    save_plot(out / "02_average_price_by_month.png")
    reference = pd.to_datetime(
        df.month_year.map(config["reference_dates"]), format="%Y-%m-%d"
    )
    days = (reference - df.last_review).dt.days
    anomalies = df.loc[days.lt(0)].copy()
    anomalies["reference_date"] = reference[days.lt(0)]
    anomalies.to_csv(out / "reviews_after_reference_date.csv", index=False)
    maximum = settings["review_days_max"]
    recent = days[days.between(0, maximum)]
    plt.figure(figsize=(9, 5))
    plt.hist(recent.dropna(), bins=40, edgecolor="black", color="seagreen")
    plt.title(f"Days Since Last Review (0–{maximum} days)")
    plt.xlabel("Days Since Last Review")
    plt.ylabel("Number of listing-month records")
    plt.xlim(left=0)
    save_plot(out / "03_days_since_last_review.png")
    ranked = df.sort_values("number_of_reviews", ascending=False, kind="stable").copy()
    ranked["Rank"] = range(1, len(ranked) + 1)
    ranked.head(int(len(df) * settings["rank_fraction"])).to_csv(
        out / "top_reviewed_records.csv", index=False
    )
    monthly.listing_records.plot.bar(figsize=(10, 5), color="steelblue")
    plt.title("Christchurch listings by snapshot month")
    plt.ylabel("Listing records")
    plt.xlabel("Month-Year")
    plt.xticks(rotation=45)
    save_plot(out / "08_listings_by_month.png")
    return len(anomalies)


def write_report(df, rental, anomalies, out):
    """Generate a reviewable narrative from this run's results."""
    unavailable = ", ".join(rental["unavailable_bond_quarters"]) or "None"
    central = rental["central"]
    missing = df.groupby("month_year").price.apply(lambda s: s.isna().all())
    no_prices = ", ".join(missing[missing].index)
    text = f"""# Deliverable 7 — automated run report

The pipeline rebuilt {len(df):,} listing-month records across {df.month_year.nunique()} months
from the original plain listings.csv snapshots. Listing and host IDs were read as text;
no floating-point conversion was used. Listing titles and host names were removed.

Christchurch Central median Airbnb price: ${central['median_price']:g}/night,
using {central['listing_months']:,} priced listing-month records and
{central['distinct_listings']:,} distinct listings under the configured price rules.

The pandas and SQLite joins match across all selected validation columns:
{rental['matched_records']:,} matched records. Unavailable bond quarters in the supplied
bond file: {unavailable}. These quarters remain in the Airbnb summaries and coverage
tables but are excluded from matched bond comparisons. No bond values were invented.

Months with entirely missing prices in the original downloads: {no_prices}.
Prices were retained as missing and flagged. Their cause has not been established.
There were {anomalies:,} reviews after the configured reference dates; these were
exported for review and excluded from the days-since-review histogram. Reference dates
are inherited from the previous notebook and supplied July/August information and
must not be described as independently verified scrape dates.

Area queries pending or failed: {rental['pending_or_failed_points']}.
Offline mode: {rental['offline']}. Bedroom figures use an unverified room-type proxy,
not measured Airbnb bedrooms. All qualifying areas appear in the bedroom chart.
"""
    (out / "REPORT.md").write_text(text)


def run_pipeline(offline=False):
    config = json.loads((ROOT / "config.json").read_text())
    prepared, audit = prepare_data(config)
    df = clean_data(prepared)
    from rental_pipeline import run_rental_pipeline

    # Build privately; invalid inputs or failed required lookups leave published outputs intact.
    stage = Path(tempfile.mkdtemp(prefix=".pipeline-", dir=ROOT))
    try:
        rental = run_rental_pipeline(df, ROOT, config, stage, offline=offline)
        anomalies = analyse(df, config, stage)
        months = sorted(df.month_year.unique())
        stem = f"christchurch_listings_{months[0]}_to_{months[-1]}"
        df.to_csv(stage / f"{stem}.csv", index=False, date_format="%Y-%m-%d")
        df.to_parquet(stage / "airbnb_christchurch_clean.parquet", index=False)
        audit.to_csv(stage / "input_audit.csv", index=False)
        report = {
            "rows": len(df),
            "months": months,
            "id_storage": "text",
            "rebuilt_from_raw": True,
            "reviews_after_reference_date": anomalies,
            "status": "partial" if rental["pending_or_failed_points"] else "complete",
            "rental": rental,
        }
        (stage / "run_summary.json").write_text(json.dumps(report, indent=2))
        write_report(df, rental, anomalies, stage)
        out = ROOT / "output"
        backup = ROOT / ".output_previous"
        if backup.exists():
            shutil.rmtree(backup)
        if out.exists():
            out.rename(backup)
        try:
            stage.rename(out)
        except Exception:
            if backup.exists():
                backup.rename(out)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        print(f"Finished ({report['status']}): {len(df):,} records. Outputs: {out}")
        return df
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use cached codes; mark missing points as a partial run",
    )
    args = parser.parse_args()
    run_pipeline(offline=args.offline)
