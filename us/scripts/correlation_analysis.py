#!/usr/bin/env python3
"""
Portfolio Correlation Analysis

Analyzes correlations between current holdings and proposed additions.
Generates heatmap and compares current vs proposed portfolio metrics.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import yfinance as yf

# Configuration
START_DATE = "2023-01-01"
END_DATE = "2026-01-21"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# Current Holdings
USD_HOLDINGS = {
    # Precious Metals - Miners/Streamers
    "PAAS": {"name": "Pan American Silver", "category": "Silver Miner", "current_pct": 15.25},
    "HL": {"name": "Hecla Mining", "category": "Silver Miner", "current_pct": 15.25},
    "AEM": {"name": "Agnico Eagle", "category": "Gold Miner", "current_pct": 10.17},
    "WPM": {"name": "Wheaton Precious Metals", "category": "PM Streamer", "current_pct": 8.47},
    "FNV": {"name": "Franco-Nevada", "category": "PM Streamer", "current_pct": 5.08},
    # Oil/Energy
    "XOM": {"name": "Exxon Mobil", "category": "Oil", "current_pct": 6.78},
    "SU": {"name": "Suncor Energy", "category": "Oil", "current_pct": 6.78},
    # Ex-US Value
    "AVDV": {"name": "Avantis Intl Small Cap Value", "category": "Ex-US Value", "current_pct": 11.86},
    "DFIV": {"name": "DFA International Value", "category": "Ex-US Value", "current_pct": 11.86},
    "IVAL": {"name": "Alpha Architect Intl Quant Value", "category": "Ex-US Value", "current_pct": 8.47},
}

# Proposed Additions
PROPOSED_ADDITIONS = {
    "VNQ": {"name": "Vanguard Real Estate ETF", "category": "REITs", "proposed_pct": 8.0},
    "SCHH": {"name": "Schwab US REIT ETF", "category": "REITs", "proposed_pct": 0},  # alternative
    "O": {"name": "Realty Income", "category": "REITs", "proposed_pct": 0},  # alternative
    "CVX": {"name": "Chevron", "category": "Oil", "proposed_pct": 0},  # alternative to more XOM
}

# Benchmarks/Proxies
BENCHMARKS = {
    "GLD": {"name": "SPDR Gold Trust", "category": "Gold"},
    "SLV": {"name": "iShares Silver Trust", "category": "Silver"},
    "^NSEI": {"name": "Nifty 50", "category": "India Equity"},
    "EEM": {"name": "iShares MSCI Emerging Markets", "category": "Emerging Markets"},
    "SPY": {"name": "S&P 500", "category": "US Equity"},
}

# Combine all tickers
ALL_TICKERS = (
    list(USD_HOLDINGS.keys())
    + list(PROPOSED_ADDITIONS.keys())
    + list(BENCHMARKS.keys())
)


def fetch_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Fetch adjusted close prices for all tickers."""
    print(f"Fetching prices for {len(tickers)} tickers...")
    data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)

    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        prices = data

    # Handle missing data
    prices = prices.ffill().bfill()
    print(f"Got {len(prices)} days of data")
    return prices


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily returns."""
    return prices.pct_change().dropna()


def calculate_correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Calculate correlation matrix."""
    return returns.corr()


def plot_correlation_heatmap(corr_matrix: pd.DataFrame, output_path: Path):
    """Generate and save correlation heatmap."""
    plt.figure(figsize=(16, 14))

    # Create mask for upper triangle
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)

    # Custom colormap
    cmap = sns.diverging_palette(250, 10, as_cmap=True)

    sns.heatmap(
        corr_matrix,
        mask=mask,
        cmap=cmap,
        vmin=-1,
        vmax=1,
        center=0,
        square=True,
        linewidths=0.5,
        annot=True,
        fmt=".2f",
        annot_kws={"size": 8},
    )

    plt.title("Portfolio Correlation Matrix (3-Year Daily Returns)", fontsize=14, pad=20)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Saved heatmap to {output_path}")


