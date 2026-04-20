"""
Calculate 3-year rolling returns using mfapi.in for Indian mutual funds.
"""

import warnings
from datetime import datetime

import httpx
import polars as pl

warnings.filterwarnings("ignore")

# mfapi.in scheme codes for Direct Growth plans
FUNDS = {
    # === ACTIVE FUNDS (long history) ===
    "PPFAS Flexi Cap": 122639,
    "Quant Small Cap": 120828,
    "Quant Mid Cap": 120841,
    "Nippon Small Cap": 118778,
    "HDFC Mid Cap": 118989,
    "SBI Contra": 120578,
    "Motilal Oswal Midcap": 127042,
    "ICICI Pru Value Discovery": 120594,
    "JM Flexicap": 120492,
    # === BENCHMARK ===
    "UTI Nifty 50": 120716,
    # === MOMENTUM FACTOR ===
    "Nippon N500 Mom50": 152881,  # Nifty 500 Momentum 50
    "Motilal N500 Mom50": 152875,  # Nifty 500 Momentum 50
    "UTI N200 Mom30": 148703,  # Nifty 200 Momentum 30
    "Tata Midcap150 Mom50": 150738,  # Nifty Midcap 150 Momentum 50
    # === VALUE FACTOR ===
    "UTI N500 Value50": 151739,  # Nifty 500 Value 50
    "Nippon N50 Value20": 148721,  # Nifty 50 Value 20
    # === QUALITY FACTOR ===
    "UTI N200 Quality30": 152859,  # Nifty 200 Quality 30
    "Nippon N500 Quality50": 153470,  # Nifty 500 Quality 50
    # === LOW VOLATILITY FACTOR ===
    "ICICI N100 LowVol30": 148822,  # Nifty 100 Low Vol 30
    "Kotak N100 LowVol30": 152663,  # Nifty 100 Low Vol 30
    # === MULTI-FACTOR (Alpha + Low Vol) ===
    "ICICI Alpha LowVol30": 149158,  # Nifty Alpha Low Vol 30
    "Nippon Alpha LowVol30": 150487,  # Nifty Alpha Low Vol 30
    "UTI Alpha LowVol30": 153086,  # Nifty Alpha Low Vol 30
}


def fetch_nav_data(scheme_code: int) -> pl.DataFrame | None:
    """Fetch NAV history from mfapi.in."""
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    try:
        resp = httpx.get(url, timeout=30)
        data = resp.json()

        if "data" not in data or not data["data"]:
            return None

        records = []
        for item in data["data"]:
            try:
                date = datetime.strptime(item["date"], "%d-%m-%Y")
                nav = float(item["nav"])
                records.append({"date": date, "nav": nav})
            except (KeyError, ValueError):
                continue

        if not records:
            return None

        df = pl.DataFrame(records)
        return df.sort("date")
    except Exception as e:
        print(f"  Error: {e}")
        return None


def calc_rolling_returns(df: pl.DataFrame, years: int = 3) -> pl.DataFrame:
    """Calculate rolling returns."""
    # Approximate trading days
    days = years * 252

    df = df.with_columns(
        [
            (((pl.col("nav") / pl.col("nav").shift(days)) ** (1 / years)) - 1).alias(
                f"return_{years}y"
            ),
        ]
    )
    return df


def get_stats(df: pl.DataFrame, col: str) -> dict | None:
    """Get rolling return statistics."""
    valid = df.filter(pl.col(col).is_not_null())
    if valid.height < 100:  # Need meaningful sample
        return None

    return valid.select(
        [
            pl.col(col).last().alias("latest"),
            pl.col(col).mean().alias("avg"),
            pl.col(col).min().alias("min"),
            pl.col(col).max().alias("max"),
            pl.col(col).median().alias("median"),
            pl.col(col).quantile(0.25).alias("p25"),
            pl.col(col).quantile(0.75).alias("p75"),
        ]
    ).to_dicts()[0]


def fmt(val):
    return f"{val * 100:.1f}%" if val is not None else "N/A"


