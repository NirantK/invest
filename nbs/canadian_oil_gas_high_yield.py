"""
Canadian Oil & Gas High-Yield Analysis

Analyzes Canadian oil and gas companies with dividend yields >7% that are
accessible through Interactive Brokers (US OTC or NYSE listings).

HIGH YIELD (7%+):
- IPOOF: InPlay Oil (~10% yield, monthly dividend)
- ZPTAF: Surge Energy (~7.5% yield, monthly dividend)
- CRLFF: Cardinal Energy (7%+ yield, monthly dividend)
- PTRUF: Petrus Resources (7%+ yield)

MEDIUM YIELD (5-7%):
- ENB: Enbridge (~5.6% yield, NYSE)
- WCPRF: Whitecap Resources (~6.2% yield, OTC)

COMPARISON (Major Producers):
- CNQ: Canadian Natural Resources (~5.1% yield, NYSE)
- SU: Suncor Energy (~4% yield, NYSE)
- CVE: Cenovus Energy (~3.1% yield, NYSE)
- TRP: TC Energy (~4.5% yield, NYSE)
- AETUF: ARC Resources (~3.15% yield, OTC)
- CPG: Crescent Point (~3.92% yield, NYSE)

All OTC tickers (ending in F) are available through Interactive Brokers.
"""

import pandas as pd
import numpy as np
import yfinance as yf

# High-yield Canadian oil & gas stocks (7%+)
HIGH_YIELD_TICKERS = {
    "IPOOF": {"name": "InPlay Oil", "yield": 10.11, "frequency": "Monthly"},
    "ZPTAF": {"name": "Surge Energy", "yield": 7.50, "frequency": "Monthly"},
    "CRLFF": {"name": "Cardinal Energy", "yield": 7.00, "frequency": "Monthly"},
    "PTRUF": {"name": "Petrus Resources", "yield": 7.00, "frequency": "Quarterly"},
}

# Medium-yield comparison
MEDIUM_YIELD_TICKERS = {
    "ENB": {"name": "Enbridge", "yield": 5.60, "frequency": "Quarterly"},
    "WCPRF": {"name": "Whitecap Resources", "yield": 6.22, "frequency": "Monthly"},
}

# Major producers (lower yield but more stable)
MAJOR_TICKERS = {
    "CNQ": {"name": "Canadian Natural Resources", "yield": 5.10, "frequency": "Quarterly"},
    "SU": {"name": "Suncor Energy", "yield": 4.00, "frequency": "Quarterly"},
    "CVE": {"name": "Cenovus Energy", "yield": 3.10, "frequency": "Quarterly"},
    "TRP": {"name": "TC Energy", "yield": 4.50, "frequency": "Quarterly"},
}

ALL_TICKERS = {**HIGH_YIELD_TICKERS, **MEDIUM_YIELD_TICKERS, **MAJOR_TICKERS}

