"""
Canadian Oil & Gas - NYSE-Listed Only

Analyzes ONLY Canadian oil and gas companies listed on NYSE
(no OTC access required for Interactive Brokers).

NYSE-LISTED CANADIAN ENERGY:
- ENB: Enbridge (~5.6% yield)
- CNQ: Canadian Natural Resources (~5.1% yield)
- TRP: TC Energy (~4.5% yield)
- SU: Suncor Energy (~4.0% yield)
- CVE: Cenovus Energy (~3.1% yield)

Note: None exceed 7% yield threshold, but all are accessible
without requiring OTC permissions in Interactive Brokers.
"""

import pandas as pd
import numpy as np
import yfinance as yf

# NYSE-listed Canadian energy stocks
NYSE_CANADIAN = {
    "ENB": {"name": "Enbridge", "yield": 5.60, "frequency": "Quarterly", "type": "Midstream"},
    "CNQ": {"name": "Canadian Natural Resources", "yield": 5.10, "frequency": "Quarterly", "type": "Integrated"},
    "TRP": {"name": "TC Energy", "yield": 4.50, "frequency": "Quarterly", "type": "Midstream"},
    "SU": {"name": "Suncor Energy", "yield": 4.00, "frequency": "Quarterly", "type": "Integrated"},
    "CVE": {"name": "Cenovus Energy", "yield": 3.10, "frequency": "Quarterly", "type": "Integrated"},
}

# For comparison - US energy stocks from our portfolio
US_ENERGY_COMPARISON = {
    "XOM": {"name": "Exxon Mobil", "yield": 3.42, "type": "Integrated"},
    "CVX": {"name": "Chevron", "yield": 4.49, "type": "Integrated"},
    "COP": {"name": "ConocoPhillips", "yield": 3.59, "type": "E&P"},
}