def sort_by_stat(results: dict, key: str) -> list[tuple[str, dict]]:
    return sorted(
        results.items(),
        key=lambda x: x[1]["stats"][key] if x[1]["stats"][key] else -999,
        reverse=True,
    )


def main():
    print("=" * 120)
    print("3-YEAR ROLLING RETURNS ANALYSIS (Using mfapi.in NAV Data)")
    print(f"Data as of: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 120)

    results = {}

    for name, code in FUNDS.items():
        print(f"Fetching: {name} (code: {code})...", end=" ")
        df = fetch_nav_data(code)

        if df is None:
            print("⚠ No data")
            continue

        print(f"✓ {df.height} NAV records, ", end="")

        # Date range
        min_date = df["date"].min()
        max_date = df["date"].max()
        print(f"{min_date.strftime('%Y-%m')} to {max_date.strftime('%Y-%m')}")

        df = calc_rolling_returns(df, years=3)
        stats = get_stats(df, "return_3y")

        if stats is None:
            print("  ⚠ Insufficient history for 3Y rolling")
            continue

        results[name] = {
            "code": code,
            "nav_count": df.height,
            "stats": stats,
            "start_date": min_date,
        }

    # Print results sorted by average return
    print(f"\n{'=' * 120}")
    print("3-YEAR ROLLING RETURNS - SORTED BY AVERAGE (Highest to Lowest)")
    print(f"{'=' * 120}")
    header = (
        f"{'Fund':<28} {'Latest':>9} {'Average':>9} {'Median':>9} "
        f"{'P25':>9} {'P75':>9} {'Min':>9} {'Max':>9}"
    )
    print(header)
    print("-" * 120)

    sorted_results = sort_by_stat(results, "avg")

    for name, data in sorted_results:
        s = data["stats"]
        print(
            f"{name:<28} {fmt(s['latest']):>9} {fmt(s['avg']):>9} "
            f"{fmt(s['median']):>9} {fmt(s['p25']):>9} {fmt(s['p75']):>9} "
            f"{fmt(s['min']):>9} {fmt(s['max']):>9}"
        )

    # Downside protection view
    print(f"\n{'=' * 120}")
    print("DOWNSIDE PROTECTION VIEW (Sorted by Minimum 3Y Return - Best to Worst)")
    print(f"{'=' * 120}")
    print(f"{'Fund':<28} {'Min 3Y':>12} {'P25':>12} {'Avg':>12} {'Max':>12}")
    print("-" * 120)

    sorted_by_min = sort_by_stat(results, "min")

    for name, data in sorted_by_min:
        s = data["stats"]
        print(
            f"{name:<28} {fmt(s['min']):>12} {fmt(s['p25']):>12} "
            f"{fmt(s['avg']):>12} {fmt(s['max']):>12}"
        )

    # Summary recommendation
    print(f"\n{'=' * 120}")
    print("SUMMARY: KEY METRICS COMPARISON")
    print(f"{'=' * 120}")

    print("\n🏆 HIGHEST AVERAGE 3Y ROLLING:")
    top3_avg = sorted_results[:3]
    for i, (name, data) in enumerate(top3_avg, 1):
        print(f"   {i}. {name}: {fmt(data['stats']['avg'])} avg")

    print("\n🛡️ BEST DOWNSIDE PROTECTION (Highest Min):")
    top3_min = sorted_by_min[:3]
    for i, (name, data) in enumerate(top3_min, 1):
        print(f"   {i}. {name}: {fmt(data['stats']['min'])} worst case")

    print("\n📊 MOST CONSISTENT (Tightest P25-P75 Range):")
    consistency = [
        (name, data, data["stats"]["p75"] - data["stats"]["p25"])
        for name, data in results.items()
        if data["stats"]["p75"] and data["stats"]["p25"]
    ]
    consistency.sort(key=lambda x: x[2])
    for i, (name, _data, spread) in enumerate(consistency[:3], 1):
        print(f"   {i}. {name}: {fmt(spread)} spread (P25-P75)")


if __name__ == "__main__":
    main()
