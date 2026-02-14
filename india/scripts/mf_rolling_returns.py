"""
Calculate 3-year rolling returns for Indian mutual funds and factor indices.
Uses yfinance for ETFs and index data.
"""

import warnings
from datetime import datetime

import pandas as pd
import polars as pl
import yfinance as yf

warnings.filterwarnings("ignore")

# Mutual Fund ETFs and indices available on yfinance
TICKERS = {
    # Factor Index ETFs
    "Midcap150 Momentum 50": "MOM50.NS",
    "Nifty200 Momentum 30": "MOM30IETF.NS",
    "Momentum 100": "MOM100.NS",
    "Low Vol ICICI": "LOWVOLIETF.NS",
    "Alpha ETF": "ALPHA.NS",
    "Quality 30": "QUAL30IETF.NS",
    # Midcap ETFs
    "Midcap 150 BEES": "MID150BEES.NS",
    # Benchmarks
    "Nifty 50": "NIFTYBEES.NS",
    "Nifty Next 50": "JUNIORBEES.NS",
    # Note: Active MF NAVs not on yfinance, using proxies where available
}

# Additional tickers to try for active funds (some may work)
ACTIVE_FUND_TICKERS = {
    "HDFC Mid Cap Opp": "0P0000XVLV.BO",  # BSE fund code
    "Nippon Small Cap": "0P0000XW34.BO",
    "SBI Contra": "0P0000XW9I.BO",
    "PPFAS Flexi Cap": "0P0001BAU7.BO",
    "Motilal Midcap": "0P0001699L.BO",
    "Quant Small Cap": "0P0000XVMS.BO",
}


def fetch_data(ticker: str, period: str = "10y") -> pl.DataFrame | None:
    """Fetch historical price data."""
    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if data.empty or len(data) < 100:
        return None

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    return pl.DataFrame(
        {
            "date": data["Date"].tolist(),
            "close": data["Close"].tolist(),
        }
    )


def calc_rolling_returns(df: pl.DataFrame) -> pl.DataFrame:
    """Calculate 3-year rolling returns."""
    df = df.sort("date")
    td_3y = 252 * 3  # 3 years of trading days

    df = df.with_columns(
        [
            (((pl.col("close") / pl.col("close").shift(td_3y)) ** (1 / 3)) - 1).alias(
                "return_3y"
            ),
        ]
    )
    return df


def get_stats(df: pl.DataFrame) -> dict:
    """Get rolling return statistics."""
    valid = df.filter(pl.col("return_3y").is_not_null())
    if valid.height == 0:
        return None

    return valid.select(
        [
            pl.col("return_3y").last().alias("latest"),
            pl.col("return_3y").mean().alias("avg"),
            pl.col("return_3y").min().alias("min"),
            pl.col("return_3y").max().alias("max"),
            pl.col("return_3y").median().alias("median"),
            pl.col("return_3y").std().alias("std"),
        ]
    ).to_dicts()[0]


def fmt(val):
    return f"{val * 100:.1f}%" if val is not None else "N/A"


def sort_by_avg(results: dict) -> list[tuple[str, dict]]:
    return sorted(
        results.items(),
        key=lambda x: x[1]["stats"]["avg"] if x[1]["stats"]["avg"] else -999,
        reverse=True,
    )


def main():
    print("=" * 110)
    print("3-YEAR ROLLING RETURNS ANALYSIS (ANNUALIZED)")
    print(f"Data as of: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 110)

    all_tickers = {**TICKERS, **ACTIVE_FUND_TICKERS}
    results = {}

    for name, ticker in all_tickers.items():
        print(f"Fetching: {name}...", end=" ")
        df = fetch_data(ticker, period="10y")

        if df is None:
            print("⚠ No data")
            continue

        df = calc_rolling_returns(df)
        stats = get_stats(df)

        if stats is None:
            print("⚠ Insufficient history")
            continue

        results[name] = {
            "ticker": ticker,
            "days": df.height,
            "stats": stats,
        }
        print(f"✓ {df.height} days")

    # Print results sorted by average return
    print(f"\n{'=' * 110}")
    print("3-YEAR ROLLING RETURNS - SORTED BY AVERAGE (Best to Worst)")
    print(f"{'=' * 110}")
    header = (
        f"{'Fund/Index':<25} {'Latest':>10} {'Average':>10} {'Median':>10} "
        f"{'Min':>10} {'Max':>10} {'Std Dev':>10}"
    )
    print(header)
    print("-" * 110)

    sorted_results = sort_by_avg(results)

    for name, data in sorted_results:
        s = data["stats"]
        print(
            f"{name:<25} {fmt(s['latest']):>10} {fmt(s['avg']):>10} "
            f"{fmt(s['median']):>10} {fmt(s['min']):>10} {fmt(s['max']):>10} "
            f"{fmt(s['std']):>10}"
        )

    # Risk-adjusted comparison
    print(f"\n{'=' * 110}")
    print("RISK-ADJUSTED VIEW (Average Return / Std Dev)")
    print(f"{'=' * 110}")
    print(f"{'Fund/Index':<25} {'Avg Return':>12} {'Std Dev':>12} {'Return/Risk':>12}")
    print("-" * 110)

    risk_adjusted = []
    for name, data in results.items():
        s = data["stats"]
        if s["avg"] and s["std"] and s["std"] > 0:
            ratio = s["avg"] / s["std"]
            risk_adjusted.append((name, s["avg"], s["std"], ratio))

    risk_adjusted.sort(key=lambda x: x[3], reverse=True)

    for name, avg, std, ratio in risk_adjusted:
        print(f"{name:<25} {fmt(avg):>12} {fmt(std):>12} {ratio:>11.2f}x")


if __name__ == "__main__":
    main()
