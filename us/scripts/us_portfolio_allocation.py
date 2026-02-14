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
- Total deployable: configured via --capital
- Bitcoin target allocation managed via DCA rules
"""

import click
import numpy as np
import pandas as pd
import yfinance as yf

# Configuration
# Expanded universe: All NYSE/NASDAQ oil & gas + precious metals + ex-US value
# All securities compete on pure Sortino basis (except MSTR which has special DCA rules)
TICKERS = [
    # === Precious Metals ===
    "WPM",  # Wheaton Precious Metals - 50% silver streamer
    "PAAS",  # Pan American Silver - silver miner
    "FNV",  # Franco-Nevada - gold streamer + energy royalties
    "AEM",  # Agnico Eagle - lowest AISC (~$1,275), 87% safe jurisdictions
    "HL",  # Hecla Mining - silver-primary, negative cash costs via byproducts
    # === Energy: Integrated Oil Majors ===
    "XOM",  # Exxon Mobil
    "CVX",  # Chevron
    "CNQ",  # Canadian Natural Resources
    "SU",  # Suncor Energy
    "CVE",  # Cenovus Energy
    "XLE",  # Energy Select Sector SPDR
    # === Energy: Midstream (1099 C-corps only) ===
    "ENB",  # Enbridge
    "TRP",  # TC Energy
    "KMI",  # Kinder Morgan
    "WMB",  # Williams Companies
    "OKE",  # ONEOK
    # === Energy: Refineries ===
    "VLO",  # Valero Energy
    "PSX",  # Phillips 66
    "MPC",  # Marathon Petroleum
    "DINO",  # HF Sinclair
    # === Energy: E&P ===
    "COP",  # ConocoPhillips
    "DVN",  # Devon Energy
    "OXY",  # Occidental Petroleum
    # === Alpha Architect (Wes Gray) ===
    "QVAL",  # US Quantitative Value - concentrated deep value, EBIT/TEV
    "QMOM",  # US Quantitative Momentum - concentrated, monthly rebalance
    "IVAL",  # Intl Quantitative Value
    "IMOM",  # Intl Quantitative Momentum
    # === DFA (Dimensional) ===
    # DFIV dropped: 70%+ overlap with DXIV (same universe, less aggressive tilt)
    "DFSV",  # DFA US Small Cap Value - strongest value loading
    # DISV dropped: 57% overlap with AVDV (both intl small cap value)
    # DFEV dropped: 51-59% overlap with AVES (both EM value)
    "DXIV",  # DFA International Vector Equity - aggressive multi-factor
    # (kept over DFIV)
    # === Avantis ===
    "AVUV",  # Avantis US Small Cap Value - flagship
    "AVDV",  # Avantis International Small Cap Value (kept over DISV)
    "AVES",  # Avantis Emerging Markets Value (kept over DFEV/AVEM)
    # AVEM dropped: 70%+ overlap with AVES (AVES is value subset of AVEM)
    # === Regional Factor ETFs ===
    "EWJV",  # iShares MSCI Japan Value
    "DFJ",  # WisdomTree Japan SmallCap Dividend
    "DFE",  # WisdomTree Europe SmallCap Dividend (quality + momentum screened)
    "FLN",  # First Trust Latin America AlphaDEX (multi-factor)
    "EWZS",  # iShares MSCI Brazil Small-Cap
    # === Ex-US Emerging Markets ===
    "FRDM",  # Freedom 100 EM ETF - economic freedom-weighted
    # === Bitcoin proxy (special DCA rules) ===
    "MSTR",
    # === Software compounder (discretionary) ===
    "CSU.TO",  # Constellation Software (TSX)
]
TOTAL_CAPITAL = 40_000  # $60K total minus $20K in VGSH (treasury)
# Can be overridden via --capital flag
BITCOIN_DCA_TARGET_PCT = 0.05  # MSTR target allocation share of total portfolio
BITCOIN_MONTHLY_DCA_PCT = 0.001  # Monthly DCA share when momentum is negative
DCA_MONTHS = 3  # Reach target allocation in 3 months
DCA_WEEKS = 12  # 3 months = 12 weeks
ROUND_TO = 100  # Round allocations to nearest $100
SKIP_1M = 21  # ~1 month skip (avoid short-term reversal)
LOOKBACK_3M = 63  # ~3 months (20% weight, recency bias)
LOOKBACK_6M = 126  # ~6 months (40% weight)
LOOKBACK_12M = 252  # ~12 months (40% weight)
RISK_FREE_RATE = 0.05  # ~5% for Sortino calculation
MIN_ALLOCATION_PCT = 0.05  # Minimum allocation threshold for active positions

# Reporting groupings (no caps enforced — let momentum signal drive allocation)
PRECIOUS_METALS = ["WPM", "PAAS", "FNV", "AEM", "HL"]
ENERGY = [
    "XOM",
    "CVX",
    "XLE",
    "CNQ",
    "SU",
    "CVE",
    "ENB",
    "TRP",
    "KMI",
    "WMB",
    "OKE",
    "VLO",
    "PSX",
    "MPC",
    "DINO",
    "COP",
    "DVN",
    "OXY",
]
FACTOR_US = ["QVAL", "QMOM", "AVUV", "DFSV"]
FACTOR_INTL = ["IVAL", "IMOM", "DXIV", "AVDV", "DFE", "EWJV", "DFJ"]
FACTOR_EM = ["FRDM", "AVES", "FLN", "EWZS"]
BITCOIN = ["MSTR"]
SOFTWARE = ["CSU.TO"]


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
                    if close.iloc[i - 1] != 0:
                        div_yield = dividends.iloc[i] / close.iloc[i - 1]
                    else:
                        div_yield = 0
                    # Adjust for dividend reinvestment
                    cumulative_dividends = (1 + cumulative_dividends) * (
                        1 + div_yield
                    ) - 1
                    total_return_index.iloc[i] = close.iloc[i] * (
                        1 + cumulative_dividends
                    )

            dfs.append(total_return_index.rename(ticker))
    return pd.concat(dfs, axis=1).dropna()


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily returns."""
    return prices.pct_change(fill_method=None).dropna()


