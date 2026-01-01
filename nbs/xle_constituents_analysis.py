"""
XLE Constituent Analysis

Analyzes the top 10 holdings of XLE (Energy Select Sector SPDR) using
total return index (price + reinvested dividends).

Top 10 constituents as of 2025:
1. XOM - Exxon Mobil (23.13%)
2. CVX - Chevron (17.39%)
3. COP - ConocoPhillips (6.62%)
4. WMB - Williams Companies (4.55%)
5. MPC - Marathon Petroleum (4.08%)
6. EOG - EOG Resources (3.94%)
7. PSX - Phillips 66 (3.84%)
8. VLO - Valero Energy (3.81%)
9. SLB - Schlumberger (3.75%)
10. KMI - Kinder Morgan (3.70%)

Total: 76.5% of XLE assets
"""

import pandas as pd
import numpy as np
import yfinance as yf

# XLE Top 10 with weights
XLE_TOP_10 = {
    "XOM": 0.2313,
    "CVX": 0.1739,
    "COP": 0.0662,
    "WMB": 0.0455,
    "MPC": 0.0408,
    "EOG": 0.0394,
    "PSX": 0.0384,
    "VLO": 0.0381,
    "SLB": 0.0375,
    "KMI": 0.0370,
}

LOOKBACK_3M = 63
LOOKBACK_6M = 126


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """
    Fetch total return index for tickers (includes reinvested dividends).

    IMPORTANT: This accounts for dividends, which matters significantly for
    energy stocks (XOM ~3.5% yield, CVX ~4% yield). With 21% flat C-Corp tax,
    dividends and capital gains are equivalent, so total return is what matters.

    Returns:
        DataFrame with total return index for each ticker
    """
    dfs = []
    for ticker in tickers:
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


def calculate_dividend_yield(ticker: str) -> float:
    """Calculate trailing 12-month dividend yield."""
    t = yf.Ticker(ticker)
    try:
        dividend_rate = t.info.get('dividendRate', 0)
        current_price = t.info.get('currentPrice', t.info.get('previousClose', 1))
        if current_price and dividend_rate:
            return (dividend_rate / current_price) * 100
    except:
        pass
    return 0.0


