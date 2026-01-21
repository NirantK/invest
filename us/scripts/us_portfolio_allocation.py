"""
US Portfolio Allocation using Sortino-weighted Momentum

Universe:
- WPM: Wheaton Precious Metals (silver-heavy streamer)
- PAAS: Pan American Silver (silver miner)
- XOM: Exxon Mobil (highest quality oil major)
- CVX: Chevron (#2 quality oil major)
- MSTR: Strategy Inc (Bitcoin proxy)
- GLD: SPDR Gold Trust (cash parking, correlates with India gold holdings)

Constraints:
- Total deployable: $60,000
- Precious metals cap: $18,242 (30% of total INR+USD portfolio)
- Bitcoin cap: $4,378 (5% of total portfolio)
"""

import click
import pandas as pd
import numpy as np
import yfinance as yf

# Configuration
# Expanded universe: All NYSE/NASDAQ oil & gas + precious metals + ex-US value
# All securities compete on pure Sortino basis (except MSTR which has special DCA rules)
TICKERS = [
    # Precious Metals Royalty/Streaming
    "WPM",   # Wheaton Precious Metals - 50% silver streamer
    "PAAS",  # Pan American Silver - silver miner
    "FNV",   # Franco-Nevada - gold streamer + energy royalties
    # Tier 1 Gold/Silver Miners
    "AEM",   # Agnico Eagle - lowest AISC (~$1,275), 87% safe jurisdictions
    "HL",    # Hecla Mining - silver-primary, negative cash costs via byproducts
    # Integrated Oil Majors
    "XOM",   # Exxon Mobil - highest quality integrated oil major
    "CVX",   # Chevron - #2 quality oil major, strong dividend
    "CNQ",   # Canadian Natural Resources - 25yr dividend growth
    "SU",    # Suncor Energy - Canadian integrated
    "CVE",   # Cenovus Energy - Canadian integrated
    # Energy ETF
    "XLE",   # Energy Select Sector SPDR - broad energy ETF
    # Midstream/Pipelines (1099 C-corps only, no MLPs)
    "ENB",   # Enbridge - 5.6% yield
    "TRP",   # TC Energy - 4.5% yield
    "KMI",   # Kinder Morgan - converted to C-corp, 1099
    "WMB",   # Williams Companies - converted to C-corp, 1099
    "OKE",   # ONEOK - converted to C-corp, 1099
    # Refineries
    "VLO",   # Valero Energy
    "PSX",   # Phillips 66
    "MPC",   # Marathon Petroleum
    "DINO",  # HF Sinclair
    # E&P
    "COP",   # ConocoPhillips
    "DVN",   # Devon Energy - 6.5% yield
    "OXY",   # Occidental Petroleum
    # Ex-US Value (DFA, Avantis - research-backed, long track record teams)
    "AVDV",  # Avantis International Small Cap Value
    "DFIV",  # DFA International Value (gold standard)
    "IVAL",  # Alpha Architect Intl Quant Value
    # Bitcoin proxy (special DCA rules)
    "MSTR",
]
TOTAL_CAPITAL = 60_000  # Default, can be overridden via --capital flag
PRECIOUS_METALS_CAP = 18_242  # WPM + PAAS + FNV combined cap (30% of total portfolio)
BITCOIN_CAP = 4_378  # MSTR (5% of total portfolio)
BITCOIN_MONTHLY_DCA_PCT = 0.001  # 0.1% per month when momentum is negative
DCA_MONTHS = 3  # Reach target allocation in 3 months
DCA_WEEKS = 12  # 3 months = 12 weeks
ROUND_TO = 100  # Round allocations to nearest $100
LOOKBACK_3M = 63   # ~3 months
LOOKBACK_6M = 126  # ~6 months
RISK_FREE_RATE = 0.05  # ~5% for Sortino calculation
MIN_ALLOCATION_PCT = 0.05  # 5% minimum - positions below this get zeroed out
SECTOR_CAP_PCT = 0.33  # 33% maximum per sector