def calculate_momentum(
    prices: pd.DataFrame, lookback: int = 126, skip: int = 0
) -> pd.Series:
    """
    Calculate momentum (total return) for a given lookback period.
    With skip > 0, measures return from (lookback+skip) days ago to (skip) days ago.
    This implements the 1-month skip to avoid short-term reversal effect.
    """
    if len(prices) < lookback + skip:
        lookback = len(prices) - skip
    end_idx = -skip if skip > 0 else len(prices)
    start_idx = end_idx - lookback
    return (prices.iloc[end_idx - 1] / prices.iloc[start_idx]) - 1


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

        for i, (_date, is_dd) in enumerate(in_drawdown.items()):
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
            window_prices = price.iloc[i - window : i]
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


def calculate_momentum_quality(
    prices: pd.DataFrame, lookback: int = 252, skip: int = 0
) -> pd.Series:
    """
    Measure smoothness of momentum path (Wes Gray's "frog in the pan" concept).

    Returns R² of a linear fit to the return path over the lookback window.
    High R² = smooth, consistent trend (good). Low R² = jagged, spike-driven (bad).

    A stock that goes up 1% every week for 6 months (high R²) is more
    persistent than one that's flat for 5 months then spikes 30% (low R²).
    """
    quality = {}
    for col in prices.columns:
        price = prices[col].dropna()
        end_idx = len(price) - skip if skip > 0 else len(price)
        start_idx = max(0, end_idx - lookback)
        window = price.iloc[start_idx:end_idx]

        if len(window) < 20:
            quality[col] = 0.0
            continue

        # Fit linear regression to log prices (constant growth = perfect line)
        log_prices = np.log(window.values)
        x = np.arange(len(log_prices))
        coeffs = np.polyfit(x, log_prices, 1)
        fitted = np.polyval(coeffs, x)

        # R² = 1 - (SS_res / SS_tot)
        ss_res = np.sum((log_prices - fitted) ** 2)
        ss_tot = np.sum((log_prices - log_prices.mean()) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        quality[col] = max(r_squared, 0.0)

    return pd.Series(quality)


def calculate_vol_scaling(returns: pd.DataFrame, lookback: int = 21) -> pd.Series:
    """
    AQR-style volatility scaling: scale position sizes inversely to recent realized vol.

    Uses trailing 1-month (21 day) realized vol. Higher recent vol = lower weight.
    Returns a scaling factor where 1.0 = average vol, >1 = low vol (upweight),
    <1 = high vol (downweight).
    """
    recent_vol = {}
    for col in returns.columns:
        col_returns = returns[col].dropna()
        if len(col_returns) >= lookback:
            trailing = col_returns.iloc[-lookback:]
        else:
            trailing = col_returns
        recent_vol[col] = trailing.std() * np.sqrt(252)

    vol_series = pd.Series(recent_vol)
    median_vol = vol_series.median()

    # Inverse vol scaling: median_vol / actual_vol
    # Clamped to [0.5, 2.0] to avoid extreme adjustments
    scaling = (median_vol / vol_series).clip(0.5, 2.0)
    return scaling


def calculate_combined_score(prices: pd.DataFrame, returns: pd.DataFrame) -> tuple:
    """
    Calculate combined score with Gray improvements (adapted for buy-and-hold):

    1. Skip most recent month (avoid short-term reversal)
    2. Use 3M (20%) + 6M (40%) + 12M (40%) lookbacks — recency bias with persistence
    3. Weight by momentum quality (path smoothness / "frog in the pan")
    4. Normalize by downside volatility (Sortino-style)

    Vol scaling removed: designed for daily-rebalanced trading strategies,
    not buy-and-hold quarterly DCA. Quality + Sortino already risk-adjust
    without eliminating volatile asset classes.

    Score = (0.2*mom_3m + 0.4*mom_6m + 0.4*mom_12m) * quality / downside_vol
    """
    # 1. Momentum with 1-month skip
    mom_3m = calculate_momentum(prices, LOOKBACK_3M, skip=SKIP_1M)
    mom_6m = calculate_momentum(prices, LOOKBACK_6M, skip=SKIP_1M)
    mom_12m = calculate_momentum(prices, LOOKBACK_12M, skip=SKIP_1M)
    downside_vol = calculate_downside_volatility(returns)

    # 2. Weighted blend: 20% recency (3M) + 40% medium (6M) + 40% long (12M)
    combined_momentum = 0.2 * mom_3m + 0.4 * mom_6m + 0.4 * mom_12m

    # 3. Momentum quality (path smoothness)
    quality = calculate_momentum_quality(prices, lookback=LOOKBACK_12M, skip=SKIP_1M)

    # 4. Final score (no vol scaling — inappropriate for buy-and-hold)
    score = (combined_momentum * quality) / downside_vol

    return score, mom_3m, mom_6m, mom_12m, downside_vol, quality


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


def apply_constraints(
    weights: pd.Series,
    prices: pd.DataFrame,
    min_allocation_pct: float = MIN_ALLOCATION_PCT,
    max_allocation_pct: float = 1.0,
) -> pd.Series:
    """
    Apply position constraints only (no sector caps — let momentum signal drive):
    - Minimum allocation threshold - positions below get zeroed out
    - Maximum allocation threshold - positions above get limited
    - Renormalize to TOTAL_CAPITAL

    Approach: Iteratively remove/cap and redistribute until stable
    """
    allocation = weights * TOTAL_CAPITAL
    min_amount = TOTAL_CAPITAL * min_allocation_pct
    max_amount = TOTAL_CAPITAL * max_allocation_pct

    for _iteration in range(100):
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

        # Step 3: Renormalize to TOTAL_CAPITAL
        current_total = allocation.sum()
        if abs(current_total - TOTAL_CAPITAL) > 1:
            allocation = allocation * (TOTAL_CAPITAL / current_total)
            changed = True

        if not changed:
            break

    return allocation


def calculate_portfolio_metrics(
    shares: pd.DataFrame,
    returns: pd.DataFrame,
    score: pd.Series,
    mom_6m: pd.Series,
    mom_12m: pd.Series,
    downside_vol: pd.Series,
    quality: pd.Series,
) -> dict:
    """Calculate portfolio-level risk and return metrics."""
    active_tickers = [t for t in shares.index if shares.loc[t, "Allocation_USD"] > 0]

    if not active_tickers:
        return {"num_positions": 0}

    weights = shares.loc[active_tickers, "Weight_Pct"] / 100

    # Weighted average metrics
    weighted_mom_6m = sum(weights[t] * mom_6m[t] for t in active_tickers)
    weighted_mom_12m = sum(weights[t] * mom_12m[t] for t in active_tickers)
    weighted_downside_vol = sum(weights[t] * downside_vol[t] for t in active_tickers)
    weighted_score = sum(weights[t] * score[t] for t in active_tickers)
    weighted_quality = sum(weights[t] * quality[t] for t in active_tickers)

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
        "weighted_mom_6m": weighted_mom_6m,
        "weighted_mom_12m": weighted_mom_12m,
        "weighted_downside_vol": weighted_downside_vol,
        "weighted_score": weighted_score,
        "weighted_quality": weighted_quality,
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
    """Calculate dollar amounts with rounding (fractional shares supported)."""
    latest_prices = prices.iloc[-1]

    # Round allocations to nearest $1000 (or $100 for small amounts)
    rounded_allocations = {t: round_to_nearest(allocation[t]) for t in allocation.index}

    shares = pd.DataFrame(
        {
            "Ticker": allocation.index,
            "Allocation_USD": [rounded_allocations[t] for t in allocation.index],
            "Price": [latest_prices[t] for t in allocation.index],
            "Shares": [
                rounded_allocations[t] / latest_prices[t] for t in allocation.index
            ],
        }
    )
    shares["Weight_Pct"] = (
        shares["Allocation_USD"] / shares["Allocation_USD"].sum() * 100
    ).round(2)
    return shares.set_index("Ticker")


@click.command()
@click.option(
    "--min-allocation",
    "-m",
    type=float,
    default=0.05,
    help="Minimum allocation percentage. Positions below this get zeroed out.",
)
@click.option(
    "--max-allocation",
    "-M",
    type=float,
    default=1.0,
    help="Maximum allocation percentage. Positions above this get limited.",
)
@click.option(
    "--capital",
    "-c",
    type=int,
    default=40000,
    help="Total capital to allocate (default: 40000). $60K minus $20K VGSH treasury.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress detailed output, show only summary.",
)
def main(min_allocation: float, max_allocation: float, capital: int, quiet: bool):
    global TOTAL_CAPITAL
    TOTAL_CAPITAL = capital
    bitcoin_dca_target = int(capital * BITCOIN_DCA_TARGET_PCT)
    print("=" * 60)
    print("US PORTFOLIO ALLOCATION - MOMENTUM (AQR/GRAY IMPROVED)")
    print("=" * 80)
    print("\nImprovements over naive momentum:")
    print("  1. 1-month skip (avoid short-term reversal)")
    print("  2. 6M + 12M lookbacks (more persistent signal)")
    print("  3. Path smoothness filter (Wes Gray 'frog in the pan')")
    print("  4. Inverse vol scaling (AQR crash protection)")
    print("\nMin allocation: configured | Max allocation: configured")
    print(f"Fetching data for: {TICKERS}")

    # Fetch data
    prices = fetch_total_return_index(TICKERS)
    returns = calculate_returns(prices)

    print(f"Data range: {prices.index[0].date()} to {prices.index[-1].date()}")

    # Calculate combined score (quality-adjusted Sortino momentum)
    score, mom_3m, mom_6m, mom_12m, downside_vol, quality = calculate_combined_score(
        prices, returns
    )
    combined_momentum = 0.2 * mom_3m + 0.4 * mom_6m + 0.4 * mom_12m

    header = (
        f"{'Ticker':<6} {'3M Mom':>9} {'6M Mom':>9} {'12M Mom':>9} "
        f"{'Wt Mom':>9} {'Quality':>9} {'DnVol':>8} "
        f"{'Score':>8} {'':>6}"
    )
    print(f"\n{header}")
    print("-" * 90)
    for ticker in TICKERS:
        if ticker in prices.columns:
            status = "PASS" if combined_momentum[ticker] > 0 else "FAIL"
            print(
                f"  {ticker:<6} {mom_3m[ticker] * 100:>+8.1f}% "
                f"{mom_6m[ticker] * 100:>+8.1f}% "
                f"{mom_12m[ticker] * 100:>+8.1f}% "
                f"{combined_momentum[ticker] * 100:>+8.1f}% "
                f"{quality[ticker]:>8.3f} "
                f"{downside_vol[ticker] * 100:>7.1f}% "
                f"{score[ticker]:>7.2f} [{status}]"
            )

    # Calculate drawdown metrics (uses full 3-year history)
    dd_metrics = calculate_drawdown_metrics(prices)

    print("\n" + "=" * 60)
    print("DRAWDOWN ANALYSIS (3-Year History)")
    print("=" * 60)
    dd_header = (
        f"{'Ticker':<6} {'Max DD':>10} {'Max Dur':>10} {'Avg Dur':>10} "
        f"{'Curr DD':>10} {'3M Roll DD':>12}"
    )
    print(f"\n{dd_header}")
    print("-" * 70)
    for ticker in TICKERS:
        if ticker in prices.columns:
            m = dd_metrics[ticker]
            print(
                f"  {ticker:<6} {m['max_drawdown'] * 100:>9.1f}% "
                f"{m['max_dd_duration_days']:>8.0f}d "
                f"{m['avg_dd_duration_days']:>8.1f}d "
                f"{m['current_drawdown'] * 100:>9.1f}% "
                f"{m['worst_rolling_3m_dd'] * 100:>11.1f}%"
            )

    # Filter by combined momentum (must be positive)
    passing_tickers = apply_momentum_filter(combined_momentum)
    print(f"\nTickers passing momentum filter: {list(passing_tickers.index)}")

    # Filter score to only passing tickers
    score_filtered = score[passing_tickers.index]

    # Calculate weights proportional to score
    weights = calculate_sortino_weights(score_filtered)
    print("\nRaw Score Weights (before constraints):")
    for ticker in weights.index:
        print(f"  {ticker}: {weights[ticker] * 100:.1f}%")

    # Apply constraints
    allocation = apply_constraints(weights, prices, min_allocation, max_allocation)

    # Calculate shares
    shares = calculate_shares(allocation, prices)

    print("\n" + "=" * 60)
    print("FINAL ALLOCATION")
    print("=" * 60)
    print(f"\nTotal Capital: ${TOTAL_CAPITAL:,.0f}")
    print("No sector caps (momentum signal drives allocation)")
    print()
    print(shares.to_string())

    # Summary by category
    print("\n" + "-" * 40)
    print("ALLOCATION BY CATEGORY")
    print("-" * 40)

    # Calculate allocations by logical grouping (for reporting only)
    def group_alloc(group):
        active = [
            t
            for t in group
            if t in shares.index and shares.loc[t, "Allocation_USD"] > 0
        ]
        return shares.loc[active, "Allocation_USD"].sum()

    def group_active(group):
        return [
            t
            for t in group
            if t in shares.index and shares.loc[t, "Allocation_USD"] > 0
        ]

    categories = [
        ("Precious Metals", PRECIOUS_METALS),
        ("Energy", ENERGY),
        ("Factor: US", FACTOR_US),
        ("Factor: Intl", FACTOR_INTL),
        ("Factor: EM", FACTOR_EM),
        ("Bitcoin", BITCOIN),
    ]

    for label, group in categories:
        alloc = group_alloc(group)
        active = group_active(group)
        if active:
            print(
                f"{label} ({'+'.join(active)}): ${alloc:,.0f} "
                f"({alloc / TOTAL_CAPITAL * 100:.1f}%)"
            )

    # Category exposure summary
    print("\n" + "-" * 40)
    print("CATEGORY EXPOSURE")
    print("-" * 40)
    for label, group in categories:
        alloc = group_alloc(group)
        print(f"{label:<20s} ${alloc:>8,.0f} ({alloc / TOTAL_CAPITAL * 100:>5.1f}%)")
    print("Position constraints: min/max configured (no sector caps)")

    # MSTR DCA Plan
    print("\n" + "-" * 40)
    print("MSTR (BITCOIN) DCA PLAN")
    print("-" * 40)
    mstr_combined_momentum = combined_momentum.get("MSTR", 0.0)
    mstr_price = prices["MSTR"].iloc[-1]
    monthly_dca_amount = TOTAL_CAPITAL * BITCOIN_MONTHLY_DCA_PCT

    if mstr_combined_momentum > 0:
        print(
            f"MSTR combined momentum is POSITIVE ({mstr_combined_momentum * 100:+.2f}%)"
        )
        print("Allocate full position via score weighting")
    else:
        print(
            f"MSTR combined momentum is NEGATIVE ({mstr_combined_momentum * 100:+.2f}%)"
        )
        print(
            "Strategy: DCA a small share of portfolio per month until target allocation"
        )
        print(f"  - Monthly DCA: ${monthly_dca_amount:,.0f}")
        print(f"  - Current MSTR price: ${mstr_price:,.2f}")
        print(
            "  - Shares per month: "
            f"{int(monthly_dca_amount / mstr_price)} "
            f"(fractional: {monthly_dca_amount / mstr_price:.2f})"
        )
        print(
            "  - Months to reach target allocation: "
            f"{int(bitcoin_dca_target / monthly_dca_amount)}"
        )
        print("  - Accelerate if momentum turns positive")

    # Weekly DCA Plan (12 weeks = 3 months)
    print("\n" + "=" * 60)
    print(f"WEEKLY DCA PLAN ({DCA_WEEKS} weeks)")
    print("=" * 60)
    print(f"\nTarget: Deploy ${TOTAL_CAPITAL:,.0f} over {DCA_WEEKS} weeks")
    print(
        f"Weekly investment: ${TOTAL_CAPITAL / DCA_WEEKS:,.0f} "
        f"(rounded to ${ROUND_TO})\n"
    )

    print(f"{'Ticker':<6} {'Target':>10} {'Weekly':>10} {'12-Week':>12}")
    print("-" * 40)

    weekly_allocations = {}
    for ticker in shares.index:
        target = shares.loc[ticker, "Allocation_USD"]
        if target > 0:
            weekly = round_to_nearest(target / DCA_WEEKS, ROUND_TO)
            weekly_allocations[ticker] = weekly
            actual_12wk = weekly * DCA_WEEKS
            print(
                f"{ticker:<6} ${target:>8,.0f} ${weekly:>8,.0f} ${actual_12wk:>10,.0f}"
            )

    # MSTR special case
    if mstr_combined_momentum <= 0:
        mstr_weekly = round_to_nearest(
            monthly_dca_amount / 4, ROUND_TO
        )  # Monthly / 4 weeks
        if mstr_weekly < ROUND_TO:
            mstr_weekly = ROUND_TO  # Minimum $100/week if DCA active
        weekly_allocations["MSTR"] = mstr_weekly
        print(
            f"{'MSTR':<6} ${'(DCA)':>7} ${mstr_weekly:>8,.0f} "
            f"${mstr_weekly * DCA_WEEKS:>10,.0f}"
        )

    weekly_total = sum(weekly_allocations.values())
    total_12wk = weekly_total * DCA_WEEKS

    print("-" * 40)
    print(
        f"{'TOTAL':<6} ${total_12wk:>8,.0f} ${weekly_total:>8,.0f} "
        f"${total_12wk:>10,.0f}"
    )

    # Portfolio Risk Metrics
    metrics = calculate_portfolio_metrics(
        shares, returns, score, mom_6m, mom_12m, downside_vol, quality
    )
    # Also compute weighted 3M for display
    active_tickers_for_metrics = [
        t for t in shares.index if shares.loc[t, "Allocation_USD"] > 0
    ]
    w_pct = shares.loc[active_tickers_for_metrics, "Weight_Pct"] / 100
    weighted_mom_3m = sum(w_pct[t] * mom_3m[t] for t in active_tickers_for_metrics)

    print("\n" + "=" * 60)
    print("PORTFOLIO RISK METRICS")
    print("=" * 60)
    print(f"Number of positions:        {metrics['num_positions']}")
    print(f"Max position weight:        {metrics['max_position_weight'] * 100:.1f}%")
    print(f"Top 3 concentration:        {metrics['top_3_concentration'] * 100:.1f}%")
    print(
        f"Weighted 3M momentum:       {weighted_mom_3m * 100:+.2f}% "
        "(1M skip, 20% weight)"
    )
    print(
        f"Weighted 6M momentum:       {metrics['weighted_mom_6m'] * 100:+.2f}% "
        "(1M skip, 40% weight)"
    )
    print(
        f"Weighted 12M momentum:      {metrics['weighted_mom_12m'] * 100:+.2f}% "
        "(1M skip, 40% weight)"
    )
    print(
        f"Weighted path quality:      {metrics['weighted_quality']:.3f} "
        "(R², higher=smoother)"
    )
    print(f"Weighted downside vol:      {metrics['weighted_downside_vol'] * 100:.2f}%")
    print(f"Weighted score:             {metrics['weighted_score']:.2f}")
    print(f"Portfolio volatility:       {metrics['portfolio_vol'] * 100:.2f}%")
    print(f"Portfolio downside vol:     {metrics['portfolio_downside_vol'] * 100:.2f}%")

    # Risk-adjusted metrics
    avg_momentum = (
        0.2 * weighted_mom_3m
        + 0.4 * metrics["weighted_mom_6m"]
        + 0.4 * metrics["weighted_mom_12m"]
    )
    if metrics["portfolio_downside_vol"] > 0:
        risk_reward_ratio = avg_momentum / metrics["portfolio_downside_vol"]
    else:
        risk_reward_ratio = 0
    print(
        "\nRisk-Reward Ratio:          "
        f"{risk_reward_ratio:.2f} (avg momentum / downside vol)"
    )

    # Portfolio-weighted drawdown metrics
    active_tickers = [t for t in shares.index if shares.loc[t, "Allocation_USD"] > 0]
    if active_tickers:
        port_weights = shares.loc[active_tickers, "Weight_Pct"] / 100
        weighted_max_dd = sum(
            port_weights[t] * dd_metrics[t]["max_drawdown"] for t in active_tickers
        )
        weighted_max_dd_dur = sum(
            port_weights[t] * dd_metrics[t]["max_dd_duration_days"]
            for t in active_tickers
        )
        weighted_3m_roll_dd = sum(
            port_weights[t] * dd_metrics[t]["worst_rolling_3m_dd"]
            for t in active_tickers
        )
        weighted_current_dd = sum(
            port_weights[t] * dd_metrics[t]["current_drawdown"] for t in active_tickers
        )

        print("\n" + "-" * 40)
        print("PORTFOLIO DRAWDOWN RISK (Weighted)")
        print("-" * 40)
        print(f"Weighted max drawdown:      {weighted_max_dd * 100:.1f}%")
        print(f"Weighted max DD duration:   {weighted_max_dd_dur:.0f} days")
        print(f"Weighted worst 3M roll DD:  {weighted_3m_roll_dd * 100:.1f}%")
        print(f"Weighted current drawdown:  {weighted_current_dd * 100:.1f}%")

        # Pain ratio: return per unit of drawdown pain
        pain_ratio = avg_momentum / abs(weighted_max_dd) if weighted_max_dd != 0 else 0
        print(
            f"\nPain Ratio:                 {pain_ratio:.2f} "
            "(avg momentum / max drawdown)"
        )

    print("\n" + "-" * 40)
    print("NOTES")
    print("-" * 40)
    print("- After 12 weeks: Stop or rerun script with new capital")
    print("- MSTR: Continue weekly DCA until momentum turns positive")
    print("- Rerun this script quarterly to rebalance based on Sortino")
    print("- If any position momentum turns negative, pause that DCA")

    return shares, metrics


if __name__ == "__main__":
    result = main()
