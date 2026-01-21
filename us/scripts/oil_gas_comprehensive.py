"""
Comprehensive Oil & Gas Analysis - All Segments

Analyzes US-listed oil & gas across all segments operating in Western jurisdictions:
- Integrated Majors
- E&P (Exploration & Production)
- Midstream/Pipelines
- Refineries
- Royalty Companies

Focus: 7%+ dividend yields, NYSE/NASDAQ only, Western Hemisphere operations

HIGH-YIELD CANDIDATES (7%+):
ROYALTY:
- DMLP: Dorchester Minerals (~14% yield, US operations)
- KRP: Kimbell Royalty (~12% yield, Permian Basin)
- BSM: Black Stone Minerals (~9% yield, 41 US states)

MIDSTREAM/PIPELINES:
- ET: Energy Transfer (~8% yield, US pipelines)
- MPLX: MPLX LP (~7.9% yield, US midstream)
- EPD: Enterprise Products (~6.8% yield, US pipelines)

MEDIUM-YIELD (4-7%):
- STR: Sitio Royalties (~5.7-7.6% yield)
- VNOM: Viper Energy (~6.2% yield, Permian)
- ENB: Enbridge (~5.6% yield, North America)
- CNQ: Canadian Natural (~5.1% yield)

All operate primarily in US/Canada (Western Hemisphere, high-trust jurisdictions)
"""

import pandas as pd
import numpy as np
import yfinance as yf

# COMPREHENSIVE OIL & GAS UNIVERSE
# Grouped by segment, sorted by expected yield

# Royalty Companies (highest yields)
ROYALTY = {
    "DMLP": {"name": "Dorchester Minerals", "yield": 14.18, "ops": "US (28 states)"},
    "KRP": {"name": "Kimbell Royalty", "yield": 11.97, "ops": "US (Permian Basin)"},
    "BSM": {"name": "Black Stone Minerals", "yield": 8.73, "ops": "US (41 states)"},
    "STR": {"name": "Sitio Royalties", "yield": 7.60, "ops": "US (Permian Basin)"},
    "VNOM": {"name": "Viper Energy", "yield": 6.22, "ops": "US (Permian Basin)"},
}

# Midstream/Pipelines (MLPs - high yields)
MIDSTREAM = {
    "ET": {"name": "Energy Transfer", "yield": 8.02, "ops": "US"},
    "MPLX": {"name": "MPLX LP", "yield": 7.90, "ops": "US"},
    "EPD": {"name": "Enterprise Products", "yield": 6.75, "ops": "US"},
    "ENB": {"name": "Enbridge", "yield": 5.60, "ops": "US/Canada"},
    "TRP": {"name": "TC Energy", "yield": 4.50, "ops": "US/Canada/Mexico"},
    "KMI": {"name": "Kinder Morgan", "yield": 4.50, "ops": "US"},
    "WMB": {"name": "Williams Companies", "yield": 4.00, "ops": "US"},
    "OKE": {"name": "ONEOK", "yield": 4.00, "ops": "US"},
}

# Integrated Majors
MAJORS = {
    "CNQ": {"name": "Canadian Natural", "yield": 5.10, "ops": "Canada/UK"},
    "CVX": {"name": "Chevron", "yield": 4.49, "ops": "US/Global"},
    "SU": {"name": "Suncor Energy", "yield": 4.00, "ops": "Canada"},
    "XOM": {"name": "Exxon Mobil", "yield": 3.42, "ops": "US/Global"},
    "CVE": {"name": "Cenovus Energy", "yield": 3.10, "ops": "Canada"},
}

# Refineries
REFINERIES = {
    "PSX": {"name": "Phillips 66", "yield": 3.72, "ops": "US/Europe"},
    "DINO": {"name": "HF Sinclair", "yield": 3.65, "ops": "US"},
    "VLO": {"name": "Valero Energy", "yield": 2.74, "ops": "US/Canada/UK"},
    "MPC": {"name": "Marathon Petroleum", "yield": 2.45, "ops": "US"},
}

# E&P Companies (Exploration & Production)
EP_COMPANIES = {
    "COP": {"name": "ConocoPhillips", "yield": 3.59, "ops": "US/Global"},
    "DVN": {"name": "Devon Energy", "yield": 6.50, "ops": "US"},
    "MRO": {"name": "Marathon Oil", "yield": 1.80, "ops": "US"},
    "OXY": {"name": "Occidental Petroleum", "yield": 1.30, "ops": "US"},
}

# Combine all
ALL_STOCKS = {
    **ROYALTY,
    **MIDSTREAM,
    **MAJORS,
    **REFINERIES,
    **EP_COMPANIES,
}