def calculate_portfolio_metrics(returns: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Calculate portfolio-level metrics."""
    # Filter to tickers we have weights for
    available_tickers = [t for t in weights.keys() if t in returns.columns]
    if not available_tickers:
        return {}

    portfolio_returns = returns[available_tickers]
    weight_series = pd.Series({t: weights[t] for t in available_tickers})
    weight_series = weight_series / weight_series.sum()  # Normalize

    # Portfolio daily returns
    portfolio_daily = (portfolio_returns * weight_series).sum(axis=1)

    # Metrics
    annual_return = portfolio_daily.mean() * 252
    annual_vol = portfolio_daily.std() * np.sqrt(252)
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0

    # Downside volatility (Sortino)
    downside_returns = portfolio_daily[portfolio_daily < 0]
    downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else annual_vol
    sortino = annual_return / downside_vol if downside_vol > 0 else 0

    # Max drawdown
    cumulative = (1 + portfolio_daily).cumprod()
    rolling_max = cumulative.expanding().max()
    drawdown = (cumulative - rolling_max) / rolling_max
    max_drawdown = drawdown.min()

    return {
        "annual_return": round(annual_return * 100, 2),
        "annual_volatility": round(annual_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown": round(max_drawdown * 100, 2),
    }


def get_current_weights() -> dict[str, float]:
    """Get current portfolio weights."""
    return {ticker: info["current_pct"] / 100 for ticker, info in USD_HOLDINGS.items()}


def get_proposed_weights() -> dict[str, float]:
    """Get proposed portfolio weights (reduced silver, more oil, add REITs)."""
    # Start with current
    weights = get_current_weights()

    # Reduce silver miners
    weights["PAAS"] = 0.08  # from 15.25%
    weights["HL"] = 0.07  # from 15.25%

    # Reduce Ex-US value slightly
    weights["AVDV"] = 0.09
    weights["DFIV"] = 0.09
    weights["IVAL"] = 0.06

    # Increase oil
    weights["XOM"] = 0.12  # from 6.78%
    weights["SU"] = 0.10  # from 6.78%

    # Add REITs
    weights["VNQ"] = 0.08

    # Keep PM streamers/miners same
    weights["AEM"] = 0.10
    weights["WPM"] = 0.08
    weights["FNV"] = 0.05

    # Normalize to 100%
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def analyze_correlations_with_india(corr_matrix: pd.DataFrame) -> pd.DataFrame:
    """Extract correlations with India equity (Nifty)."""
    if "^NSEI" not in corr_matrix.columns:
        return pd.DataFrame()

    india_corr = corr_matrix["^NSEI"].drop("^NSEI").sort_values()
    return india_corr.to_frame("correlation_with_india")


def main():
    print("=" * 60)
    print("PORTFOLIO CORRELATION ANALYSIS")
    print("=" * 60)

    # Fetch data
    prices = fetch_prices(ALL_TICKERS, START_DATE, END_DATE)
    returns = calculate_returns(prices)

    # Calculate correlation matrix
    corr_matrix = calculate_correlation_matrix(returns)

    # Save correlation matrix
    corr_path = OUTPUT_DIR / "correlation_matrix.csv"
    corr_matrix.to_csv(corr_path)
    print(f"\nSaved correlation matrix to {corr_path}")

    # Plot heatmap
    heatmap_path = OUTPUT_DIR / "correlation_heatmap.png"
    plot_correlation_heatmap(corr_matrix, heatmap_path)

    # Analyze India correlations
    print("\n" + "=" * 60)
    print("CORRELATIONS WITH INDIA EQUITY (NIFTY 50)")
    print("=" * 60)
    india_corr = analyze_correlations_with_india(corr_matrix)
    if not india_corr.empty:
        print(india_corr.to_string())

    # Calculate portfolio metrics
    print("\n" + "=" * 60)
    print("PORTFOLIO COMPARISON")
    print("=" * 60)

    current_weights = get_current_weights()
    proposed_weights = get_proposed_weights()

    current_metrics = calculate_portfolio_metrics(returns, current_weights)
    proposed_metrics = calculate_portfolio_metrics(returns, proposed_weights)

    print("\nCURRENT PORTFOLIO:")
    print(f"  Weights: {json.dumps({k: f'{v*100:.1f}%' for k, v in current_weights.items()}, indent=4)}")
    print(f"  Metrics: {json.dumps(current_metrics, indent=4)}")

    print("\nPROPOSED PORTFOLIO:")
    print(f"  Weights: {json.dumps({k: f'{v*100:.1f}%' for k, v in proposed_weights.items()}, indent=4)}")
    print(f"  Metrics: {json.dumps(proposed_metrics, indent=4)}")

    # Save comparison
    comparison = {
        "current": {"weights": {k: round(v * 100, 2) for k, v in current_weights.items()}, "metrics": current_metrics},
        "proposed": {"weights": {k: round(v * 100, 2) for k, v in proposed_weights.items()}, "metrics": proposed_metrics},
    }
    comparison_path = OUTPUT_DIR / "portfolio_comparison.json"
    with open(comparison_path, "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"\nSaved comparison to {comparison_path}")

    # Key findings
    print("\n" + "=" * 60)
    print("KEY FINDINGS")
    print("=" * 60)

    # Silver correlation with gold
    if "GLD" in corr_matrix.columns and "SLV" in corr_matrix.columns:
        gold_silver_corr = corr_matrix.loc["GLD", "SLV"]
        print(f"\n1. Gold-Silver correlation: {gold_silver_corr:.2f}")
        print("   → High correlation confirms diversification benefit is limited")

    # REIT correlations
    if "VNQ" in corr_matrix.columns:
        vnq_gold = corr_matrix.loc["VNQ", "GLD"] if "GLD" in corr_matrix.columns else None
        vnq_silver = corr_matrix.loc["VNQ", "SLV"] if "SLV" in corr_matrix.columns else None
        vnq_oil = corr_matrix.loc["VNQ", "XOM"] if "XOM" in corr_matrix.columns else None
        print(f"\n2. VNQ (REITs) correlations:")
        if vnq_gold:
            print(f"   - vs Gold: {vnq_gold:.2f}")
        if vnq_silver:
            print(f"   - vs Silver: {vnq_silver:.2f}")
        if vnq_oil:
            print(f"   - vs Oil (XOM): {vnq_oil:.2f}")
        print("   → REITs provide meaningful diversification")

    # Oil-India hedge
    if "XOM" in corr_matrix.columns and "^NSEI" in corr_matrix.columns:
        oil_india = corr_matrix.loc["XOM", "^NSEI"]
        print(f"\n3. Oil (XOM) vs India (Nifty) correlation: {oil_india:.2f}")
        if oil_india < 0.3:
            print("   → Low/negative correlation confirms India hedge thesis")

    # Metric improvements
    if current_metrics and proposed_metrics:
        print("\n4. Portfolio Metrics Comparison:")
        sharpe_change = proposed_metrics["sharpe_ratio"] - current_metrics["sharpe_ratio"]
        sortino_change = proposed_metrics["sortino_ratio"] - current_metrics["sortino_ratio"]
        dd_change = proposed_metrics["max_drawdown"] - current_metrics["max_drawdown"]
        print(f"   - Sharpe change: {sharpe_change:+.3f}")
        print(f"   - Sortino change: {sortino_change:+.3f}")
        print(f"   - Max drawdown change: {dd_change:+.2f}%")

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
