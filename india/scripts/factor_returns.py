"""
Calculate rolling returns for Indian factor indices using Polars.
Uses ETFs that track these indices from NSE.
"""

import warnings
from datetime import datetime

import pandas as pd
import polars as pl
import yfinance as yf

warnings.filterwarnings("ignore")

# Verified working NSE ETF symbols
TICKERS = {
    # Momentum ETFs - KEY FOCUS
    "Nifty500 Momentum 50 ETF": "MOM50.NS",  # Nifty 500 Momentum 50
    "Nifty200 Momentum 30 ETF": "MOM30IETF.NS",  # Nifty 200 Momentum 30
    "Momentum 100 ETF": "MOM100.NS",
    "Momentum 50 (Alt)": "MOMENTUM50.NS",
    # Low Volatility ETFs - KEY FOCUS
    "Low Vol ETF": "LOWVOL.NS",
    "Low Vol ICICI ETF": "LOWVOLIETF.NS",
    # Alpha ETFs
    "Alpha ETF": "ALPHA.NS",
    "Alpha ETF (Nippon)": "ALPHAETF.NS",
    # Quality ETF
    "Quality 30 ETF": "QUAL30IETF.NS",
    # Value ETF
    "Nifty50 Value 20 ETF": "NV20.NS",
    # Midcap
    "Midcap 150 BEES": "MID150BEES.NS",
    # Benchmarks
    "Nifty 50 (NIFTYBEES)": "NIFTYBEES.NS",
    "Nifty Next 50": "JUNIORBEES.NS",
    "Nifty 50 Index": "^NSEI",
}


def fetch_price_data(ticker: str, period: str = "10y") -> pl.DataFrame | None:
    """Fetch historical price data using yfinance."""
    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if data.empty:
        return None

    # Flatten multi-index columns if present
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()

    df = pl.DataFrame(
        {
            "date": data["Date"].tolist(),
            "close": data["Close"].tolist(),
        }
    )
    return df


def calculate_returns(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate various return metrics."""
    df = df.sort("date")

    # Trading days
    td_1y = 252
    td_3y = 252 * 3
    td_5y = 252 * 5

    df = df.with_columns(
        [
            # 1 Year rolling return
            ((pl.col("close") / pl.col("close").shift(td_1y)) - 1).alias("return_1y"),
            # 3 Year rolling return (annualized)
            (((pl.col("close") / pl.col("close").shift(td_3y)) ** (1 / 3)) - 1).alias(
                "return_3y_ann"
            ),
            # 5 Year rolling return (annualized)
            (((pl.col("close") / pl.col("close").shift(td_5y)) ** (1 / 5)) - 1).alias(
                "return_5y_ann"
            ),
        ]
    )

    return df


def get_stats(df: pl.DataFrame, col: str) -> dict:
    """Get statistics for a return column."""
    valid = df.filter(pl.col(col).is_not_null())
    if valid.height == 0:
        return {"latest": None, "avg": None, "min": None, "max": None, "median": None}

    return valid.select(
        [
            pl.col(col).last().alias("latest"),
            pl.col(col).mean().alias("avg"),
            pl.col(col).min().alias("min"),
            pl.col(col).max().alias("max"),
            pl.col(col).median().alias("median"),
        ]
    ).to_dicts()[0]


def fmt(val, pct=True):
    """Format value as percentage or N/A."""
    if val is None:
        return "N/A"
    return f"{val * 100:.1f}%" if pct else f"{val:.2f}"


def sort_by_metric(results: dict, metric_key: str) -> list[tuple[str, dict]]:
    return sorted(
        results.items(),
        key=lambda x: x[1][metric_key].get("avg") or -999,
        reverse=True,
    )


def print_table(
    results: dict, title: str, metric_key: str, note: str = ""
) -> list[tuple[str, dict]]:
    print(f"\n{'=' * 100}")
    print(title)
    if note:
        print(note)
    print(f"{'=' * 100}")
    header = (
        f"{'Index':<28} {'Latest':>10} {'Average':>10} {'Min':>10} {'Max':>10} "
        f"{'Median':>10}"
    )
    print(header)
    print("-" * 100)

    sorted_results = sort_by_metric(results, metric_key)
    for name, data in sorted_results:
        stats = data[metric_key]
        if stats.get("avg") is not None:
            print(
                f"{name:<28} {fmt(stats['latest']):>10} {fmt(stats['avg']):>10} "
                f"{fmt(stats['min']):>10} {fmt(stats['max']):>10} "
                f"{fmt(stats['median']):>10}"
            )
    return sorted_results


def main():
    print("=" * 100)
    print("INDIAN FACTOR INDICES - ROLLING RETURNS ANALYSIS")
    print(f"Data as of: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 100)

    results = {}

    for name, ticker in TICKERS.items():
        print(f"Fetching: {name}...", end=" ")
        df = fetch_price_data(ticker, period="10y")

        if df is None or df.height < 252:
            print("⚠ Insufficient data")
            continue

        df = calculate_returns(df)

        results[name] = {
            "ticker": ticker,
            "data_points": df.height,
            "return_1y": get_stats(df, "return_1y"),
            "return_3y": get_stats(df, "return_3y_ann"),
            "return_5y": get_stats(df, "return_5y_ann"),
        }

        print(f"✓ {df.height} days")

    sorted_results = print_table(
        results,
        "5-YEAR ROLLING RETURNS (ANNUALIZED) - What matters for long-term investing",
        "return_5y",
    )
    print_table(results, "3-YEAR ROLLING RETURNS (ANNUALIZED)", "return_3y")
    print_table(results, "1-YEAR ROLLING RETURNS (ABSOLUTE)", "return_1y")

    # Summary comparison
    print(f"\n{'=' * 100}")
    print("SUMMARY: LATEST RETURNS COMPARISON (Sorted by 5Y)")
    print(f"{'=' * 100}")
    print(f"{'Index':<28} {'1Y':>12} {'3Y Ann':>12} {'5Y Ann':>12} {'Data Days':>12}")
    print("-" * 100)

    for name, data in sorted_results:
        r1 = fmt(data["return_1y"].get("latest"))
        r3 = fmt(data["return_3y"].get("latest"))
        r5 = fmt(data["return_5y"].get("latest"))
        days = data["data_points"]

        print(f"{name:<28} {r1:>12} {r3:>12} {r5:>12} {days:>12}")


if __name__ == "__main__":
    main()