LOOKBACK_3M = 63
LOOKBACK_6M = 126


def get_segment(ticker: str) -> str:
    """Identify which segment a ticker belongs to."""
    if ticker in ROYALTY:
        return "Royalty"
    elif ticker in MIDSTREAM:
        return "Midstream"
    elif ticker in MAJORS:
        return "Major"
    elif ticker in REFINERIES:
        return "Refinery"
    elif ticker in EP_COMPANIES:
        return "E&P"
    return "Unknown"


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """
    Fetch total return index for tickers (includes reinvested dividends).

    CRITICAL for high-yield stocks where dividends are major return component.
    With 21% flat C-Corp tax, dividends = capital gains.
    """
    dfs = []
    failed = []

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
            else:
                failed.append(ticker)
        except Exception as e:
            failed.append(ticker)
            continue

    if failed:
        print(f"Warning: Could not fetch data for: {', '.join(failed)}")

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
    print("=" * 95)
    print("COMPREHENSIVE OIL & GAS ANALYSIS - ALL SEGMENTS")
    print("Western Hemisphere Operations | NYSE/NASDAQ Listed | 7%+ Yield Focus")
    print("=" * 95)

    # Display universe
    print(f"\nUNIVERSE: {len(ALL_STOCKS)} stocks across 5 segments\n")

    for segment_name, segment_dict in [
        ("ROYALTY COMPANIES", ROYALTY),
        ("MIDSTREAM/PIPELINES (MLPs)", MIDSTREAM),
        ("INTEGRATED MAJORS", MAJORS),
        ("REFINERIES", REFINERIES),
        ("E&P (EXPLORATION & PRODUCTION)", EP_COMPANIES),
    ]:
        print(f"{segment_name}:")
        print(f"{'Ticker':<8} {'Name':<30} {'Yield':<8} {'Operations':<25}")
        print("-" * 95)
        for ticker, info in sorted(segment_dict.items(), key=lambda x: -x[1]['yield']):
            print(f"{ticker:<8} {info['name']:<30} {info['yield']:>6.2f}% {info['ops']:<25}")
        print()

    # Fetch data
    print("=" * 95)
    print("FETCHING 3-YEAR TOTAL RETURN DATA...")
    print("=" * 95)

    all_tickers = list(ALL_STOCKS.keys())
    prices = fetch_total_return_index(all_tickers)

    if prices.empty:
        print("\nError: No price data could be fetched. Exiting.")
        return

    returns = calculate_returns(prices)

    print(f"\nData range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Trading days: {len(returns)}")
    print(f"Stocks with data: {len(prices.columns)}/{len(all_tickers)}")

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
        'Segment': [get_segment(t) for t in prices.columns],
        'Div_Yield': [ALL_STOCKS[t]['yield'] for t in prices.columns],
        'Operations': [ALL_STOCKS[t]['ops'] for t in prices.columns],
        '3M_Mom': mom_3m,
        '6M_Mom': mom_6m,
        'Avg_Mom': combined_mom,
        'Down_Vol': downside_vol,
        'Max_DD': max_dd * 100,
        'Score': score,
    }, index=prices.columns)

    # HIGH-YIELD ANALYSIS (7%+)
    print("\n" + "=" * 95)
    print("HIGH-YIELD STOCKS (7%+ Dividend Yield)")
    print("=" * 95)

    high_yield = summary[summary['Div_Yield'] >= 7.0].sort_values('Score', ascending=False)

    if len(high_yield) > 0:
        print(f"\nFound {len(high_yield)} stocks with 7%+ yield:\n")
        print("Ticker  Segment    Div Yld    3M Mom    6M Mom   Avg Mom  Down Vol  Max DD    Score")
        print("-" * 95)
        for ticker in high_yield.index:
            row = high_yield.loc[ticker]
            print(f"{ticker:<6} {row['Segment']:<10} {row['Div_Yield']:>6.2f}% {row['3M_Mom']:>+8.2f}% "
                  f"{row['6M_Mom']:>+8.2f}% {row['Avg_Mom']:>+8.2f}% {row['Down_Vol']:>8.2f}% "
                  f"{row['Max_DD']:>+7.1f}% {row['Score']:>8.2f}")

        print(f"\nHIGH-YIELD CATEGORY AVERAGES:")
        print(f"  Average Yield:        {high_yield['Div_Yield'].mean():>6.2f}%")
        print(f"  Average 6M Momentum:  {high_yield['6M_Mom'].mean():>+6.2f}%")
        print(f"  Average Downside Vol: {high_yield['Down_Vol'].mean():>6.2f}%")
        print(f"  Average Score:        {high_yield['Score'].mean():>6.2f}")
    else:
        print("\nNo stocks found with 7%+ yield in the dataset.")

    # SEGMENT ANALYSIS
    print("\n" + "=" * 95)
    print("SEGMENT COMPARISON")
    print("=" * 95)

    for segment in ["Royalty", "Midstream", "Major", "Refinery", "E&P"]:
        seg_data = summary[summary['Segment'] == segment]
        if len(seg_data) > 0:
            print(f"\n{segment.upper()} ({len(seg_data)} stocks):")
            print(f"  Avg Yield:       {seg_data['Div_Yield'].mean():>6.2f}% (range: {seg_data['Div_Yield'].min():.2f}% - {seg_data['Div_Yield'].max():.2f}%)")
            print(f"  Avg 6M Momentum: {seg_data['6M_Mom'].mean():>+6.2f}%")
            print(f"  Avg Down Vol:    {seg_data['Down_Vol'].mean():>6.2f}%")
            print(f"  Avg Max DD:      {seg_data['Max_DD'].mean():>+6.1f}%")
            print(f"  Avg Score:       {seg_data['Score'].mean():>6.2f}")

    # TOP 10 BY SCORE
    print("\n" + "=" * 95)
    print("TOP 10 STOCKS BY COMBINED SCORE (Risk-Adjusted Returns)")
    print("=" * 95)

    top_10 = summary.nlargest(10, 'Score')
    print("\nRank Ticker  Segment    Div Yld   Avg Mom  Down Vol  Max DD    Score    Operations")
    print("-" * 100)
    for i, ticker in enumerate(top_10.index, 1):
        row = top_10.loc[ticker]
        print(f"{i:>3}. {ticker:<6} {row['Segment']:<10} {row['Div_Yield']:>6.2f}% {row['Avg_Mom']:>+8.2f}% "
              f"{row['Down_Vol']:>8.2f}% {row['Max_DD']:>+7.1f}% {row['Score']:>8.2f}  {row['Operations']:<20}")

    # YIELD-FOCUSED RANKING (Top 10 by yield that also have positive momentum)
    print("\n" + "=" * 95)
    print("TOP 10 HIGHEST YIELDS (with Positive Momentum)")
    print("=" * 95)

    positive_mom = summary[summary['Avg_Mom'] > 0].sort_values('Div_Yield', ascending=False).head(10)
    print("\nRank Ticker  Segment    Div Yld   Avg Mom  Down Vol    Score    Operations")
    print("-" * 95)
    for i, ticker in enumerate(positive_mom.index, 1):
        row = positive_mom.loc[ticker]
        print(f"{i:>3}. {ticker:<6} {row['Segment']:<10} {row['Div_Yield']:>6.2f}% {row['Avg_Mom']:>+8.2f}% "
              f"{row['Down_Vol']:>8.2f}% {row['Score']:>8.2f}  {row['Operations']:<20}")

    # PORTFOLIO OPTIMIZATION SCENARIOS
    print("\n" + "=" * 95)
    print("PORTFOLIO ALLOCATION SCENARIOS")
    print("=" * 95)

    CAPITAL = 4000

    # Scenario 1: Pure yield maximization (top 3 by yield with positive momentum)
    print(f"\nSCENARIO 1: Maximum Yield Portfolio (${CAPITAL:,})")
    print("Strategy: Top 3 highest yields with positive momentum, equal-weighted\n")

    top_yield = positive_mom.head(3)
    equal_weight = CAPITAL / 3

    print("Ticker  Div Yld   Avg Mom    Score   Allocation  Annual Div Income")
    print("-" * 75)
    total_div_income = 0
    for ticker in top_yield.index:
        row = top_yield.loc[ticker]
        div_income = equal_weight * row['Div_Yield'] / 100
        total_div_income += div_income
        print(f"{ticker:<6} {row['Div_Yield']:>6.2f}% {row['Avg_Mom']:>+8.2f}% {row['Score']:>8.2f}  ${equal_weight:>8,.0f}   ${div_income:>8,.0f}")

    print("-" * 75)
    print(f"TOTAL                                 ${CAPITAL:>8,.0f}   ${total_div_income:>8,.0f}")
    print(f"Weighted Average Yield: {(total_div_income / CAPITAL * 100):>6.2f}%")

    # Scenario 2: Score-weighted (top 5 by score)
    print(f"\n\nSCENARIO 2: Risk-Adjusted Portfolio (${CAPITAL:,})")
    print("Strategy: Top 5 by score, score-weighted allocation\n")

    top_score = summary.nlargest(5, 'Score')
    total_score = top_score['Score'].sum()

    print("Ticker  Segment    Score   Weight   Allocation  Div Yld  Annual Div Income")
    print("-" * 80)
    total_div_income = 0
    for ticker in top_score.index:
        row = top_score.loc[ticker]
        weight = row['Score'] / total_score
        alloc = CAPITAL * weight
        div_income = alloc * row['Div_Yield'] / 100
        total_div_income += div_income
        print(f"{ticker:<6} {row['Segment']:<10} {row['Score']:>6.2f} {weight*100:>6.2f}%  ${alloc:>8,.0f}   {row['Div_Yield']:>6.2f}% ${div_income:>8,.0f}")

    print("-" * 80)
    print(f"TOTAL                                 ${CAPITAL:>8,.0f}           ${total_div_income:>8,.0f}")
    print(f"Weighted Average Yield: {(total_div_income / CAPITAL * 100):>6.2f}%")

    # Scenario 3: Diversified across segments
    print(f"\n\nSCENARIO 3: Segment-Diversified Portfolio (${CAPITAL:,})")
    print("Strategy: Best stock from each segment, score-weighted\n")

    best_per_segment = summary.groupby('Segment').apply(lambda x: x.nlargest(1, 'Score')).reset_index(drop=True)
    best_per_segment = best_per_segment.set_index(best_per_segment.index.map(lambda x: summary.index[x]))
    total_score = best_per_segment['Score'].sum()

    print("Ticker  Segment    Score   Weight   Allocation  Div Yld  Annual Div Income")
    print("-" * 80)
    total_div_income = 0
    for ticker in best_per_segment.index:
        row = best_per_segment.loc[ticker]
        weight = row['Score'] / total_score
        alloc = CAPITAL * weight
        div_income = alloc * row['Div_Yield'] / 100
        total_div_income += div_income
        print(f"{ticker:<6} {row['Segment']:<10} {row['Score']:>6.2f} {weight*100:>6.2f}%  ${alloc:>8,.0f}   {row['Div_Yield']:>6.2f}% ${div_income:>8,.0f}")

    print("-" * 80)
    print(f"TOTAL                                 ${CAPITAL:>8,.0f}           ${total_div_income:>8,.0f}")
    print(f"Weighted Average Yield: {(total_div_income / CAPITAL * 100):>6.2f}%")

    # KEY INSIGHTS
    print("\n" + "-" * 95)
    print("KEY INSIGHTS & RECOMMENDATIONS")
    print("-" * 95)

    best_7plus = high_yield.nlargest(1, 'Score').index[0] if len(high_yield) > 0 else None
    best_7plus_score = high_yield.loc[best_7plus, 'Score'] if best_7plus else 0

    print(f"""
1. YIELD LANDSCAPE:
   - Highest yield: {summary['Div_Yield'].max():.2f}% ({summary['Div_Yield'].idxmax()})
   - Stocks with 7%+ yield: {len(high_yield)}
   - Best 7%+ stock by score: {best_7plus} ({best_7plus_score:.2f}) if best_7plus else 'None'

2. SEGMENT PERFORMANCE:
   - Best segment by avg score: {summary.groupby('Segment')['Score'].mean().idxmax()}
   - Highest-yielding segment: {summary.groupby('Segment')['Div_Yield'].mean().idxmax()}

3. RISK-ADJUSTED WINNERS:
   - Top 3 by score: {', '.join(top_10.head(3).index.tolist())}
   - XOM (current portfolio) rank: #{summary['Score'].rank(ascending=False).loc['XOM']:.0f} of {len(summary)}

4. TAX CONSIDERATIONS (21% C-Corp):
   - Dividends taxed same as capital gains
   - MLPs (ET, MPLX, EPD) may have K-1 complexity
   - Royalty companies (DMLP, KRP, BSM) also issue K-1s
   - Consider administrative burden vs yield benefit

5. GEOGRAPHIC EXPOSURE:
   - All stocks operate primarily in Western Hemisphere
   - High-trust jurisdictions: US (majority), Canada, limited Europe
   - Minimal geopolitical risk vs international operators

RECOMMENDATIONS:
   - For 7%+ yield: Focus on Royalty companies (DMLP, KRP, BSM)
   - For risk-adjusted returns: Use Scenario 2 allocation
   - For diversification: Use Scenario 3 allocation
   - Consider MLP tax complexity for C-Corps (consult tax advisor)
   - DMLP (14% yield, score {summary.loc['DMLP', 'Score']:.2f}) offers highest yield
   - Top score overall: {summary['Score'].idxmax()} ({summary['Score'].max():.2f})
""")


if __name__ == "__main__":
    main()