LOOKBACK_3M = 63
LOOKBACK_6M = 126


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """
    Fetch total return index for tickers (includes reinvested dividends).

    CRITICAL for high-yield stocks where dividends are major return component.
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


def calculate_drawdown_duration(prices: pd.DataFrame) -> pd.Series:
    """Calculate longest underwater period in days."""
    durations = {}

    for ticker in prices.columns:
        price_series = prices[ticker]
        running_max = price_series.cummax()
        underwater = price_series < running_max

        max_duration = 0
        current_duration = 0

        for is_underwater in underwater:
            if is_underwater:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        durations[ticker] = max_duration

    return pd.Series(durations)


def main():
    print("=" * 85)
    print("CANADIAN OIL & GAS - NYSE-LISTED ONLY (No OTC Required)")
    print("=" * 85)

    print("\nNYSE-LISTED CANADIAN ENERGY STOCKS:")
    print(f"{'Ticker':<8} {'Name':<30} {'Yield':<8} {'Type':<12} {'Frequency':<12}")
    print("-" * 85)
    for ticker, info in NYSE_CANADIAN.items():
        print(f"{ticker:<8} {info['name']:<30} {info['yield']:>6.2f}% {info['type']:<12} {info['frequency']:<12}")

    print("\nNOTE: Highest yield is ENB at 5.6% (none reach 7% threshold)")
    print("All stocks directly accessible via Interactive Brokers NYSE feed")

    # Fetch data
    print(f"\n{'=' * 85}")
    print("FETCHING 3-YEAR TOTAL RETURN DATA (Price + Reinvested Dividends)...")
    print("=" * 85)

    canadian_tickers = list(NYSE_CANADIAN.keys())
    us_tickers = list(US_ENERGY_COMPARISON.keys())
    all_tickers = canadian_tickers + us_tickers

    prices = fetch_total_return_index(all_tickers)

    if prices.empty:
        print("\nError: No price data could be fetched. Exiting.")
        return

    returns = calculate_returns(prices)

    print(f"\nData range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Trading days: {len(returns)}")

    # Calculate metrics
    mom_3m = calculate_momentum(prices, LOOKBACK_3M)
    mom_6m = calculate_momentum(prices, LOOKBACK_6M)
    downside_vol = calculate_downside_volatility(returns)
    max_dd = calculate_max_drawdown(prices)
    dd_duration = calculate_drawdown_duration(prices)

    # Combined score
    combined_mom = (mom_3m + mom_6m) / 2
    score = combined_mom / downside_vol

    # Create summary table
    summary = pd.DataFrame({
        'Div_Yield': [NYSE_CANADIAN.get(t, US_ENERGY_COMPARISON.get(t))['yield'] for t in prices.columns],
        'Type': [NYSE_CANADIAN.get(t, US_ENERGY_COMPARISON.get(t))['type'] for t in prices.columns],
        '3M_Mom': mom_3m,
        '6M_Mom': mom_6m,
        'Avg_Mom': combined_mom,
        'Down_Vol': downside_vol,
        'Max_DD': max_dd * 100,
        'DD_Days': dd_duration,
        'Score': score,
    }, index=prices.columns)

    # Separate Canadian and US
    canadian_summary = summary.loc[canadian_tickers]
    us_summary = summary.loc[us_tickers]

    # Sort Canadian by score
    canadian_summary = canadian_summary.sort_values('Score', ascending=False)

    print("\n" + "=" * 85)
    print("CANADIAN NYSE STOCKS - TOTAL RETURN ANALYSIS")
    print("=" * 85)
    print("\nTicker  Div Yld  Type          3M Mom    6M Mom   Avg Mom  Down Vol  Max DD  DD Days  Score")
    print("-" * 95)

    for ticker in canadian_summary.index:
        row = canadian_summary.loc[ticker]
        print(f"{ticker:<6} {row['Div_Yield']:>6.2f}% {row['Type']:<12} {row['3M_Mom']:>+8.2f}% "
              f"{row['6M_Mom']:>+8.2f}% {row['Avg_Mom']:>+8.2f}% {row['Down_Vol']:>8.2f}% "
              f"{row['Max_DD']:>+7.1f}% {row['DD_Days']:>7.0f}d {row['Score']:>7.2f}")

    # US comparison
    print("\n" + "=" * 85)
    print("US ENERGY COMPARISON (Currently in Portfolio)")
    print("=" * 85)
    print("\nTicker  Div Yld  Type          3M Mom    6M Mom   Avg Mom  Down Vol  Max DD  DD Days  Score")
    print("-" * 95)

    for ticker in us_summary.index:
        row = us_summary.loc[ticker]
        print(f"{ticker:<6} {row['Div_Yield']:>6.2f}% {row['Type']:<12} {row['3M_Mom']:>+8.2f}% "
              f"{row['6M_Mom']:>+8.2f}% {row['Avg_Mom']:>+8.2f}% {row['Down_Vol']:>8.2f}% "
              f"{row['Max_DD']:>+7.1f}% {row['DD_Days']:>7.0f}d {row['Score']:>7.2f}")

    # Category analysis
    print("\n" + "=" * 85)
    print("CATEGORY COMPARISON")
    print("=" * 85)

    print(f"\nCANADIAN NYSE STOCKS (n={len(canadian_summary)}):")
    print(f"  Average Div Yield:    {canadian_summary['Div_Yield'].mean():>6.2f}%")
    print(f"  Average 3M Momentum:  {canadian_summary['3M_Mom'].mean():>+6.2f}%")
    print(f"  Average 6M Momentum:  {canadian_summary['6M_Mom'].mean():>+6.2f}%")
    print(f"  Average Downside Vol: {canadian_summary['Down_Vol'].mean():>6.2f}%")
    print(f"  Average Max DD:       {canadian_summary['Max_DD'].mean():>+6.1f}%")
    print(f"  Average Score:        {canadian_summary['Score'].mean():>6.2f}")

    print(f"\nUS ENERGY (n={len(us_summary)}):")
    print(f"  Average Div Yield:    {us_summary['Div_Yield'].mean():>6.2f}%")
    print(f"  Average 3M Momentum:  {us_summary['3M_Mom'].mean():>+6.2f}%")
    print(f"  Average 6M Momentum:  {us_summary['6M_Mom'].mean():>+6.2f}%")
    print(f"  Average Downside Vol: {us_summary['Down_Vol'].mean():>6.2f}%")
    print(f"  Average Max DD:       {us_summary['Max_DD'].mean():>+6.1f}%")
    print(f"  Average Score:        {us_summary['Score'].mean():>6.2f}")

    # Best performers
    print("\n" + "=" * 85)
    print("TOP 3 CANADIAN STOCKS BY SCORE")
    print("=" * 85)

    top_3 = canadian_summary.nlargest(3, 'Score')
    print("\nTicker  Div Yld   Avg Mom  Down Vol  Max DD    Score   Current Portfolio?")
    print("-" * 75)
    for ticker in top_3.index:
        row = top_3.loc[ticker]
        in_portfolio = "✓ YES (XOM)" if ticker == "XOM" else "  No"
        print(f"{ticker:<6} {row['Div_Yield']:>6.2f}% {row['Avg_Mom']:>+8.2f}% {row['Down_Vol']:>8.2f}% "
              f"{row['Max_DD']:>+7.1f}% {row['Score']:>8.2f}  {in_portfolio}")

    # Allocation simulation
    print("\n" + "=" * 85)
    print("HYPOTHETICAL ALLOCATION ANALYSIS")
    print("=" * 85)

    # If we allocate $4,000 (same as current XOM allocation) to Canadian stocks
    CAPITAL = 4000

    print(f"\nScenario: Allocate ${CAPITAL:,} to Canadian NYSE stocks using score-weighting")
    print("(Same capital currently allocated to XOM in portfolio)\n")

    # Score-weighted allocation
    total_score = canadian_summary['Score'].sum()
    allocations = (canadian_summary['Score'] / total_score * CAPITAL).round(0)

    print("Ticker  Score   Weight   Allocation  Div Yield  Annual Div Income")
    print("-" * 70)
    total_div_income = 0
    for ticker in canadian_summary.index:
        row = canadian_summary.loc[ticker]
        alloc = allocations[ticker]
        weight = row['Score'] / total_score * 100
        div_income = alloc * row['Div_Yield'] / 100
        total_div_income += div_income
        print(f"{ticker:<6} {row['Score']:>6.2f}  {weight:>6.2f}%  ${alloc:>8,.0f}   {row['Div_Yield']:>6.2f}%   ${div_income:>8,.0f}")

    print("-" * 70)
    print(f"TOTAL                     ${CAPITAL:>8,.0f}              ${total_div_income:>8,.0f}")
    print(f"\nWeighted Average Yield: {(total_div_income / CAPITAL * 100):>6.2f}%")

    # Compare to XOM
    xom_div_income = CAPITAL * us_summary.loc['XOM', 'Div_Yield'] / 100
    print(f"\nCurrent XOM allocation:")
    print(f"  XOM    ${CAPITAL:>8,.0f}   {us_summary.loc['XOM', 'Div_Yield']:>6.2f}%   ${xom_div_income:>8,.0f}")

    diff = total_div_income - xom_div_income
    print(f"\nDividend income difference: ${diff:>+8,.0f} ({(diff/xom_div_income*100):>+6.2f}%)")

    # Key insights
    print("\n" + "-" * 85)
    print("KEY INSIGHTS")
    print("-" * 85)
    print(f"""