# Sector definitions (with 33% caps enforced)
SECTOR_GOLD = ["FNV", "AEM"]  # Gold-primary streamers/miners
SECTOR_SILVER = ["PAAS", "HL"]  # Silver-primary miners
SECTOR_PRECIOUS_MIXED = ["WPM"]  # 50/50 gold/silver (counted separately)
SECTOR_OIL_GAS = ["XOM", "CVX", "CNQ", "SU", "CVE", "XLE", "ENB", "TRP", "KMI", "WMB", "OKE", "VLO", "PSX", "MPC", "DINO", "COP", "DVN", "OXY"]
SECTOR_EX_US_VALUE = ["AVDV", "DFIV", "IVAL"]
SECTOR_BITCOIN = ["MSTR"]  # Special DCA rules

# Legacy groupings for reporting
PRECIOUS_METALS = ["WPM", "PAAS", "FNV", "AEM", "HL"]
ENERGY = ["XOM", "CVX", "XLE"]
BITCOIN = ["MSTR"]
EX_US_VALUE = ["AVDV", "DFIV", "IVAL"]


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


def calculate_momentum(prices: pd.DataFrame, lookback: int = 126) -> pd.Series:
    """Calculate momentum (total return) for a given lookback period."""
    if len(prices) < lookback:
        lookback = len(prices)
    return (prices.iloc[-1] / prices.iloc[-lookback]) - 1


def calculate_downside_volatility(returns: pd.DataFrame) -> pd.Series:
    """Calculate annualized downside volatility (std of negative returns only)."""
    downside_vol = {}
    for col in returns.columns:
        col_returns = returns[col].dropna()
        negative_returns = col_returns[col_returns < 0]
        if len(negative_returns) > 0:
            downside_vol[col] = negative_returns.std() * np.sqrt(252)
        else:
            downside_vol[col] = 0.0001  # Avoid division by zero
    return pd.Series(downside_vol)


def calculate_drawdown_metrics(prices: pd.DataFrame) -> dict:
    """
    Calculate maximum drawdown and duration metrics for each ticker.

    Returns dict with:
    - max_drawdown: Maximum peak-to-trough decline
    - max_drawdown_duration: Days spent in the worst drawdown
    - avg_drawdown_duration: Average days to recover from drawdowns
    - current_drawdown: Current drawdown from peak
    - rolling_3m_max_drawdown: Worst 3-month rolling max drawdown over the period
    """
    metrics = {}

    for ticker in prices.columns:
        price = prices[ticker].dropna()

        # Calculate running maximum (peak)
        running_max = price.cummax()

        # Calculate drawdown series
        drawdown = (price - running_max) / running_max

        # Maximum drawdown
        max_dd = drawdown.min()

        # Current drawdown
        current_dd = drawdown.iloc[-1]

        # Find drawdown durations
        # A drawdown period is when price is below its running max
        in_drawdown = drawdown < 0

        # Calculate duration of each drawdown period
        drawdown_periods = []
        current_period_start = None

        for i, (date, is_dd) in enumerate(in_drawdown.items()):
            if is_dd and current_period_start is None:
                current_period_start = i
            elif not is_dd and current_period_start is not None:
                drawdown_periods.append(i - current_period_start)
                current_period_start = None

        # If still in drawdown, count to end
        if current_period_start is not None:
            drawdown_periods.append(len(in_drawdown) - current_period_start)

        max_dd_duration = max(drawdown_periods) if drawdown_periods else 0
        avg_dd_duration = np.mean(drawdown_periods) if drawdown_periods else 0

        # Rolling 3-month (63 trading days) max drawdown
        rolling_3m_dd = []
        window = 63
        for i in range(window, len(price)):
            window_prices = price.iloc[i-window:i]
            window_max = window_prices.cummax()
            window_dd = ((window_prices - window_max) / window_max).min()
            rolling_3m_dd.append(window_dd)

        worst_rolling_3m_dd = min(rolling_3m_dd) if rolling_3m_dd else max_dd

        metrics[ticker] = {
            "max_drawdown": max_dd,
            "max_dd_duration_days": max_dd_duration,
            "avg_dd_duration_days": avg_dd_duration,
            "current_drawdown": current_dd,
            "worst_rolling_3m_dd": worst_rolling_3m_dd,
        }

    return metrics


