"""
Portfolio Monte Carlo Simulation

Uses historical 3-year daily returns to simulate possible 3-month outcomes
for the given portfolio allocation. Shows distribution of returns, not averages.
"""

import pandas as pd
import numpy as np
import yfinance as yf

# Portfolio allocation with 1% min, 12% max constraints (22 positions)
PORTFOLIO = {
    "PAAS": 0.1148,  # 11.48%
    "HL": 0.1148,    # 11.48%
    "AVDV": 0.0820,  # 8.20%
    "DFIV": 0.0820,  # 8.20%
    "MPLX": 0.0656,  # 6.56%
    "IVAL": 0.0656,  # 6.56%
    "WPM": 0.0492,   # 4.92%
    "AEM": 0.0492,   # 4.92%
    "XOM": 0.0492,   # 4.92%
    "FNV": 0.0328,   # 3.28%
    "SU": 0.0328,    # 3.28%
    "CVE": 0.0328,   # 3.28%
    "TRP": 0.0328,   # 3.28%
    "EPD": 0.0328,   # 3.28%
    "DVN": 0.0328,   # 3.28%
    "BSM": 0.0328,   # 3.28%
    "CVX": 0.0164,   # 1.64%
    "CNQ": 0.0164,   # 1.64%
    "XLE": 0.0164,   # 1.64%
    "ENB": 0.0164,   # 1.64%
    "VLO": 0.0164,   # 1.64%
    "VNOM": 0.0164,  # 1.64%
}