def main():
    print("=" * 70)
    print("XLE CONSTITUENT ANALYSIS - TOTAL RETURN INDEX")
    print("=" * 70)
    print("\nTop 10 Holdings (76.5% of XLE):\n")

    for ticker, weight in XLE_TOP_10.items():
        print(f"  {ticker:<6} {weight*100:>6.2f}%")

    # Fetch data
    print(f"\nFetching 3-year total return data...")
    tickers = list(XLE_TOP_10.keys())
    prices = fetch_total_return_index(tickers)
    returns = calculate_returns(prices)

    print(f"Data range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Trading days: {len(returns)}")

    # Calculate metrics
    mom_3m = calculate_momentum(prices, LOOKBACK_3M)
    mom_6m = calculate_momentum(prices, LOOKBACK_6M)
    downside_vol = calculate_downside_volatility(returns)

    # Dividend yields
    print("\nFetching current dividend yields...")
    div_yields = {ticker: calculate_dividend_yield(ticker) for ticker in tickers}

    # Combined score
    combined_mom = (mom_3m + mom_6m) / 2
    score = combined_mom / downside_vol

    # Create summary table
    summary = pd.DataFrame({
        'XLE_Weight': [XLE_TOP_10[t] * 100 for t in tickers],
        'Div_Yield': [div_yields[t] for t in tickers],
        '3M_Mom': mom_3m,
        '6M_Mom': mom_6m,
        'Avg_Mom': combined_mom,
        'Down_Vol': downside_vol,
        'Score': score,
    }, index=tickers)

    summary = summary.sort_values('XLE_Weight', ascending=False)

    print("\n" + "=" * 70)
    print("CONSTITUENT ANALYSIS")
    print("=" * 70)
    print("\nTicker  XLE Wgt  Div Yld    3M Mom    6M Mom   Avg Mom  Down Vol    Score")
    print("-" * 78)

    for ticker in summary.index:
        row = summary.loc[ticker]
        print(f"{ticker:<6} {row['XLE_Weight']:>6.2f}%  {row['Div_Yield']:>6.2f}%  "
              f"{row['3M_Mom']:>+8.2f}% {row['6M_Mom']:>+8.2f}% {row['Avg_Mom']:>+8.2f}% "
              f"{row['Down_Vol']:>8.2f}% {row['Score']:>8.2f}")

    # Compare to XLE itself
    print("\n" + "=" * 70)
    print("XLE ETF vs WEIGHTED CONSTITUENTS COMPARISON")
    print("=" * 70)

    xle_prices = fetch_total_return_index(['XLE'])
    xle_returns = calculate_returns(xle_prices)
    xle_mom_3m = calculate_momentum(xle_prices, LOOKBACK_3M)['XLE']
    xle_mom_6m = calculate_momentum(xle_prices, LOOKBACK_6M)['XLE']
    xle_down_vol = calculate_downside_volatility(xle_returns)['XLE']
    xle_combined = (xle_mom_3m + xle_mom_6m) / 2
    xle_score = xle_combined / xle_down_vol

    # Calculate weighted average of constituents
    weights = np.array([XLE_TOP_10[t] for t in summary.index])
    weighted_3m = (summary['3M_Mom'] * weights).sum()
    weighted_6m = (summary['6M_Mom'] * weights).sum()
    weighted_avg_mom = (summary['Avg_Mom'] * weights).sum()
    weighted_down_vol = (summary['Down_Vol'] * weights).sum()
    weighted_score = (summary['Score'] * weights).sum()
    weighted_div = (summary['Div_Yield'] * weights).sum()

    print(f"\n{'Metric':<25} {'XLE ETF':>15} {'Wtd Top 10':>15} {'Difference':>15}")
    print("-" * 70)
    print(f"{'3-Month Momentum':<25} {xle_mom_3m:>+14.2f}% {weighted_3m:>+14.2f}% {(weighted_3m - xle_mom_3m):>+14.2f}%")
    print(f"{'6-Month Momentum':<25} {xle_mom_6m:>+14.2f}% {weighted_6m:>+14.2f}% {(weighted_6m - xle_mom_6m):>+14.2f}%")
    print(f"{'Average Momentum':<25} {xle_combined:>+14.2f}% {weighted_avg_mom:>+14.2f}% {(weighted_avg_mom - xle_combined):>+14.2f}%")
    print(f"{'Downside Volatility':<25} {xle_down_vol:>14.2f}% {weighted_down_vol:>14.2f}% {(weighted_down_vol - xle_down_vol):>+14.2f}%")
    print(f"{'Combined Score':<25} {xle_score:>14.2f} {weighted_score:>14.2f} {(weighted_score - xle_score):>+14.2f}")
    print(f"{'Dividend Yield (est)':<25} {'~3.0%':>15} {weighted_div:>14.2f}% {'-':>15}")

    # Best individual stocks
    print("\n" + "=" * 70)
    print("TOP 5 CONSTITUENTS BY SCORE")
    print("=" * 70)

    top_5 = summary.nlargest(5, 'Score')
    print("\nTicker  XLE Wgt  Div Yld   Avg Mom  Down Vol    Score")
    print("-" * 60)
    for ticker in top_5.index:
        row = top_5.loc[ticker]
        print(f"{ticker:<6} {row['XLE_Weight']:>6.2f}%  {row['Div_Yield']:>6.2f}% {row['Avg_Mom']:>+8.2f}% "
              f"{row['Down_Vol']:>8.2f}% {row['Score']:>8.2f}")

    print("\n" + "-" * 70)
    print("INTERPRETATION")
    print("-" * 70)
    print("""
The analysis shows how XLE's top 10 constituents perform individually
versus the ETF wrapper. Key insights:

1. Dividend yields vary significantly across constituents
2. Individual stocks may have better risk-adjusted returns than the ETF
3. The weighted average approximates XLE but with tracking differences
4. Top performers by score could be considered for direct investment

Consider: If the best constituents outperform XLE significantly, direct
investment in those stocks may be preferable to the ETF wrapper.
""")


if __name__ == "__main__":
    main()
