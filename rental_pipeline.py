"""Cached spatial enrichment, quarterly bond joins and Deliverable 5 outputs."""

import os
import json
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import urllib.request
import urllib.parse
import urllib.error
import matplotlib.pyplot as plt


def query_point(point, key, config):
    """Retry transient failures; reject authentication failures immediately."""
    lat, lon = point
    layer = config["layer"]
    for attempt in range(config["attempts"]):
        try:
            parameters = {
                "key": key,
                "layer": layer,
                "x": lon,
                "y": lat,
                "max_results": config["max_results"],
                "radius": config["radius"],
                "geometry": "false",
            }
            url = config["query_url"] + "?" + urllib.parse.urlencode(parameters)
            with urllib.request.urlopen(
                url, timeout=config["timeout_seconds"]
            ) as response:
                payload = json.load(response)
            features = payload["vectorQuery"]["layers"][str(layer)]["features"]
            if not features:
                return point, None, "no_feature"
            return point, int(features[0]["properties"][config["code_field"]]), "found"
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise ValueError(
                    "API authentication rejected. Check the key and query_url domain in config.json."
                ) from None
            if error.code not in (408, 429) and error.code < 500:
                raise ValueError(
                    f"API rejected the request (HTTP {error.code}); check layer and endpoint settings."
                ) from None
        except (urllib.error.URLError, KeyError, ValueError, TypeError, TimeoutError):
            pass
        if attempt + 1 < config["attempts"]:
            time.sleep(attempt + 1)
    return point, None, "request_or_response_failed"


def enrich(air, root, config, offline):
    cache_path = root / config["cache"]
    cache = pd.read_csv(cache_path)
    for c in ["latitude", "longitude", "area_code"]:
        cache[c] = pd.to_numeric(cache[c], errors="coerce")
    cache["lat_k"] = cache.latitude.round(6)
    cache["lon_k"] = cache.longitude.round(6)
    cache = cache.dropna(subset=["lat_k", "lon_k", "area_code"])
    conflicts = cache.groupby(["lat_k", "lon_k"]).area_code.nunique()
    if (conflicts > 1).any():
        raise ValueError("Conflicting cached area codes for the same rounded point")
    cache = cache.drop_duplicates(["lat_k", "lon_k"])
    air = air.copy()
    air["lat_k"] = air.latitude.round(6)
    air["lon_k"] = air.longitude.round(6)
    points = set(map(tuple, air[["lat_k", "lon_k"]].dropna().drop_duplicates().values))
    done = set(map(tuple, cache[["lat_k", "lon_k"]].values))
    pending = sorted(points - done)
    print(
        f"Area-code cache: {len(done):,} points; new lookups: {len(pending)}",
        flush=True,
    )
    failures = []
    if pending and not offline:
        key = os.environ.get("KOORDINATES_API_KEY", "").strip()
        key_path = root / "koordinates_key.txt"
        if not key and key_path.exists():
            key = key_path.read_text().strip()
        if not key:
            raise ValueError(
                "Place your API key in koordinates_key.txt locally, or set KOORDINATES_API_KEY. Use --offline for a clearly marked partial run."
            )
        # Authenticate one point before scheduling the remainder.
        first = query_point(pending[0], key, config)
        if first[1] is None:
            raise ValueError(
                f"First required area lookup failed ({first[2]}). Outputs unchanged."
            )
        results = cache[["latitude", "longitude", "area_code"]].to_dict("records")
        results.append(
            {"latitude": first[0][0], "longitude": first[0][1], "area_code": first[1]}
        )
        with ThreadPoolExecutor(max_workers=config["workers"]) as pool:
            futures = [
                pool.submit(query_point, point, key, config) for point in pending[1:]
            ]
            for i, future in enumerate(as_completed(futures), 2):
                point, code, status = future.result()
                if code is None:
                    failures.append(
                        {"latitude": point[0], "longitude": point[1], "status": status}
                    )
                else:
                    results.append(
                        {"latitude": point[0], "longitude": point[1], "area_code": code}
                    )
                if i % 25 == 0 or i == len(pending):
                    print(
                        f"Area-code queries completed: {i}/{len(pending)}", flush=True
                    )
        if failures:
            raise ValueError(
                f"{len(failures)} required area lookups failed. Outputs unchanged; retry or explicitly use --offline."
            )
        cache = pd.DataFrame(results)
        temp = cache_path.with_suffix(".tmp")
        cache.to_csv(temp, index=False)
        temp.replace(cache_path)
        cache["lat_k"] = cache.latitude.round(6)
        cache["lon_k"] = cache.longitude.round(6)
    elif offline:
        failures = [
            {"latitude": p[0], "longitude": p[1], "status": "offline_pending"}
            for p in pending
        ]
    air = air.merge(
        cache[["lat_k", "lon_k", "area_code"]],
        on=["lat_k", "lon_k"],
        how="left",
        validate="many_to_one",
    )
    if air.empty:
        raise ValueError("Spatial enrichment produced no rows")
    return air, pd.DataFrame(failures, columns=["latitude", "longitude", "status"])