TOTAL_CAPITAL = 60_000
SIMULATION_DAYS = 63  # ~3 months of trading days
NUM_SIMULATIONS = 10_000


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pd.DataFrame:
    """
    Fetch total return prices for tickers (includes reinvested dividends).

    IMPORTANT: This accounts for dividends, which matters significantly for
    energy stocks (XOM ~3.5% yield, CVX ~4% yield). With 21% flat C-Corp tax,
    dividends and capital gains are equivalent, so total return is what matters.
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


def calculate_portfolio_returns(returns: pd.DataFrame, weights: dict) -> pd.Series:
    """Calculate weighted portfolio daily returns."""
    portfolio_returns = pd.Series(0.0, index=returns.index)
    for ticker, weight in weights.items():
        if ticker in returns.columns:
            portfolio_returns += weight * returns[ticker]
    return portfolio_returns


def run_bootstrap_simulation(
    returns: pd.DataFrame,
    weights: dict,
    num_simulations: int = 10_000,
    simulation_days: int = 63,
) -> np.ndarray:
    """
    Bootstrap simulation: randomly sample from historical daily returns
    to create possible 3-month paths.

    Returns array of final portfolio values after simulation_days.
    """
    portfolio_returns = calculate_portfolio_returns(returns, weights)
    daily_returns = portfolio_returns.values

    final_values = []

    for _ in range(num_simulations):
        # Randomly sample simulation_days returns with replacement
        sampled_returns = np.random.choice(daily_returns, size=simulation_days, replace=True)

        # Calculate cumulative return
        cumulative_return = np.prod(1 + sampled_returns) - 1
        final_value = TOTAL_CAPITAL * (1 + cumulative_return)
        final_values.append(final_value)

    return np.array(final_values)


def run_block_bootstrap_simulation(
    returns: pd.DataFrame,
    weights: dict,
    num_simulations: int = 10_000,
    simulation_days: int = 63,
    block_size: int = 5,
) -> np.ndarray:
    """
    Block bootstrap: preserves some autocorrelation by sampling blocks of returns.
    More realistic than pure random sampling.
    """
    portfolio_returns = calculate_portfolio_returns(returns, weights)
    daily_returns = portfolio_returns.values
    n = len(daily_returns)

    final_values = []

    for _ in range(num_simulations):
        path = []
        while len(path) < simulation_days:
            # Random starting point for block
            start = np.random.randint(0, n - block_size)
            block = daily_returns[start:start + block_size]
            path.extend(block)

        path = path[:simulation_days]
        cumulative_return = np.prod(1 + np.array(path)) - 1
        final_value = TOTAL_CAPITAL * (1 + cumulative_return)
        final_values.append(final_value)

    return np.array(final_values)


def calculate_historical_3m_returns(returns: pd.DataFrame, weights: dict) -> np.ndarray:
    """
    Calculate all historical rolling 3-month portfolio returns.
    This shows what actually happened in every 3-month window over 3 years.
    """
    portfolio_returns = calculate_portfolio_returns(returns, weights)

    rolling_3m = []
    for i in range(63, len(portfolio_returns)):
        window = portfolio_returns.iloc[i-63:i]
        cumulative = (1 + window).prod() - 1
        rolling_3m.append(cumulative)

    return np.array(rolling_3m)


def print_distribution_stats(values: np.ndarray, title: str):
    """Print distribution statistics."""
    returns = (values / TOTAL_CAPITAL - 1) * 100  # Convert to percentage

    print(f"\n{'='*60}")
    print(title)
    print("="*60)

    print(f"\nPortfolio Value Distribution (starting from ${TOTAL_CAPITAL:,}):")
    print(f"  Minimum:       ${np.min(values):>12,.0f}  ({np.min(returns):>+7.1f}%)")
    print(f"  1st percentile:${np.percentile(values, 1):>12,.0f}  ({np.percentile(returns, 1):>+7.1f}%)")
    print(f"  5th percentile:${np.percentile(values, 5):>12,.0f}  ({np.percentile(returns, 5):>+7.1f}%)")
    print(f"  10th percentile:${np.percentile(values, 10):>11,.0f}  ({np.percentile(returns, 10):>+7.1f}%)")
    print(f"  25th percentile:${np.percentile(values, 25):>11,.0f}  ({np.percentile(returns, 25):>+7.1f}%)")
    print(f"  Median (50th): ${np.percentile(values, 50):>12,.0f}  ({np.percentile(returns, 50):>+7.1f}%)")
    print(f"  75th percentile:${np.percentile(values, 75):>11,.0f}  ({np.percentile(returns, 75):>+7.1f}%)")
    print(f"  90th percentile:${np.percentile(values, 90):>11,.0f}  ({np.percentile(returns, 90):>+7.1f}%)")
    print(f"  95th percentile:${np.percentile(values, 95):>11,.0f}  ({np.percentile(returns, 95):>+7.1f}%)")
    print(f"  99th percentile:${np.percentile(values, 99):>11,.0f}  ({np.percentile(returns, 99):>+7.1f}%)")
    print(f"  Maximum:       ${np.max(values):>12,.0f}  ({np.max(returns):>+7.1f}%)")

    print(f"\nKey Risk Metrics:")
    print(f"  Probability of loss:      {(returns < 0).mean()*100:>6.1f}%")
    print(f"  Probability of >10% loss: {(returns < -10).mean()*100:>6.1f}%")
    print(f"  Probability of >20% loss: {(returns < -20).mean()*100:>6.1f}%")
    print(f"  Probability of >30% loss: {(returns < -30).mean()*100:>6.1f}%")

    print(f"\nUpside Potential:")
    print(f"  Probability of >10% gain: {(returns > 10).mean()*100:>6.1f}%")
    print(f"  Probability of >20% gain: {(returns > 20).mean()*100:>6.1f}%")
    print(f"  Probability of >30% gain: {(returns > 30).mean()*100:>6.1f}%")
    print(f"  Probability of >50% gain: {(returns > 50).mean()*100:>6.1f}%")

    # Value at Risk
    var_95 = np.percentile(returns, 5)
    var_99 = np.percentile(returns, 1)
    cvar_95 = returns[returns <= var_95].mean()

    print(f"\nValue at Risk:")
    print(f"  VaR 95% (5th percentile): {var_95:>+7.1f}% (${TOTAL_CAPITAL * var_95/100:>+,.0f})")
    print(f"  VaR 99% (1st percentile): {var_99:>+7.1f}% (${TOTAL_CAPITAL * var_99/100:>+,.0f})")
    print(f"  CVaR 95% (expected loss in worst 5%): {cvar_95:>+7.1f}%")


def print_historical_pain_analysis(returns: pd.DataFrame, weights: dict):
    """Analyze historical pain: drawdowns and recovery times."""
    portfolio_returns = calculate_portfolio_returns(returns, weights)

    # Calculate cumulative returns
    cumulative = (1 + portfolio_returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max

    print(f"\n{'='*60}")
    print("HISTORICAL PAIN ANALYSIS (3-Year Portfolio)")
    print("="*60)

    print(f"\nDrawdown Statistics:")
    print(f"  Maximum drawdown:     {drawdown.min()*100:>+7.1f}%")
    print(f"  Current drawdown:     {drawdown.iloc[-1]*100:>+7.1f}%")

    # Calculate underwater periods
    underwater = drawdown < 0
    periods = []
    current_start = None

    for i, (date, is_uw) in enumerate(underwater.items()):
        if is_uw and current_start is None:
            current_start = i
        elif not is_uw and current_start is not None:
            periods.append(i - current_start)
            current_start = None

    if current_start is not None:
        periods.append(len(underwater) - current_start)

    if periods:
        print(f"  Longest underwater:   {max(periods)} days")
        print(f"  Average underwater:   {np.mean(periods):.0f} days")
        print(f"  Number of drawdowns:  {len(periods)}")

    # Monthly returns analysis
    monthly_returns = portfolio_returns.resample('ME').apply(lambda x: (1+x).prod() - 1)

    print(f"\nMonthly Return Distribution:")
    print(f"  Worst month:          {monthly_returns.min()*100:>+7.1f}%")
    print(f"  Best month:           {monthly_returns.max()*100:>+7.1f}%")
    print(f"  Median month:         {monthly_returns.median()*100:>+7.1f}%")
    print(f"  % of months positive: {(monthly_returns > 0).mean()*100:>6.1f}%")

    # Total return
    total_return = (cumulative.iloc[-1] - 1) * 100
    annualized_return = ((1 + total_return/100) ** (252/len(portfolio_returns)) - 1) * 100

    print(f"\nTotal Performance:")
    print(f"  3-Year total return:  {total_return:>+7.1f}%")
    print(f"  Annualized return:    {annualized_return:>+7.1f}%")


def main():
    print("="*60)
    print("PORTFOLIO MONTE CARLO SIMULATION")
    print("="*60)

    print(f"\nPortfolio Allocation (1% min, 12% max - 22 positions):")
    for ticker, weight in sorted(PORTFOLIO.items(), key=lambda x: -x[1]):
        allocation = TOTAL_CAPITAL * weight
        print(f"  {ticker:<6} {weight*100:>6.2f}%  ${allocation:>8,.0f}")

    print(f"\nFetching 3-year historical data...")
    tickers = list(PORTFOLIO.keys())
    prices = fetch_total_return_index(tickers)
    returns = calculate_returns(prices)

    print(f"Data range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"Trading days: {len(returns)}")

    # Historical pain analysis
    print_historical_pain_analysis(returns, PORTFOLIO)

    # Historical 3-month returns (what actually happened)
    historical_3m = calculate_historical_3m_returns(returns, PORTFOLIO)
    historical_values = TOTAL_CAPITAL * (1 + historical_3m)
    print_distribution_stats(
        historical_values,
        "HISTORICAL 3-MONTH ROLLING RETURNS (What Actually Happened)"
    )

    # Bootstrap simulation
    print(f"\nRunning {NUM_SIMULATIONS:,} bootstrap simulations...")
    bootstrap_values = run_bootstrap_simulation(
        returns, PORTFOLIO, NUM_SIMULATIONS, SIMULATION_DAYS
    )
    print_distribution_stats(
        bootstrap_values,
        "BOOTSTRAP SIMULATION (Random Sampling of Daily Returns)"
    )

    # Block bootstrap (more realistic)
    print(f"\nRunning {NUM_SIMULATIONS:,} block bootstrap simulations...")
    block_values = run_block_bootstrap_simulation(
        returns, PORTFOLIO, NUM_SIMULATIONS, SIMULATION_DAYS, block_size=5
    )
    print_distribution_stats(
        block_values,
        "BLOCK BOOTSTRAP SIMULATION (Preserves Some Autocorrelation)"
    )

    # Summary comparison
    print(f"\n{'='*60}")
    print("SUMMARY: 3-MONTH OUTLOOK COMPARISON")
    print("="*60)

    print(f"\n{'Metric':<30} {'Historical':>15} {'Bootstrap':>15} {'Block Boot':>15}")
    print("-"*75)

    for method, values in [
        ("Historical", historical_values),
        ("Bootstrap", bootstrap_values),
        ("Block Bootstrap", block_values),
    ]:
        returns_pct = (values / TOTAL_CAPITAL - 1) * 100
        print(f"  Median return:              {np.median(returns_pct):>+14.1f}%")

    print(f"\n{'Percentile':<20} {'Historical':>15} {'Bootstrap':>15} {'Block Boot':>15}")
    print("-"*65)

    for pct in [5, 25, 50, 75, 95]:
        h = (np.percentile(historical_values, pct) / TOTAL_CAPITAL - 1) * 100
        b = (np.percentile(bootstrap_values, pct) / TOTAL_CAPITAL - 1) * 100
        bb = (np.percentile(block_values, pct) / TOTAL_CAPITAL - 1) * 100
        print(f"  {pct}th percentile:        {h:>+14.1f}% {b:>+14.1f}% {bb:>+14.1f}%")

    print(f"\n{'Risk Metric':<25} {'Historical':>15} {'Bootstrap':>15} {'Block Boot':>15}")
    print("-"*70)

    for label, values in [
        ("Historical", historical_values),
        ("Bootstrap", bootstrap_values),
        ("Block Bootstrap", block_values),
    ]:
        ret = (values / TOTAL_CAPITAL - 1) * 100
        prob_loss = (ret < 0).mean() * 100
        prob_20_loss = (ret < -20).mean() * 100
        var_95 = np.percentile(ret, 5)

    h_ret = (historical_values / TOTAL_CAPITAL - 1) * 100
    b_ret = (bootstrap_values / TOTAL_CAPITAL - 1) * 100
    bb_ret = (block_values / TOTAL_CAPITAL - 1) * 100

    print(f"  Prob of loss:            {(h_ret < 0).mean()*100:>14.1f}% {(b_ret < 0).mean()*100:>14.1f}% {(bb_ret < 0).mean()*100:>14.1f}%")
    print(f"  Prob of >20% loss:       {(h_ret < -20).mean()*100:>14.1f}% {(b_ret < -20).mean()*100:>14.1f}% {(bb_ret < -20).mean()*100:>14.1f}%")
    print(f"  VaR 95%:                 {np.percentile(h_ret, 5):>+14.1f}% {np.percentile(b_ret, 5):>+14.1f}% {np.percentile(bb_ret, 5):>+14.1f}%")

    print(f"\n" + "-"*60)
    print("INTERPRETATION")
    print("-"*60)
    print("""
Based on 3-year historical data and Monte Carlo simulation:

- Historical: Shows actual rolling 3-month returns that occurred
- Bootstrap: Randomly samples daily returns (may understate tail risk)
- Block Bootstrap: Samples blocks of returns (more realistic volatility clustering)

The distributions show what your $60,000 portfolio could look like after 3 months.
Focus on the 5th percentile (VaR 95%) for worst-case planning.
""")


if __name__ == "__main__":
    main()