def calculate_combined_score(prices: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """
    Calculate combined score: equally weighted 3M + 6M momentum, normalized by downside volatility.
    Score = (0.5 * mom_3m + 0.5 * mom_6m) / downside_volatility
    """
    mom_3m = calculate_momentum(prices, LOOKBACK_3M)
    mom_6m = calculate_momentum(prices, LOOKBACK_6M)
    downside_vol = calculate_downside_volatility(returns)

    # Equally weight 3M and 6M momentum
    combined_momentum = 0.5 * mom_3m + 0.5 * mom_6m

    # Normalize by downside volatility
    score = combined_momentum / downside_vol

    return score, mom_3m, mom_6m, downside_vol


def apply_momentum_filter(momentum: pd.Series) -> pd.Series:
    """Filter out assets with negative momentum."""
    return momentum[momentum > 0]


def calculate_sortino_weights(sortino: pd.Series) -> pd.Series:
    """Calculate weights proportional to Sortino ratio."""
    positive_sortino = sortino[sortino > 0]
    if len(positive_sortino) == 0:
        return pd.Series(dtype=float)

    weights = positive_sortino / positive_sortino.sum()
    return weights


def apply_constraints(weights: pd.Series, prices: pd.DataFrame, min_allocation_pct: float = MIN_ALLOCATION_PCT, max_allocation_pct: float = 1.0) -> pd.Series:
    """
    Apply position and sector constraints:
    - Minimum allocation threshold - positions below get zeroed out
    - Maximum allocation threshold - positions above get capped
    - Sector caps: 33% maximum per sector
    - Redistribute to preserve score-based proportions within constraints

    Approach: Iteratively remove/cap and redistribute until stable
    """
    allocation = weights * TOTAL_CAPITAL
    min_amount = TOTAL_CAPITAL * min_allocation_pct
    max_amount = TOTAL_CAPITAL * max_allocation_pct
    sector_cap_amount = TOTAL_CAPITAL * SECTOR_CAP_PCT

    # Iterative process to apply constraints
    for iteration in range(100):  # Max iterations
        changed = False

        # Step 1: Zero out positions below minimum
        for t in allocation.index:
            if 0 < allocation[t] < min_amount:
                allocation[t] = 0
                changed = True

        # Step 2: Cap positions above maximum
        for t in allocation.index:
            if allocation[t] > max_amount:
                allocation[t] = max_amount
                changed = True

        # Step 3: Apply sector caps
        # Gold sector
        gold_total = sum(allocation[t] for t in SECTOR_GOLD if t in allocation.index)
        if gold_total > sector_cap_amount:
            scale_factor = sector_cap_amount / gold_total
            for t in SECTOR_GOLD:
                if t in allocation.index:
                    allocation[t] *= scale_factor
            changed = True

        # Silver sector
        silver_total = sum(allocation[t] for t in SECTOR_SILVER if t in allocation.index)
        if silver_total > sector_cap_amount:
            scale_factor = sector_cap_amount / silver_total
            for t in SECTOR_SILVER:
                if t in allocation.index:
                    allocation[t] *= scale_factor
            changed = True

        # Mixed precious metals (WPM)
        mixed_total = sum(allocation[t] for t in SECTOR_PRECIOUS_MIXED if t in allocation.index)
        if mixed_total > sector_cap_amount:
            scale_factor = sector_cap_amount / mixed_total
            for t in SECTOR_PRECIOUS_MIXED:
                if t in allocation.index:
                    allocation[t] *= scale_factor
            changed = True

        # Oil & Gas sector
        oil_gas_total = sum(allocation[t] for t in SECTOR_OIL_GAS if t in allocation.index)
        if oil_gas_total > sector_cap_amount:
            scale_factor = sector_cap_amount / oil_gas_total
            for t in SECTOR_OIL_GAS:
                if t in allocation.index:
                    allocation[t] *= scale_factor
            changed = True

        # Ex-US Value sector
        ex_us_total = sum(allocation[t] for t in SECTOR_EX_US_VALUE if t in allocation.index)
        if ex_us_total > sector_cap_amount:
            scale_factor = sector_cap_amount / ex_us_total
            for t in SECTOR_EX_US_VALUE:
                if t in allocation.index:
                    allocation[t] *= scale_factor
            changed = True

        # Step 4: Renormalize to TOTAL_CAPITAL
        current_total = allocation.sum()
        if abs(current_total - TOTAL_CAPITAL) > 1:  # More than $1 off
            allocation = allocation * (TOTAL_CAPITAL / current_total)
            changed = True

        # If nothing changed in this iteration, we're converged
        if not changed:
            break

    return allocation


def calculate_portfolio_metrics(
    shares: pd.DataFrame,
    returns: pd.DataFrame,
    score: pd.Series,
    mom_3m: pd.Series,
    mom_6m: pd.Series,
    downside_vol: pd.Series,
) -> dict:
    """Calculate portfolio-level risk and return metrics."""
    active_tickers = [t for t in shares.index if shares.loc[t, "Allocation_USD"] > 0]

    if not active_tickers:
        return {"num_positions": 0}

    weights = shares.loc[active_tickers, "Weight_Pct"] / 100

    # Weighted average metrics
    weighted_mom_3m = sum(weights[t] * mom_3m[t] for t in active_tickers)
    weighted_mom_6m = sum(weights[t] * mom_6m[t] for t in active_tickers)
    weighted_downside_vol = sum(weights[t] * downside_vol[t] for t in active_tickers)
    weighted_score = sum(weights[t] * score[t] for t in active_tickers)

    # Concentration metrics
    num_positions = len(active_tickers)
    max_position_weight = weights.max()
    top_3_concentration = weights.nlargest(min(3, num_positions)).sum()

    # Portfolio returns (simple weighted average of daily returns)
    portfolio_returns = sum(weights[t] * returns[t] for t in active_tickers)
    portfolio_vol = portfolio_returns.std() * np.sqrt(252)
    portfolio_downside = portfolio_returns[portfolio_returns < 0].std() * np.sqrt(252)

    return {
        "num_positions": num_positions,
        "weighted_mom_3m": weighted_mom_3m,
        "weighted_mom_6m": weighted_mom_6m,
        "weighted_downside_vol": weighted_downside_vol,
        "weighted_score": weighted_score,
        "max_position_weight": max_position_weight,
        "top_3_concentration": top_3_concentration,
        "portfolio_vol": portfolio_vol,
        "portfolio_downside_vol": portfolio_downside,
    }


def round_to_nearest(value: float, multiple: int = 1000) -> int:
    """Round to nearest multiple (default $1000, fallback to $100 for small amounts)."""
    if value < 500:
        return round(value / 100) * 100
    return round(value / multiple) * multiple


def calculate_shares(allocation: pd.Series, prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate dollar amounts rounded to nearest $1000 (fractional shares supported)."""
    latest_prices = prices.iloc[-1]

    # Round allocations to nearest $1000 (or $100 for small amounts)
    rounded_allocations = {t: round_to_nearest(allocation[t]) for t in allocation.index}

    shares = pd.DataFrame({
        "Ticker": allocation.index,
        "Allocation_USD": [rounded_allocations[t] for t in allocation.index],
        "Price": [latest_prices[t] for t in allocation.index],
        "Shares": [rounded_allocations[t] / latest_prices[t] for t in allocation.index]
    })
    shares["Weight_Pct"] = (shares["Allocation_USD"] / shares["Allocation_USD"].sum() * 100).round(2)
    return shares.set_index("Ticker")


@click.command()
@click.option(
    "--min-allocation",
    "-m",
    type=float,
    default=0.05,
    help="Minimum allocation percentage (0.05 = 5%). Positions below this get zeroed out.",
)
@click.option(
    "--max-allocation",
    "-M",
    type=float,
    default=1.0,
    help="Maximum allocation percentage (0.12 = 12%). Positions above this get capped.",
)
@click.option(
    "--capital",
    "-c",
    type=int,
    default=60000,
    help="Total capital to allocate (default: 60000).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress detailed output, show only summary.",
)
def main(min_allocation: float, max_allocation: float, capital: int, quiet: bool):
    global TOTAL_CAPITAL, PRECIOUS_METALS_CAP, BITCOIN_CAP
    TOTAL_CAPITAL = capital
    PRECIOUS_METALS_CAP = int(capital * 0.304)  # 30.4% of total
    BITCOIN_CAP = int(capital * 0.073)  # 7.3% of total
    print("=" * 60)
    print("US PORTFOLIO ALLOCATION - COMBINED MOMENTUM SCORE")
    print("=" * 60)
    print(f"\nMinimum allocation threshold: {min_allocation*100:.0f}%")
    print(f"Maximum allocation threshold: {max_allocation*100:.0f}%")
    print(f"Fetching data for: {TICKERS}")

    # Fetch data
    prices = fetch_total_return_index(TICKERS)
    returns = calculate_returns(prices)

    print(f"Data range: {prices.index[0].date()} to {prices.index[-1].date()}")

    # Calculate combined score: (0.5 * mom_3m + 0.5 * mom_6m) / downside_volatility
    score, mom_3m, mom_6m, downside_vol = calculate_combined_score(prices, returns)
    combined_momentum = 0.5 * mom_3m + 0.5 * mom_6m

    print(f"\n{'Ticker':<6} {'3M Mom':>10} {'6M Mom':>10} {'Avg Mom':>10} {'Down Vol':>10} {'Score':>10} {'Status':>8}")
    print("-" * 70)
    for ticker in TICKERS:
        if ticker in prices.columns:
            # Pass if combined momentum is positive
            status = "PASS" if combined_momentum[ticker] > 0 else "FAIL"
            print(f"  {ticker:<6} {mom_3m[ticker]*100:>+9.2f}% {mom_6m[ticker]*100:>+9.2f}% "
                  f"{combined_momentum[ticker]*100:>+9.2f}% {downside_vol[ticker]*100:>9.2f}% "
                  f"{score[ticker]:>9.2f} [{status}]")

    # Calculate drawdown metrics (uses full 3-year history)
    dd_metrics = calculate_drawdown_metrics(prices)

    print(f"\n" + "=" * 60)
    print("DRAWDOWN ANALYSIS (3-Year History)")
    print("=" * 60)
    print(f"\n{'Ticker':<6} {'Max DD':>10} {'Max Dur':>10} {'Avg Dur':>10} {'Curr DD':>10} {'3M Roll DD':>12}")
    print("-" * 70)
    for ticker in TICKERS:
        if ticker in prices.columns:
            m = dd_metrics[ticker]
            print(f"  {ticker:<6} {m['max_drawdown']*100:>9.1f}% {m['max_dd_duration_days']:>8.0f}d "
                  f"{m['avg_dd_duration_days']:>8.1f}d {m['current_drawdown']*100:>9.1f}% "
                  f"{m['worst_rolling_3m_dd']*100:>11.1f}%")

    # Filter by combined momentum (must be positive)
    passing_tickers = apply_momentum_filter(combined_momentum)
    print(f"\nTickers passing momentum filter: {list(passing_tickers.index)}")

    # Filter score to only passing tickers
    score_filtered = score[passing_tickers.index]

    # Calculate weights proportional to score
    weights = calculate_sortino_weights(score_filtered)
    print(f"\nRaw Score Weights (before constraints):")
    for ticker in weights.index:
        print(f"  {ticker}: {weights[ticker]*100:.1f}%")

    # Apply constraints
    allocation = apply_constraints(weights, prices, min_allocation, max_allocation)

    # Calculate shares
    shares = calculate_shares(allocation, prices)

    print(f"\n" + "=" * 60)
    print("FINAL ALLOCATION")
    print("=" * 60)
    print(f"\nTotal Capital: ${TOTAL_CAPITAL:,.0f}")
    print(f"Precious Metals Cap: ${PRECIOUS_METALS_CAP:,.0f}")
    print(f"Bitcoin Cap: ${BITCOIN_CAP:,.0f}")
    print()
    print(shares.to_string())

    # Summary by category
    print(f"\n" + "-" * 40)
    print("ALLOCATION BY CATEGORY")
    print("-" * 40)

    # Calculate allocations by logical grouping (for reporting only)
    pm_alloc = shares.loc[[t for t in PRECIOUS_METALS if t in shares.index and shares.loc[t, "Allocation_USD"] > 0], "Allocation_USD"].sum()
    energy_alloc = shares.loc[[t for t in ENERGY if t in shares.index and shares.loc[t, "Allocation_USD"] > 0], "Allocation_USD"].sum()
    btc_alloc = shares.loc[[t for t in BITCOIN if t in shares.index], "Allocation_USD"].sum()
    exus_alloc = shares.loc[[t for t in EX_US_VALUE if t in shares.index and shares.loc[t, "Allocation_USD"] > 0], "Allocation_USD"].sum()

    # Build ticker strings for display
    pm_active = [t for t in PRECIOUS_METALS if t in shares.index and shares.loc[t, "Allocation_USD"] > 0]
    energy_active = [t for t in ENERGY if t in shares.index and shares.loc[t, "Allocation_USD"] > 0]
    exus_active = [t for t in EX_US_VALUE if t in shares.index and shares.loc[t, "Allocation_USD"] > 0]

    if pm_active:
        print(f"Precious Metals ({'+'.join(pm_active)}): ${pm_alloc:,.0f} ({pm_alloc/TOTAL_CAPITAL*100:.1f}%)")
    if energy_active:
        print(f"Energy ({'+'.join(energy_active)}): ${energy_alloc:,.0f} ({energy_alloc/TOTAL_CAPITAL*100:.1f}%)")
    if exus_active:
        print(f"Ex-US Value ({'+'.join(exus_active)}): ${exus_alloc:,.0f} ({exus_alloc/TOTAL_CAPITAL*100:.1f}%)")
    print(f"Bitcoin (MSTR):             ${btc_alloc:,.0f} ({btc_alloc/TOTAL_CAPITAL*100:.1f}%)")

    # Category exposure report (no caps enforced - pure score competition)
    print(f"\n" + "-" * 40)
    print("CATEGORY EXPOSURE (Reference Only)")
    print("-" * 40)
    print(f"Precious Metals: ${pm_alloc:,.0f} ({pm_alloc/TOTAL_CAPITAL*100:.1f}%) [Reference cap was 30%]")
    print(f"Energy:          ${energy_alloc:,.0f} ({energy_alloc/TOTAL_CAPITAL*100:.1f}%) [Always in competition]")
    print(f"Ex-US Value:     ${exus_alloc:,.0f} ({exus_alloc/TOTAL_CAPITAL*100:.1f}%)")
    print(f"Bitcoin:         ${btc_alloc:,.0f} ({btc_alloc/TOTAL_CAPITAL*100:.1f}%) [Reference cap was 5%]")
    print(f"Position constraints: {min_allocation*100:.0f}% minimum, {max_allocation*100:.0f}% maximum")

    # MSTR DCA Plan
    print(f"\n" + "-" * 40)
    print("MSTR (BITCOIN) DCA PLAN")
    print("-" * 40)
    mstr_combined_momentum = combined_momentum.get("MSTR", 0)
    mstr_price = prices["MSTR"].iloc[-1]
    monthly_dca_amount = TOTAL_CAPITAL * BITCOIN_MONTHLY_DCA_PCT

    if mstr_combined_momentum > 0:
        print(f"MSTR combined momentum is POSITIVE ({mstr_combined_momentum*100:+.2f}%)")
        print(f"Allocate full position via score weighting")
    else:
        print(f"MSTR combined momentum is NEGATIVE ({mstr_combined_momentum*100:+.2f}%)")
        print(f"Strategy: DCA 0.1% of portfolio per month until 5% cap")
        print(f"  - Monthly DCA: ${monthly_dca_amount:,.0f}")
        print(f"  - Current MSTR price: ${mstr_price:,.2f}")
        print(f"  - Shares per month: {int(monthly_dca_amount / mstr_price)} (fractional: {monthly_dca_amount / mstr_price:.2f})")
        print(f"  - Months to reach 5% cap: {int(BITCOIN_CAP / monthly_dca_amount)}")
        print(f"  - Accelerate if momentum turns positive")

    # Weekly DCA Plan (12 weeks = 3 months)
    print(f"\n" + "=" * 60)
    print(f"WEEKLY DCA PLAN ({DCA_WEEKS} weeks)")
    print("=" * 60)
    print(f"\nTarget: Deploy ${TOTAL_CAPITAL:,.0f} over {DCA_WEEKS} weeks")
    print(f"Weekly investment: ${TOTAL_CAPITAL / DCA_WEEKS:,.0f} (rounded to ${ROUND_TO})\n")

    print(f"{'Ticker':<6} {'Target':>10} {'Weekly':>10} {'12-Week':>12}")
    print("-" * 40)

    weekly_allocations = {}
    for ticker in shares.index:
        target = shares.loc[ticker, "Allocation_USD"]
        if target > 0:
            weekly = round_to_nearest(target / DCA_WEEKS, ROUND_TO)
            weekly_allocations[ticker] = weekly
            actual_12wk = weekly * DCA_WEEKS
            print(f"{ticker:<6} ${target:>8,.0f} ${weekly:>8,.0f} ${actual_12wk:>10,.0f}")

    # MSTR special case
    if mstr_combined_momentum <= 0:
        mstr_weekly = round_to_nearest(monthly_dca_amount / 4, ROUND_TO)  # Monthly / 4 weeks
        if mstr_weekly < ROUND_TO:
            mstr_weekly = ROUND_TO  # Minimum $100/week if DCA active
        weekly_allocations["MSTR"] = mstr_weekly
        print(f"{'MSTR':<6} ${'(DCA)':>7} ${mstr_weekly:>8,.0f} ${mstr_weekly * DCA_WEEKS:>10,.0f}")

    weekly_total = sum(weekly_allocations.values())
    total_12wk = weekly_total * DCA_WEEKS

    print("-" * 40)
    print(f"{'TOTAL':<6} ${total_12wk:>8,.0f} ${weekly_total:>8,.0f} ${total_12wk:>10,.0f}")

    # Portfolio Risk Metrics
    metrics = calculate_portfolio_metrics(shares, returns, score, mom_3m, mom_6m, downside_vol)

    print(f"\n" + "=" * 60)
    print("PORTFOLIO RISK METRICS")
    print("=" * 60)
    print(f"Number of positions:        {metrics['num_positions']}")
    print(f"Max position weight:        {metrics['max_position_weight']*100:.1f}%")
    print(f"Top 3 concentration:        {metrics['top_3_concentration']*100:.1f}%")
    print(f"Weighted 3M momentum:       {metrics['weighted_mom_3m']*100:+.2f}%")
    print(f"Weighted 6M momentum:       {metrics['weighted_mom_6m']*100:+.2f}%")
    print(f"Weighted downside vol:      {metrics['weighted_downside_vol']*100:.2f}%")
    print(f"Weighted score:             {metrics['weighted_score']:.2f}")
    print(f"Portfolio volatility:       {metrics['portfolio_vol']*100:.2f}%")
    print(f"Portfolio downside vol:     {metrics['portfolio_downside_vol']*100:.2f}%")

    # Risk-adjusted metrics
    avg_momentum = (metrics['weighted_mom_3m'] + metrics['weighted_mom_6m']) / 2
    risk_reward_ratio = avg_momentum / metrics['portfolio_downside_vol'] if metrics['portfolio_downside_vol'] > 0 else 0
    print(f"\nRisk-Reward Ratio:          {risk_reward_ratio:.2f} (avg momentum / downside vol)")

    # Portfolio-weighted drawdown metrics
    active_tickers = [t for t in shares.index if shares.loc[t, "Allocation_USD"] > 0]
    if active_tickers:
        port_weights = shares.loc[active_tickers, "Weight_Pct"] / 100
        weighted_max_dd = sum(port_weights[t] * dd_metrics[t]["max_drawdown"] for t in active_tickers)
        weighted_max_dd_dur = sum(port_weights[t] * dd_metrics[t]["max_dd_duration_days"] for t in active_tickers)
        weighted_3m_roll_dd = sum(port_weights[t] * dd_metrics[t]["worst_rolling_3m_dd"] for t in active_tickers)
        weighted_current_dd = sum(port_weights[t] * dd_metrics[t]["current_drawdown"] for t in active_tickers)

        print(f"\n" + "-" * 40)
        print("PORTFOLIO DRAWDOWN RISK (Weighted)")
        print("-" * 40)
        print(f"Weighted max drawdown:      {weighted_max_dd*100:.1f}%")
        print(f"Weighted max DD duration:   {weighted_max_dd_dur:.0f} days")
        print(f"Weighted worst 3M roll DD:  {weighted_3m_roll_dd*100:.1f}%")
        print(f"Weighted current drawdown:  {weighted_current_dd*100:.1f}%")

        # Pain ratio: return per unit of drawdown pain
        pain_ratio = avg_momentum / abs(weighted_max_dd) if weighted_max_dd != 0 else 0
        print(f"\nPain Ratio:                 {pain_ratio:.2f} (avg momentum / max drawdown)")

    print(f"\n" + "-" * 40)
    print("NOTES")
    print("-" * 40)
    print("- After 12 weeks: Stop or rerun script with new capital")
    print("- MSTR: Continue weekly DCA until momentum turns positive")
    print("- Rerun this script quarterly to rebalance based on Sortino")
    print("- If any position momentum turns negative, pause that DCA")

    return shares, metrics


if __name__ == "__main__":
    result = main()
