#!/usr/bin/env python3
"""
Hindustan Zinc vs Silver Price Correlation Analysis

Calculates correlation between HINDZINC.NS and silver prices.
Thesis: ~25% of Hindustan Zinc revenue comes from silver byproduct.
"""

import pandas as pd
import yfinance as yf

# Configuration
PERIOD = "3y"
ROLLING_WINDOW = 90  # days


def fetch_data():
    """Fetch price data for Hindustan Zinc and Silver."""
    print("Fetching Hindustan Zinc (HINDZINC.NS)...")
    hindzinc_data = yf.download("HINDZINC.NS", period=PERIOD, progress=False)
    hindzinc = hindzinc_data["Close"].squeeze()

    print("Fetching Silver ETF (SILVERBEES.NS)...")
    silver_data = yf.download("SILVERBEES.NS", period=PERIOD, progress=False)
    silver = silver_data["Close"].squeeze()

    # Fallback to SLV if SILVERBEES data insufficient
    if len(silver.dropna()) < 100:
        print("SILVERBEES data insufficient, using SLV (USD) as proxy...")
        silver_data = yf.download("SLV", period=PERIOD, progress=False)
        silver = silver_data["Close"].squeeze()

    return hindzinc, silver


def calculate_correlation(hindzinc: pd.Series, silver: pd.Series):
    """Calculate overall and rolling correlation."""
    # Align dates
    df = pd.DataFrame({"HINDZINC": hindzinc, "Silver": silver}).dropna()
    print(f"\nAligned data points: {len(df)}")
    print(
        "Date range: "
        f"{df.index[0].strftime('%Y-%m-%d')} to "
        f"{df.index[-1].strftime('%Y-%m-%d')}"
    )

    # Daily returns
    returns = df.pct_change().dropna()

    # Overall correlation
    corr = returns["HINDZINC"].corr(returns["Silver"])

    # Rolling correlation
    rolling_corr = returns["HINDZINC"].rolling(ROLLING_WINDOW).corr(returns["Silver"])

    return corr, rolling_corr, returns


def fetch_gold_for_comparison():
    """Fetch gold for context comparison."""
    print("\nFetching Gold ETF for comparison...")
    gold_data = yf.download("GLD", period=PERIOD, progress=False)
    gold = gold_data["Close"].squeeze()
    return gold


def main():
    print("=" * 60)
    print("HINDUSTAN ZINC vs SILVER CORRELATION ANALYSIS")
    print("=" * 60)

    # Fetch data
    hindzinc, silver = fetch_data()

    # Calculate correlation
    corr, rolling_corr, returns = calculate_correlation(hindzinc, silver)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(f"\n📊 Overall Correlation: {corr:.3f}")

    # Interpretation
    if corr > 0.5:
        interpretation = "Strong positive — HINDZINC moves with silver"
    elif corr > 0.3:
        interpretation = "Moderate positive — some silver exposure"
    elif corr > 0.1:
        interpretation = "Weak positive — limited silver linkage"
    elif corr > -0.1:
        interpretation = "Negligible — no meaningful relationship"
    else:
        interpretation = "Negative — inverse relationship"

    print(f"   Interpretation: {interpretation}")

    # Rolling correlation stats
    rolling_stats = rolling_corr.dropna()
    print(f"\n📈 Rolling {ROLLING_WINDOW}-day Correlation:")
    print(f"   Mean:   {rolling_stats.mean():.3f}")
    print(f"   Std:    {rolling_stats.std():.3f}")
    print(f"   Min:    {rolling_stats.min():.3f}")
    print(f"   Max:    {rolling_stats.max():.3f}")
    print(f"   Latest: {rolling_stats.iloc[-1]:.3f}")

    # Compare to gold
    gold = fetch_gold_for_comparison()
    df_gold = pd.DataFrame({"HINDZINC": hindzinc, "Gold": gold}).dropna()
    returns_gold = df_gold.pct_change().dropna()
    gold_corr = returns_gold["HINDZINC"].corr(returns_gold["Gold"])

    print(f"\n🥇 Comparison - HINDZINC vs Gold: {gold_corr:.3f}")

    # Summary table
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("\n| Pair             | Correlation |")
    print("|------------------|-------------|")
    print(f"| HINDZINC-Silver  | {corr:>11.3f} |")
    print(f"| HINDZINC-Gold    | {gold_corr:>11.3f} |")

    # Thesis check
    print("\n📋 Thesis Check:")
    print("   Expected: Moderate-to-strong correlation (silver is ~25% of revenue)")
    if corr > 0.3:
        print(
            "   Result: ✓ Confirmed — correlation "
            f"{corr:.2f} supports silver exposure thesis"
        )
    else:
        print("   Result: ✗ Weaker than expected — zinc price may dominate")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