def prepare_bonds(air, root, config, out):
    lookup = pd.read_csv(root / config["lookup"])
    bond = pd.read_csv(root / config["bond_raw"], na_values=["NULL"])
    bond["TimeFrame"] = pd.to_datetime(bond["TimeFrame"], errors="raise")
    bond["period"] = bond.TimeFrame.dt.to_period("Q").astype(str)
    bond["Location Id"] = pd.to_numeric(bond["Location Id"], errors="coerce")
    air["period"] = pd.to_datetime(air.month_year + "-01").dt.to_period("Q").astype(str)
    periods = set(air.period)
    bond = bond.loc[
        bond.period.isin(periods) & bond["Location Id"].isin(lookup.sa2_code)
    ].copy()
    for c in [
        "Total Bonds",
        "Active Bonds",
        "Closed Bonds",
        "Median Rent",
        "Geometric Mean Rent",
        "Upper Quartile Rent",
        "Lower Quartile Rent",
        "Log Std Dev Weekly Rent",
    ]:
        bond[c] = pd.to_numeric(bond[c], errors="raise")
    bond["Number Of Beds"] = bond["Number Of Beds"].fillna("Unknown")
    bond.to_csv(out / "bond_data_clean.csv", index=False)
    bond.to_parquet(out / "bond_data_clean.parquet", index=False)
    all_rows = bond.loc[
        bond["Dwelling Type"].eq("ALL") & bond["Number Of Beds"].eq("ALL")
    ].copy()
    if all_rows.duplicated(["Location Id", "period"]).any():
        raise ValueError("Duplicate ALL/ALL bond totals for an area/quarter")
    bond_one = all_rows[
        ["Location Id", "period", "Median Rent", "Active Bonds"]
    ].rename(columns={"Median Rent": "median_rent", "Active Bonds": "active_bonds"})
    bond_one["rent_per_night"] = bond_one.median_rent / 7
    left = air.merge(
        bond_one,
        left_on=["area_code", "period"],
        right_on=["Location Id", "period"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    inner = left.loc[left["_merge"].eq("both")].drop(columns="_merge").copy()
    left["bond_match_status"] = left["_merge"].astype(str)
    left = left.drop(columns="_merge")
    left.to_csv(out / "airbnb_bond_left_join.csv", index=False)
    inner.to_csv(out / "airbnb_bond_inner_join.csv", index=False)
    coverage = left.groupby("month_year").agg(
        records=("id", "size"),
        area_codes=("area_code", "count"),
        bond_matches=("Location Id", "count"),
        published_rents=("median_rent", "count"),
    )
    coverage.to_csv(out / "monthly_join_coverage.csv")
    return air, bond, bond_one, lookup, inner, left


def savefig(out, name):
    plt.tight_layout()
    plt.savefig(out / name, dpi=160)
    plt.close()


def rental_analysis(air, bond, bond_one, lookup, inner, out, settings):
    prices = air.loc[
        air.area_code.eq(settings["central_area"])
        & air.price.gt(settings["comparison_price_min"])
        & air.price.lt(settings["comparison_price_max"])
    ]
    central = {
        "area_code": settings["central_area"],
        "median_price": None if prices.empty else float(prices.price.median()),
        "listing_months": len(prices),
        "distinct_listings": prices.id.nunique(),
    }
    (out / "central_summary.json").write_text(json.dumps(central, indent=2))
    gap = inner.loc[
        inner.price.gt(settings["comparison_price_min"])
        & inner.price.lt(settings["comparison_price_max"])
        & inner.rent_per_night.notna()
    ].copy()
    gap["gap"] = gap.price - gap.rent_per_night
    minimum = settings["gap_min_records"]
    stats = (
        gap.groupby("area_code")
        .agg(
            median_gap=("gap", "median"), n=("gap", "size"), listings=("id", "nunique")
        )
        .query("n >= @minimum")
        .sort_values("median_gap", ascending=False)
        .reset_index()
    )
    stats = stats.merge(
        lookup,
        left_on="area_code",
        right_on="sa2_code",
        how="left",
        validate="many_to_one",
    )
    stats.to_csv(out / "gap_by_area.csv", index=False)
    top = stats.head(settings["gap_top_areas"])
    if not top.empty:
        names = top.sa2_name.fillna(top.area_code.astype(str))
        plt.figure(figsize=(11, 5))
        plt.bar(names, top.median_gap, color="#2c6e49")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Median gap (NZD/night)")
        plt.title("Largest Airbnb premiums — matched quarters only")
        savefig(out, "04_gap_median_bar.png")
        plt.figure(figsize=(11, 5))
        plt.boxplot(
            [gap.loc[gap.area_code.eq(a), "gap"] for a in top.area_code],
            showfliers=False,
        )
        plt.xticks(range(1, len(names) + 1), names, rotation=30, ha="right")
        plt.axhline(0, color="grey")
        plt.ylabel("Airbnb minus bond weekly rent / 7 (NZD/night)")
        plt.title("Gap distribution — matched quarters only")
        savefig(out, "05_gap_distribution_box.png")
    # Quarter table includes new Airbnb counts, leaving unavailable bonds missing.
    counts = (
        air.dropna(subset=["area_code"])
        .drop_duplicates(["id", "period"])
        .groupby(["area_code", "period"])
        .size()
        .rename("n_airbnb_listings")
        .reset_index()
    )
    counts = counts.merge(
        bond_one,
        left_on=["area_code", "period"],
        right_on=["Location Id", "period"],
        how="outer",
        validate="one_to_one",
    )
    counts["area_code"] = counts.area_code.fillna(counts["Location Id"])
    counts = counts.merge(
        lookup,
        left_on="area_code",
        right_on="sa2_code",
        how="left",
        validate="many_to_one",
    )
    counts.to_csv(out / "listings_and_bonds_by_quarter.csv", index=False)
    available = counts.loc[counts.period.isin(bond_one.period.unique())]
    typical = (
        available.groupby("area_code")
        .agg(
            n_airbnb_listings=("n_airbnb_listings", "median"),
            n_active_bonds=("active_bonds", "median"),
        )
        .reset_index()
        .merge(lookup, left_on="area_code", right_on="sa2_code", how="left")
        .sort_values("n_airbnb_listings", ascending=False)
    )
    typical["display_name"] = typical.sa2_name.fillna(
        "SA2 " + typical.area_code.astype("Int64").astype(str)
    )
    typical.to_csv(out / "typical_quarter_counts.csv", index=False)
    topc = typical.head(settings["count_top_areas"]).set_index("display_name")[
        ["n_airbnb_listings", "n_active_bonds"]
    ]
    if not topc.empty:
        topc.plot.bar(figsize=(12, 6))
        plt.xticks(rotation=35, ha="right")
        plt.ylabel("Typical quarter count")
        plt.xlabel("Area")
        plt.legend(["Airbnb listings", "Active rental bonds"])
        for position, value in enumerate(topc.n_active_bonds):
            if pd.isna(value):
                plt.text(
                    position + 0.12,
                    10,
                    "No bond match",
                    rotation=90,
                    fontsize=8,
                    ha="center",
                )
        plt.title("Airbnb listings and active bonds — quarters with bond data")
        savefig(out, "06_listings_vs_active_bonds.png")
    with sqlite3.connect(out / "christchurch_housing.db") as conn:
        air.to_sql("airbnb", conn, if_exists="replace", index=False)
        bond_one.to_sql("bond", conn, if_exists="replace", index=False)
        sql = pd.read_sql_query(
            'SELECT a.*,b."Location Id",b.median_rent,b.active_bonds,b.rent_per_night FROM airbnb a INNER JOIN bond b ON a.area_code=b."Location Id" AND a.period=b.period',
            conn,
        )
    cols = list(inner.columns)
    sql["id"] = sql["id"].astype("string")
    sql["host_id"] = sql["host_id"].astype("string")
    sql["last_review"] = pd.to_datetime(sql["last_review"])
    sql = sql.astype(inner[cols].dtypes.to_dict())
    pd.testing.assert_frame_equal(
        sql[cols].sort_values(["month_year", "id"]).reset_index(drop=True),
        inner[cols].sort_values(["month_year", "id"]).reset_index(drop=True),
        check_dtype=True,
    )
    return central, len(inner)


def run_rental_pipeline(df, root, config, out, offline=False):
    cfg = config["rental"]
    air, failures = enrich(df, root, cfg, offline)
    air.to_csv(out / "Airbnb_with_sa2.csv", index=False)
    failures.to_csv(out / "pending_or_failed_area_queries.csv", index=False)
    air, bond, bond_one, lookup, inner, left = prepare_bonds(air, root, cfg, out)
    central, njoin = rental_analysis(
        air, bond, bond_one, lookup, inner, out, config["analysis"]
    )
    # Retain the original optional room-type bedroom proxy, explicitly labelled.
    run_bed_proxy(air, bond, lookup, out, config["analysis"])
    report = {
        "offline": offline,
        "uncoded_records": int(air.area_code.isna().sum()),
        "pending_or_failed_points": len(failures),
        "matched_records": njoin,
        "sql_pandas_values_match": True,
        "bond_quarters": sorted(bond_one.period.unique().tolist()),
        "unavailable_bond_quarters": sorted(set(air.period) - set(bond_one.period)),
        "central": central,
    }
    (out / "rental_run_summary.json").write_text(json.dumps(report, indent=2))
    print(
        f"Rental analysis finished: {njoin:,} matched records; {len(failures)} pending/failed points.",
        flush=True,
    )
    return report


def run_bed_proxy(air, bond, lookup, out, settings):
    air = air.loc[air.period.isin(bond.period.unique())].copy()
    MIN_BOND_COVERAGE = settings["bed_min_coverage"]
    MIN_LISTINGS_PER_QUARTER = settings["bed_min_listings"]
    room_type_bed_proxy = settings["bed_proxy"]
    air["approx_beds"] = air["room_type"].map(room_type_bed_proxy).fillna(1)

    # Airbnb side: count each listing ONCE per quarter (the panel has one row per
    # listing per month), take the MEAN bedrooms per listing in each area/quarter
    # (typical property size, not total volume), then the median quarter.
    air_by_quarter = air.drop_duplicates(["id", "period"]).groupby(
        ["area_code", "period"]
    )["approx_beds"]
    mean_airbnb_beds_per_area = (
        air_by_quarter.mean()
        .groupby("area_code")
        .median()
        .rename("mean_airbnb_bedrooms")
    )
    airbnb_listings_per_quarter = (
        air_by_quarter.size()
        .groupby("area_code")
        .median()
        .rename("airbnb_listings_per_quarter")
    )

    # Bond side: use the actual bed-count breakdown (excluding the "ALL" rollup row
    # so we don't double count). "5+" counted as 5, so this is a lower bound.
    bond_by_beds = bond[bond["Dwelling Type"].astype(str).str.upper() == "ALL"].copy()
    bond_by_beds = bond_by_beds[
        bond_by_beds["Number Of Beds"].astype(str).str.upper() != "ALL"
    ]
    bond_by_beds["period"] = (
        pd.to_datetime(bond_by_beds["TimeFrame"]).dt.to_period("Q").astype(str)
    )
    bond_by_beds["beds_n"] = pd.to_numeric(
        bond_by_beds["Number Of Beds"].astype(str).str.rstrip("+"), errors="coerce"
    )
    bond_by_beds["bedrooms"] = bond_by_beds["beds_n"] * bond_by_beds["Active Bonds"]

    # Rows with a blank bed count (unknown bedrooms) cannot contribute to an average, so
    # they are excluded from BOTH the numerator and the denominator. Keeping them in the
    # denominator only made some areas look like they had 0 bedrooms.
    n_unknown_beds = bond_by_beds["beds_n"].isna().sum()
    bond_known_beds = bond_by_beds.dropna(subset=["beds_n", "Active Bonds"])
    print(
        f"Excluded {n_unknown_beds} bond rows with an unknown bed count from the bedroom mean."
    )

    by_area_quarter = bond_known_beds.groupby(["Location Id", "period"])[
        ["bedrooms", "Active Bonds"]
    ].sum()
    by_area_quarter["mean_beds"] = (
        by_area_quarter["bedrooms"] / by_area_quarter["Active Bonds"]
    )

    # Coverage = share of the area's total active bonds (from the ALL/ALL row) that have a
    # published bed count. Low coverage means the mean would reflect only whichever
    # categories survived Tenancy Services' privacy suppression.
    all_bonds = (
        bond[
            (bond["Dwelling Type"].astype(str).str.upper() == "ALL")
            & (bond["Number Of Beds"].astype(str).str.upper() == "ALL")
        ]
        .assign(
            period=lambda d: pd.to_datetime(d["TimeFrame"])
            .dt.to_period("Q")
            .astype(str)
        )
        .set_index(["Location Id", "period"])["Active Bonds"]
    )
    by_area_quarter["coverage"] = by_area_quarter["Active Bonds"] / all_bonds
    n_before = by_area_quarter.index.get_level_values("Location Id").nunique()
    by_area_quarter = by_area_quarter[by_area_quarter["coverage"] >= MIN_BOND_COVERAGE]
    n_after = by_area_quarter.index.get_level_values("Location Id").nunique()
    print(
        f"Bond coverage filter (>= {MIN_BOND_COVERAGE:.0%}): {n_before} -> {n_after} areas."
    )

    mean_long_term_beds_per_area = (
        by_area_quarter["mean_beds"]
        .groupby("Location Id")
        .median()
        .rename("mean_long_term_bedrooms")
    )

    bed_comparison = pd.concat(
        [
            mean_airbnb_beds_per_area,
            airbnb_listings_per_quarter,
            mean_long_term_beds_per_area,
        ],
        axis=1,
    ).dropna()
    bed_comparison = bed_comparison[
        bed_comparison["airbnb_listings_per_quarter"] >= MIN_LISTINGS_PER_QUARTER
    ]
    bed_comparison = bed_comparison.merge(
        lookup, left_index=True, right_on="sa2_code", how="left"
    ).set_index("sa2_code")
    bed_comparison["size_diff"] = (
        bed_comparison["mean_airbnb_bedrooms"]
        - bed_comparison["mean_long_term_bedrooms"]
    )
    bed_comparison = bed_comparison.sort_values("size_diff", ascending=False)
    bed_comparison.to_csv(out / "bedroom_proxy_comparison.csv")
    plot_df = bed_comparison.sort_values("size_diff")
    plot_df["display_name"] = plot_df.sa2_name.fillna(
        pd.Series("SA2 " + plot_df.index.astype(str), index=plot_df.index)
    )
    if not plot_df.empty:
        plt.figure(figsize=(10, max(5, 0.3 * len(plot_df) + 2)))
        colors = ["#c0392b" if value < 0 else "#2874a6" for value in plot_df.size_diff]
        plt.barh(plot_df["display_name"], plot_df["size_diff"], color=colors)
        plt.axvline(0, color="black")
        plt.xlabel("Room-type bedroom proxy minus bond mean bedrooms")
        plt.title("Illustrative bedroom proxy — unverified Airbnb assumption")
        savefig(out, "07_bedroom_proxy_difference.png")