1. YIELD COMPARISON:
   - Best Canadian NYSE yield: {canadian_summary['Div_Yield'].max():.2f}% (ENB)
   - Worst Canadian NYSE yield: {canadian_summary['Div_Yield'].min():.2f}% (CVE)
   - Average Canadian yield: {canadian_summary['Div_Yield'].mean():.2f}%
   - XOM yield: {us_summary.loc['XOM', 'Div_Yield']:.2f}%

2. RISK-ADJUSTED RETURNS (Score):
   - Best Canadian: {canadian_summary['Score'].idxmax()} ({canadian_summary['Score'].max():.2f})
   - XOM Score: {us_summary.loc['XOM', 'Score']:.2f}
   - Canadian average: {canadian_summary['Score'].mean():.2f}
   - US average: {us_summary['Score'].mean():.2f}

3. MOMENTUM:
   - Canadian 6M avg: {canadian_summary['6M_Mom'].mean():+.2f}%
   - US 6M avg: {us_summary['6M_Mom'].mean():+.2f}%

4. DRAWDOWN RISK:
   - Canadian max DD avg: {canadian_summary['Max_DD'].mean():.1f}%
   - US max DD avg: {us_summary['Max_DD'].mean():.1f}%

RECOMMENDATION:
- None of the NYSE-listed Canadian stocks meet your 7% yield requirement
- {canadian_summary['Score'].idxmax()} has the best risk-adjusted returns among Canadian stocks
- XOM (currently in portfolio) scores {us_summary.loc['XOM', 'Score']:.2f} vs Canadian avg {canadian_summary['Score'].mean():.2f}
- If seeking pure yield: ENB at {canadian_summary.loc['ENB', 'Div_Yield']:.2f}% is the highest NYSE option
- If seeking total return: Use score-weighted allocation shown above

For 7%+ yields, you would need OTC access (CRLFF, IPOOF, PTRUF, ZPTAF).
""")


if __name__ == "__main__":
    main()