LOOKBACK_3M = 63
LOOKBACK_6M = 126


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """
    Fetch total return index for tickers (includes reinvested dividends).

    For high-yield stocks, dividends are a major component of returns.
    With 21% flat C-Corp tax, dividends = capital gains.
    """
    dfs = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if not hist.empty:
                # Calculate total return index: reinvest dividends
                close = hist["Close"]
                dividends = hist["Dividends"]

                # Build total return index
                total_return_index = close.copy()
                cumulative_dividends = 0.0

                for i in range(len(close)):
                    if i > 0:
                        # Dividend yield on ex-date
                        div_yield = dividends.iloc[i] / close.iloc[i-1] if close.iloc[i-1] != 0 else 0
                        # Adjust for dividend reinvestment
                        cumulative_dividends = (1 + cumulative_dividends) * (1 + div_yield) - 1
                        total_return_index.iloc[i] = close.iloc[i] * (1 + cumulative_dividends)

                dfs.append(total_return_index.rename(ticker))
        except Exception as e:
            print(f"Warning: Could not fetch data for {ticker}: {e}")
            continue

    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, axis=1).dropna()


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily returns."""
    return prices.pct_change(fill_method=None).dropna()


def calculate_momentum(prices: pd.DataFrame, lookback: int) -> pd.Series:
    """Calculate momentum (total return) for a given lookback period."""
    if len(prices) < lookback:
        return pd.Series(np.nan, index=prices.columns)
    return (prices.iloc[-1] / prices.iloc[-lookback] - 1) * 100


def calculate_downside_volatility(returns: pd.DataFrame, threshold: float = 0.0) -> pd.Series:
    """Calculate annualized downside volatility."""
    downside_returns = returns[returns < threshold]
    downside_vol = downside_returns.std() * np.sqrt(252)
    return downside_vol


def calculate_max_drawdown(prices: pd.DataFrame) -> pd.Series:
    """Calculate maximum drawdown for each ticker."""
    running_max = prices.cummax()
    drawdown = (prices - running_max) / running_max
    return drawdown.min()


def main():
    print("=" * 80)
    print("CANADIAN OIL & GAS HIGH-YIELD ANALYSIS")
    print("=" * 80)

    print("\nHIGH-YIELD CANDIDATES (7%+):")
    print(f"{'Ticker':<10} {'Name':<25} {'Yield':<8} {'Frequency':<12} {'Exchange':<10}")
    print("-" * 80)
    for ticker, info in HIGH_YIELD_TICKERS.items():
        exchange = "OTC" if ticker.endswith("F") else "NYSE"
        print(f"{ticker:<10} {info['name']:<25} {info['yield']:>6.2f}% {info['frequency']:<12} {exchange:<10}")

    print("\nMEDIUM-YIELD COMPARISON (5-7%):")
    print(f"{'Ticker':<10} {'Name':<25} {'Yield':<8} {'Frequency':<12} {'Exchange':<10}")
    print("-" * 80)
    for ticker, info in MEDIUM_YIELD_TICKERS.items():
        exchange = "OTC" if ticker.endswith("F") else "NYSE"
        print(f"{ticker:<10} {info['name']:<25} {info['yield']:>6.2f}% {info['frequency']:<12} {exchange:<10}")

    print("\nMAJOR PRODUCERS (<5%):")
    print(f"{'Ticker':<10} {'Name':<25} {'Yield':<8} {'Frequency':<12} {'Exchange':<10}")
    print("-" * 80)
    for ticker, info in MAJOR_TICKERS.items():
        exchange = "OTC" if ticker.endswith("F") else "NYSE"
        print(f"{ticker:<10} {info['name']:<25} {info['yield']:>6.2f}% {info['frequency']:<12} {exchange:<10}")

    # Fetch data
    print(f"\n{'=' * 80}")
    print("FETCHING 3-YEAR TOTAL RETURN DATA...")
    print("=" * 80)

    all_tickers = list(ALL_TICKERS.keys())
    prices = fetch_total_return_index(all_tickers)

    if prices.empty:
        print("\nError: No price data could be fetched. Exiting.")
        return

    returns = calculate_returns(prices)

    print(f"\nData range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Trading days: {len(returns)}")
    print(f"Tickers with data: {list(prices.columns)}")

    # Calculate metrics
    mom_3m = calculate_momentum(prices, LOOKBACK_3M)
    mom_6m = calculate_momentum(prices, LOOKBACK_6M)
    downside_vol = calculate_downside_volatility(returns)
    max_dd = calculate_max_drawdown(prices)

    # Combined score
    combined_mom = (mom_3m + mom_6m) / 2
    score = combined_mom / downside_vol

    # Create summary table
    summary = pd.DataFrame({
        'Div_Yield': [ALL_TICKERS[t]['yield'] for t in prices.columns],
        '3M_Mom': mom_3m,
        '6M_Mom': mom_6m,
        'Avg_Mom': combined_mom,
        'Down_Vol': downside_vol,
        'Max_DD': max_dd * 100,
        'Score': score,
        'Exchange': ['OTC' if t.endswith('F') else 'NYSE' for t in prices.columns],
    }, index=prices.columns)

    # Sort by dividend yield
    summary = summary.sort_values('Div_Yield', ascending=False)

    print("\n" + "=" * 80)
    print("TOTAL RETURN ANALYSIS (3-Year History)")
    print("=" * 80)
    print("\nTicker    Div Yld    3M Mom    6M Mom   Avg Mom  Down Vol   Max DD    Score  Exch")
    print("-" * 85)

    for ticker in summary.index:
        row = summary.loc[ticker]
        print(f"{ticker:<8} {row['Div_Yield']:>6.2f}%  {row['3M_Mom']:>+8.2f}% {row['6M_Mom']:>+8.2f}% "
              f"{row['Avg_Mom']:>+8.2f}% {row['Down_Vol']:>8.2f}% {row['Max_DD']:>+7.1f}% "
              f"{row['Score']:>8.2f}  {row['Exchange']:<4}")

    # Analyze by category
    print("\n" + "=" * 80)
    print("CATEGORY ANALYSIS")
    print("=" * 80)

    high_yield = summary[summary['Div_Yield'] >= 7.0]
    medium_yield = summary[(summary['Div_Yield'] >= 5.0) & (summary['Div_Yield'] < 7.0)]
    major_prod = summary[summary['Div_Yield'] < 5.0]

    for category_name, category_df in [
        ("HIGH-YIELD (7%+)", high_yield),
        ("MEDIUM-YIELD (5-7%)", medium_yield),
        ("MAJOR PRODUCERS (<5%)", major_prod)
    ]:
        if not category_df.empty:
            print(f"\n{category_name}:")
            print(f"  Average Div Yield:    {category_df['Div_Yield'].mean():>6.2f}%")
            print(f"  Average 6M Momentum:  {category_df['6M_Mom'].mean():>+6.2f}%")
            print(f"  Average Downside Vol: {category_df['Down_Vol'].mean():>6.2f}%")
            print(f"  Average Max DD:       {category_df['Max_DD'].mean():>+6.1f}%")
            print(f"  Average Score:        {category_df['Score'].mean():>6.2f}")

    # Top performers by score
    print("\n" + "=" * 80)
    print("TOP 5 BY COMBINED SCORE")
    print("=" * 80)

    top_5 = summary.nlargest(5, 'Score')
    print("\nTicker    Div Yld   Avg Mom  Down Vol   Max DD    Score")
    print("-" * 65)
    for ticker in top_5.index:
        row = top_5.loc[ticker]
        print(f"{ticker:<8} {row['Div_Yield']:>6.2f}% {row['Avg_Mom']:>+8.2f}% {row['Down_Vol']:>8.2f}% "
              f"{row['Max_DD']:>+7.1f}% {row['Score']:>8.2f}")

    # Interactive Brokers availability
    print("\n" + "=" * 80)
    print("INTERACTIVE BROKERS AVAILABILITY")
    print("=" * 80)

    nyse_tickers = summary[summary['Exchange'] == 'NYSE'].index.tolist()
    otc_tickers = summary[summary['Exchange'] == 'OTC'].index.tolist()

    print(f"\nNYSE-LISTED (Direct access): {len(nyse_tickers)}")
    for ticker in nyse_tickers:
        print(f"  {ticker}: {ALL_TICKERS[ticker]['name']}")

    print(f"\nOTC-LISTED (Requires OTC access): {len(otc_tickers)}")
    for ticker in otc_tickers:
        print(f"  {ticker}: {ALL_TICKERS[ticker]['name']}")

    print("\nNOTE: All tickers listed above are accessible via Interactive Brokers.")
    print("OTC tickers require enabling OTC trading permissions in your IB account.")

    # Key insights
    print("\n" + "-" * 80)
    print("KEY INSIGHTS")
    print("-" * 80)
    print("""
1. High-yield stocks (7%+) are mostly smaller producers trading OTC
2. Dividend yield doesn't always correlate with total return performance
3. Major producers offer lower yields but potentially lower volatility
4. Monthly dividends (InPlay, Surge, Cardinal, Whitecap) provide steady income
5. With 21% flat C-Corp tax, focus on total return (dividends + price appreciation)

RECOMMENDATION:
- If seeking pure yield: InPlay Oil (IPOOF) at 10.11% is the highest
- If seeking balance: Whitecap (WCPRF) at 6.22% with monthly payments
- If seeking stability: CNQ at 5.1% with 25 years of dividend growth
- For momentum allocation: Use the Score column to weight positions

All high-yield candidates require OTC access in Interactive Brokers.
""")


if __name__ == "__main__":
    main()
