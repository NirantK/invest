"""
Momentum Parameter Sweep — Walk-Forward Validated, Vectorized

Signals from AQR, Alpha Architect (Wes Gray), and academic research.
6 momentum flavors: arithmetic, log, EWMA-log, vol-normalized, acceleration, trimmed.
All hot paths use numpy. ProcessPoolExecutor with shared-memory initializer.

Usage:
    uv run python us/scripts/backtest.py
    uv run python us/scripts/backtest.py --top 20 --period 5y
    uv run python us/scripts/backtest.py --period max --max-dd-cap 0.50
"""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from itertools import product

import click
import numpy as np
from rich.console import Console
from rich.table import Table

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_utils import (
    fetch_all_numpy, fetch_all_earnings, build_earnings_momentum,
    fetch_all_mf_numpy, search_mf_schemes, get_all_mf_schemes,
)

console = Console()


class LogVariant(Enum):
    """Log-return momentum flavors — each dampens outliers differently."""
    NONE = "arith"      # Arithmetic returns (not log)
    BASIC = "log"       # ln(P_end/P_start)
    EWMA = "ewma"       # EWMA-weighted daily log returns (recency bias)
    VOLNORM = "vnorm"   # Log return / vol — t-statistic of trend
    ACCEL = "accel"     # 2nd half - 1st half log return (trend acceleration)
    TRIMMED = "trim"    # Sum of daily log returns after dropping top/bottom 5%


# ── Ticker universe ──────────────────────────────────────────────────────────

TICKERS = [
    # Precious Metals
    "WPM", "PAAS", "FNV", "AEM", "HL", "RGLD",
    # Energy: Integrated
    "XOM", "CVX", "CNQ", "SU", "CVE", "XLE",
    # Energy: Midstream (1099 only)
    "ENB", "TRP", "KMI", "WMB", "OKE",
    # Energy: Refineries
    "VLO", "PSX", "MPC", "DINO",
    # Energy: E&P
    "COP", "DVN", "OXY",
    # Industrial Metals / Uranium / Platinum
    "COPX", "URA", "PPLT",
    # LatAm / EM Fintech
    "ILF", "NU",
    # Factor ETFs
    "QVAL", "QMOM", "IVAL", "IMOM", "DFSV", "DXIV",
    "AVUV", "AVDV", "AVES", "IMTM",
    # Regional Factor
    "EWJV", "DFJ", "DFE", "EWZS", "FLN", "FRDM",
    # Gold ETFs / Sprott
    "GOAU", "SGDM", "SGDJ", "GBUG", "URNM", "URNJ", "COPP",
    # Bitcoin / Software
    "MSTR", "CSU.TO",
    # AI Infrastructure
    "BE", "CRWV", "INTC", "LITE", "CORZ", "IREN", "APLD", "SNDK",
    "CIFR", "EQT", "COHR", "SEI", "TSEM", "RIOT", "KRC", "HUT", "WYFI",
    # NYSE FANG+ (10 constituents)
    "META", "AAPL", "AMZN", "NFLX", "GOOGL", "MSFT", "NVDA",
    "SNOW", "TSLA", "AVGO",
    # Tech / Software (non-FANG+)
    "ADBE", "CRWD",
    # Nifty IT (US ADRs + NSE)
    "INFY", "WIT",
    "TCS.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS",
    "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS", "INFY.NS", "WIPRO.NS",
    # === Safe haven / Dual momentum risk-off assets ===
    "GLD",     # SPDR Gold Trust (physical gold ETF)
    "SLV",     # iShares Silver Trust (physical silver ETF)
    "SGOV",    # iShares 0-3 Month Treasury Bond ETF (cash proxy)
    "SHV",     # iShares Short Treasury Bond ETF (cash proxy, longer history)
    "BIL",     # SPDR Bloomberg 1-3 Month T-Bill ETF
    "IAU",     # iShares Gold Trust (alternative to GLD, lower ER)
]

# ── India MF universe (mfapi.in scheme codes) ───────────────────────────────
# Populated at runtime via --market india --mf-query "flexi cap,large cap,..."
# or fetched from mfapi.in search endpoint
INDIA_MF_QUERIES = [
    # ── Core equity categories ──
    "flexi cap growth direct",
    "large cap growth direct",
    "mid cap growth direct",
    "small cap growth direct",
    "large and mid cap growth direct",
    "multi cap growth direct",
    "focused fund direct growth",
    # ── Factor / smart-beta ──
    "alpha fund direct growth",
    "low volatility direct growth",
    "momentum index direct growth",
    "nifty alpha low volatility direct growth",
    "quality direct growth",
    "value fund direct growth",
    "dividend yield fund direct growth",
    "equal weight direct growth",
    "quant fund direct growth",
    # ── Index funds ──
    "nifty 50 index direct growth",
    "nifty next 50 index direct growth",
    "nifty midcap 150 index direct growth",
    "nifty smallcap 250 index direct growth",
    "sensex index direct growth",
    "nifty 500 index direct growth",
    # ── Sector / thematic ──
    "banking fund direct growth",
    "financial services fund direct growth",
    "pharma fund direct growth",
    "healthcare fund direct growth",
    "technology fund direct growth",
    "it fund direct growth",
    "infrastructure fund direct growth",
    "consumption fund direct growth",
    "manufacturing fund direct growth",
    "energy fund direct growth",
    "psu equity fund direct growth",
    "mnc fund direct growth",
    "auto fund direct growth",
    "realty fund direct growth",
    "defence fund direct growth",
    "innovation fund direct growth",
    "digital india fund direct growth",
    "business cycle fund direct growth",
    "transportation fund direct growth",
    # ── International ──
    "nasdaq 100 fund of fund direct growth",
    "s&p 500 index fund direct growth",
    "international fund direct growth",
    "us equity fund direct growth",
    "global fund direct growth",
    "china fund direct growth",
    "emerging market fund direct growth",
    # ── Commodities / precious metals ──
    "gold fund direct growth",
    "silver etf",
    "commodities fund direct growth",
    # ── Hybrid / multi-asset (safe havens for dual momentum) ──
    "liquid fund direct growth",
    "gilt fund direct growth",
    "overnight fund direct growth",
    "money market fund direct growth",
    "balanced advantage direct growth",
    "aggressive hybrid direct growth",
    "multi asset direct growth",
    "equity savings fund direct growth",
    # ── Tax saver ──
    "elss tax saver direct growth",
]

MIN_TICKERS_PER_FOLD = 15

# Safe-haven tickers for dual momentum risk-off allocation
SAFE_HAVENS = {"GLD", "IAU", "SLV", "SGOV", "SHV", "BIL"}

# Rebalance frequencies in trading days
REBAL_FREQS = {
    "1w": 5,
    "2w": 10,
    "1m": 21,
    "2m": 42,
    "1q": 63,
}

# ── Transaction cost model (IBKR C-Corp, $50K account) ──────────────────────
# Source: interactivebrokers.com/en/pricing/commissions-stocks.php (Mar 2026)
PORTFOLIO_VALUE = 50_000.0           # Starting capital for cost scaling
IBKR_COMMISSION_PER_SHARE = 0.0035   # Tiered pricing, ≤300K shares/mo
IBKR_MIN_COMMISSION = 0.35           # Minimum per order
AVG_SHARE_PRICE = 75.0               # Avg price across our ETF universe
HALF_SPREAD_BPS = 5.0                # Half bid-ask spread in bps (0.05%)
                                     # Conservative: commodity ETFs avg 4-12 bps full spread
CCORP_TAX_RATE = 0.21                # Flat 21% federal on all realized gains
SEC_FINRA_FEE_PER_SHARE = 0.0002     # SEC + FINRA + CAT fees (negligible but included)


# ── Vectorized signal functions ──────────────────────────────────────────────


def momentum_arithmetic(prices: np.ndarray, lookback: int, skip: int) -> np.ndarray:
    """Standard arithmetic momentum: P[end]/P[start] - 1."""
    n = prices.shape[0]
    if n < lookback + skip:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    with np.errstate(divide="ignore", invalid="ignore"):
        mom = prices[end - 1] / prices[start] - 1
    return np.nan_to_num(mom, nan=0.0)


def momentum_log(prices: np.ndarray, lookback: int, skip: int) -> np.ndarray:
    """Log-return momentum: ln(P[end]/P[start]). Dampens outliers."""
    n = prices.shape[0]
    if n < lookback + skip:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    with np.errstate(divide="ignore", invalid="ignore"):
        mom = np.log(prices[end - 1] / prices[start])
    return np.nan_to_num(mom, nan=0.0)


def momentum_log_ewma(prices: np.ndarray, lookback: int, skip: int, halflife: int = 63) -> np.ndarray:
    """EWMA-weighted log returns: recent days weighted more. halflife in trading days."""
    n = prices.shape[0]
    if n < lookback + skip + 1:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    segment = prices[start:end]
    with np.errstate(divide="ignore", invalid="ignore"):
        daily_log = np.diff(np.log(segment), axis=0)
    daily_log = np.nan_to_num(daily_log, nan=0.0, posinf=0.0, neginf=0.0)
    # Exponential weights: most recent day gets highest weight
    decay = np.log(2) / halflife
    w = np.exp(decay * np.arange(daily_log.shape[0], dtype=np.float64))
    w /= w.sum()
    return (w[:, np.newaxis] * daily_log).sum(axis=0)


def momentum_log_volnorm(prices: np.ndarray, lookback: int, skip: int) -> np.ndarray:
    """Vol-normalized log momentum: ln(P_end/P_start) / std(daily log returns).

    Essentially a t-statistic of the trend. High value = strong, consistent trend.
    """
    n = prices.shape[0]
    if n < lookback + skip + 1:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    with np.errstate(divide="ignore", invalid="ignore"):
        log_ret = np.log(prices[end - 1] / prices[start])
        daily_log = np.diff(np.log(prices[start:end]), axis=0)
    daily_log = np.nan_to_num(daily_log, nan=0.0, posinf=0.0, neginf=0.0)
    vol = np.std(daily_log, axis=0)
    vol = np.where(vol > 0, vol, 0.0001)
    result = log_ret / (vol * np.sqrt(lookback))
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def momentum_log_accel(prices: np.ndarray, lookback: int, skip: int) -> np.ndarray:
    """Log return acceleration: 2nd half momentum minus 1st half.

    Positive = trend accelerating, negative = decelerating.
    Added to base log momentum as a boost/penalty.
    """
    n = prices.shape[0]
    if n < lookback + skip:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    mid = start + lookback // 2
    with np.errstate(divide="ignore", invalid="ignore"):
        first_half = np.log(prices[mid] / prices[start])
        second_half = np.log(prices[end - 1] / prices[mid])
        base = np.log(prices[end - 1] / prices[start])
    accel = second_half - first_half  # positive = accelerating
    # Blend: base momentum + acceleration bonus (scaled down)
    result = base + 0.5 * accel
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def momentum_log_trimmed(prices: np.ndarray, lookback: int, skip: int, trim_pct: float = 0.05) -> np.ndarray:
    """Trimmed log returns: drop top/bottom 5% of daily returns, then sum.

    Robust against gap days (earnings jumps, flash crashes) common in miners/commodities.
    """
    n = prices.shape[0]
    if n < lookback + skip + 1:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    segment = prices[start:end]
    with np.errstate(divide="ignore", invalid="ignore"):
        daily_log = np.diff(np.log(segment), axis=0)
    daily_log = np.nan_to_num(daily_log, nan=0.0, posinf=0.0, neginf=0.0)
    n_days = daily_log.shape[0]
    n_trim = max(1, int(n_days * trim_pct))
    # Sort each column, trim top and bottom
    sorted_rets = np.sort(daily_log, axis=0)
    trimmed = sorted_rets[n_trim:-n_trim]
    return trimmed.sum(axis=0)


def downside_vol(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """Annualized downside vol."""
    w = min(window, prices.shape[0] - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(prices[-w - 1:], axis=0) / prices[-w - 1:-1]
    rets = np.nan_to_num(rets, nan=0.0)
    neg = np.minimum(rets, 0.0)
    dv = np.sqrt(252) * np.nanstd(neg, axis=0)
    return np.where(dv > 0, dv, 0.0001)


def total_vol(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """Annualized total volatility."""
    w = min(window, prices.shape[0] - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(prices[-w - 1:], axis=0) / prices[-w - 1:-1]
    rets = np.nan_to_num(rets, nan=0.0)
    tv = np.sqrt(252) * np.nanstd(rets, axis=0)
    return np.where(tv > 0, tv, 0.0001)


def trend_quality(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """R² of log-price trend — fully vectorized."""
    n = prices.shape[0]
    w = min(window, n)
    segment = prices[-w:]
    with np.errstate(divide="ignore", invalid="ignore"):
        log_p = np.log(segment)
    log_p = np.nan_to_num(log_p, nan=0.0, posinf=0.0, neginf=0.0)

    x = np.arange(w, dtype=np.float64)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    if x_var == 0:
        return np.zeros(prices.shape[1])

    y_mean = log_p.mean(axis=0)
    numerator = ((x - x_mean)[:, np.newaxis] * (log_p - y_mean)).sum(axis=0)
    slope = numerator / x_var
    fitted = slope * (x[:, np.newaxis] - x_mean) + y_mean
    ss_res = ((log_p - fitted) ** 2).sum(axis=0)
    ss_tot = ((log_p - y_mean) ** 2).sum(axis=0)

    with np.errstate(divide="ignore", invalid="ignore"):
        quality = 1.0 - ss_res / ss_tot
    return np.maximum(np.where(ss_tot > 0, quality, 0.0), 0.0)


def fip_score(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """Frog-in-the-Pan: fraction of positive daily returns."""
    w = min(window, prices.shape[0] - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(prices[-(w + 1):], axis=0) / prices[-(w + 1):-1]
    rets = np.nan_to_num(rets, nan=0.0)
    return np.mean(rets > 0, axis=0)


def consistency_filter(prices: np.ndarray, skip: int = 21) -> np.ndarray:
    """Alpha Architect 8-of-12: count positive months in t-2..t-12.

    Returns (n_tickers,) with 1.0 if >=8 positive months, 0.0 otherwise.
    """
    n = prices.shape[0]
    if n < 252 + skip:
        return np.ones(prices.shape[1])  # pass all if insufficient data

    # Sample monthly returns (every ~21 trading days) for months t-2..t-12
    end = n - skip
    month_returns = []
    for m in range(1, 12):  # 11 months
        m_end = end - m * 21
        m_start = m_end - 21
        if m_start < 0:
            break
        with np.errstate(divide="ignore", invalid="ignore"):
            mr = prices[m_end] / prices[m_start] - 1
        month_returns.append(np.nan_to_num(mr, nan=0.0))

    if len(month_returns) < 8:
        return np.ones(prices.shape[1])

    month_arr = np.array(month_returns)  # (n_months, n_tickers)
    pos_count = np.sum(month_arr > 0, axis=0)
    return np.where(pos_count >= 8, 1.0, 0.0)


def high_52wk(prices: np.ndarray) -> np.ndarray:
    """52-week high distance: price / max(past 252 days). Closer to 1.0 = stronger."""
    n = prices.shape[0]
    w = min(252, n)
    peak = np.nanmax(prices[-w:], axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = prices[-1] / peak
    return np.nan_to_num(ratio, nan=0.0)


def crash_protection_signal_at(mkt_prices: np.ndarray, day: int) -> float:
    """Daniel-Moskowitz crash check at a specific day index. Returns 0.5 or 1.0."""
    if day < 504:
        return 1.0
    mkt_24m = mkt_prices[day] / mkt_prices[day - 504] - 1 if mkt_prices[day - 504] > 0 else 0
    mkt_1m = mkt_prices[day] / mkt_prices[day - 21] - 1 if day >= 21 and mkt_prices[day - 21] > 0 else 0
    return 0.5 if (mkt_24m < 0 and mkt_1m > 0.05) else 1.0


# ── Precomputed signal cache ─────────────────────────────────────────────────
# Compute all expensive signals ONCE at each possible rebalance date.
# Then score_universe is pure arithmetic on cached arrays.


@dataclass
class PrecomputedSignals:
    """All signal values precomputed at every possible rebalance date."""
    # Keyed by day index → (n_tickers,) arrays
    # Momentum: keyed by (lookback, skip, log_variant) → {day: array}
    # log_variant: False=arithmetic, 0=basic log, 1=ewma, 2=volnorm, 3=accel, 4=trimmed
    momentum_cache: dict  # {(lb, skip, variant): {day: np.ndarray}}
    # Quality signals: {day: array}
    smoothness: dict      # {day: np.ndarray}  sqrt(R² * FIP)
    dn_vol: dict          # {day: np.ndarray}  downside vol
    tv: dict              # {day: np.ndarray}  total vol (for vol-scaling)
    consistency: dict     # {day: np.ndarray}  8-of-12 filter (0 or 1)
    abs_mom_12m: dict     # {day: np.ndarray}  12m arithmetic momentum (for dual)
    crash_mult: dict      # {day: float}       crash protection multiplier


def precompute_signals(
    prices: np.ndarray,
    rebal_days: list[int],
    lookbacks: list[int],
    skips: list[int],
) -> PrecomputedSignals:
    """Precompute all signals at each rebalance date. Called once per worker."""
    n_tickers = prices.shape[1]

    # Market proxy for crash protection (precompute once)
    with np.errstate(divide="ignore", invalid="ignore"):
        mkt = np.nanmean(prices, axis=1)

    # Unique (lookback, skip, LogVariant) combos
    mom_keys = set()
    for lb in lookbacks:
        for skip in skips:
            for lv in LogVariant:
                mom_keys.add((lb, skip, lv))

    momentum_cache = {k: {} for k in mom_keys}
    smoothness = {}
    dn_vol_cache = {}
    tv_cache = {}
    consistency_cache = {}
    abs_mom_cache = {}
    crash_cache = {}

    momentum_fn_by_variant = {
        LogVariant.NONE: momentum_arithmetic,
        LogVariant.BASIC: momentum_log,
        LogVariant.EWMA: momentum_log_ewma,
        LogVariant.VOLNORM: momentum_log_volnorm,
        LogVariant.ACCEL: momentum_log_accel,
        LogVariant.TRIMMED: momentum_log_trimmed,
    }

    for day in rebal_days:
        pw = prices[:day + 1]
        n = pw.shape[0]

        # Momentum for all (lookback, skip, LogVariant) combos
        for lb, skip, variant in mom_keys:
            if n < lb + skip:
                momentum_cache[(lb, skip, variant)][day] = np.zeros(n_tickers)
            else:
                momentum_cache[(lb, skip, variant)][day] = momentum_fn_by_variant[variant](pw, lb, skip)

        # Smoothness: sqrt(R² * FIP)
        qual = trend_quality(pw, min(252, n))
        fip = fip_score(pw, min(252, n - 1))
        smoothness[day] = np.sqrt(qual * fip)

        # Volatility
        dn_vol_cache[day] = downside_vol(pw, min(252, n))
        tv_cache[day] = total_vol(pw, min(126, n))

        # Consistency (8-of-12)
        consistency_cache[day] = consistency_filter(pw, 21)

        # Absolute 12m momentum (for dual momentum filter)
        abs_mom_cache[day] = momentum_arithmetic(pw, min(252, n), 0)

        # Crash protection
        crash_cache[day] = crash_protection_signal_at(mkt, day)

    return PrecomputedSignals(
        momentum_cache=momentum_cache,
        smoothness=smoothness,
        dn_vol=dn_vol_cache,
        tv=tv_cache,
        consistency=consistency_cache,
        abs_mom_12m=abs_mom_cache,
        crash_mult=crash_cache,
    )


# ── Scoring params ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoringParams:
    lb_short: int
    lb_mid: int
    lb_long: int
    w_short: float
    w_mid: float
    w_long: float
    skip: int
    # Signal modifiers
    use_sortino: bool       # Divide by downside vol
    use_smoothness: bool    # R² × FIP quality
    use_earnings: bool      # Earnings momentum boost
    log_variant: LogVariant  # Which momentum return type to use
    use_consistency: bool   # 8-of-12 positive months filter
    use_abs_momentum: bool  # Dual momentum: require positive 12m return
    use_vol_scaling: bool   # Inverse-vol position weighting
    use_crash_prot: bool    # Daniel-Moskowitz crash throttle
    # Portfolio
    max_positions: int
    rebal_freq: int         # Trading days between rebalances

    def label(self) -> str:
        parts = [
            f"lb={self.lb_short}/{self.lb_mid}/{self.lb_long}",
            f"w={self.w_short:.1f}/{self.w_mid:.1f}/{self.w_long:.1f}",
            f"sk={self.skip}",
        ]
        flags = []
        if self.use_sortino: flags.append("sort")
        if self.use_smoothness: flags.append("smth")
        if self.use_earnings: flags.append("earn")
        if self.log_variant != LogVariant.NONE:
            flags.append(self.log_variant.value)
        if self.use_consistency: flags.append("8/12")
        if self.use_abs_momentum: flags.append("dual")
        if self.use_vol_scaling: flags.append("vscl")
        if self.use_crash_prot: flags.append("crsh")
        if flags:
            parts.append("+".join(flags))
        parts.append(f"n={self.max_positions}")
        parts.append(f"r={self.rebal_freq}d")
        return " ".join(parts)


def score_from_cache(
    day: int,
    params: ScoringParams,
    cache: PrecomputedSignals,
    earnings_row: np.ndarray | None = None,
) -> np.ndarray:
    """Score all tickers using precomputed signals. Pure array arithmetic."""
    variant = params.log_variant
    mc = cache.momentum_cache

    mom_s = mc.get((params.lb_short, params.skip, variant), {}).get(day)
    mom_m = mc.get((params.lb_mid, params.skip, variant), {}).get(day)
    mom_l = mc.get((params.lb_long, params.skip, variant), {}).get(day)

    if mom_s is None or mom_m is None or mom_l is None:
        return np.full(len(cache.smoothness.get(day, np.array([]))), -1.0)

    wt_mom = params.w_short * mom_s + params.w_mid * mom_m + params.w_long * mom_l
    scores = wt_mom.copy()

    if params.use_smoothness:
        scores *= cache.smoothness[day]

    if params.use_sortino:
        scores /= cache.dn_vol[day]

    if params.use_earnings and earnings_row is not None:
        earn = np.nan_to_num(earnings_row, nan=0.0)
        scores *= (1 + np.clip(earn, -0.5, 2.0))

    if params.use_consistency:
        scores *= cache.consistency[day]

    if params.use_abs_momentum:
        scores = np.where(cache.abs_mom_12m[day] > 0, scores, -1.0)

    if params.use_crash_prot:
        scores *= cache.crash_mult[day]

    return np.where(wt_mom > 0, scores, -1.0)


# ── Vectorized OOS period ────────────────────────────────────────────────────


def _compute_rebalance_cost(
    old_weights: np.ndarray,
    new_weights: np.ndarray,
    cost_basis: np.ndarray,
    current_prices_ratio: np.ndarray,
) -> float:
    """Compute total cost of rebalancing as a fraction of portfolio value.

    All math is in weight-space (fractions), so it's scale-invariant.
    Commission is computed in real dollars using PORTFOLIO_VALUE, then converted back to fraction.
    """
    turnover = np.abs(new_weights - old_weights)  # per-ticker weight change
    total_turnover = turnover.sum()  # two-sided turnover (buy + sell)

    if total_turnover < 0.001:
        return 0.0

    # 1. Commission: IBKR tiered — $0.0035/share, min $0.35/order
    #    Scale to real dollars using PORTFOLIO_VALUE for accurate commission calc
    traded_dollars_real = total_turnover * PORTFOLIO_VALUE
    shares_traded = traded_dollars_real / AVG_SHARE_PRICE
    n_orders = int(np.sum(turnover > 0.001))
    per_share_cost = IBKR_COMMISSION_PER_SHARE + SEC_FINRA_FEE_PER_SHARE
    commission_real = max(shares_traded * per_share_cost, n_orders * IBKR_MIN_COMMISSION)
    commission_frac = commission_real / PORTFOLIO_VALUE

    # 2. Bid-ask slippage: pay half-spread on each dollar traded (already a fraction)
    slippage_frac = total_turnover * (HALF_SPREAD_BPS / 10_000)

    # 3. C-Corp tax on realized gains (sells only)
    sells = np.maximum(old_weights - new_weights, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        gain_pct = np.where(cost_basis > 0, current_prices_ratio / cost_basis - 1, 0.0)
    gain_pct = np.maximum(gain_pct, 0.0)  # only tax gains, not losses
    # Tax = 21% of (sell_weight × gain_pct) for each ticker
    tax_frac = (sells * gain_pct).sum() * CCORP_TAX_RATE

    return commission_frac + slippage_frac + tax_frac


def run_oos_period(
    prices: np.ndarray,
    params: ScoringParams,
    oos_start: int,
    oos_end: int,
    cache: PrecomputedSignals | None = None,
    earn_mom: np.ndarray | None = None,
    ticker_names: list[str] | None = None,
) -> tuple[float, float, float, np.ndarray]:
    """Run one OOS period. Returns (return, max_dd, avg_pos, daily_values)."""
    n_tickers = prices.shape[1]
    period_len = oos_end - oos_start
    portfolio_value = np.ones(period_len + 1)
    position_counts = []

    # Track weights and cost basis for tax + turnover cost calculation
    prev_weights = np.zeros(n_tickers)
    cost_basis = np.ones(n_tickers)  # normalized price at which position was entered

    # Pre-identify safe-haven ticker indices for dual momentum risk-off
    safe_indices = []
    if ticker_names and params.use_abs_momentum:
        safe_indices = [i for i, t in enumerate(ticker_names) if t in SAFE_HAVENS]

    rebal_offsets = list(range(0, period_len, params.rebal_freq))

    for idx, rb_offset in enumerate(rebal_offsets):
        next_offset = rebal_offsets[idx + 1] if idx + 1 < len(rebal_offsets) else period_len

        rb_abs = oos_start + rb_offset
        earn_row = earn_mom[rb_abs] if earn_mom is not None else None
        scores = score_from_cache(rb_abs, params, cache, earn_row)
        valid = np.where(scores > 0)[0]

        # Exclude safe havens from the risky scoring (they're risk-off destinations)
        if safe_indices:
            valid = np.array([v for v in valid if v not in safe_indices])

        if len(valid) == 0:
            # Dual momentum risk-off: all risky assets failed → allocate to best safe haven
            if safe_indices and params.use_abs_momentum:
                sh_mom = cache.abs_mom_12m.get(rb_abs, np.zeros(n_tickers))
                best_sh = max(safe_indices, key=lambda i: sh_mom[i])
                weights = np.zeros(n_tickers)
                weights[best_sh] = 1.0
                position_counts.append(1)
            else:
                portfolio_value[rb_offset + 1:next_offset + 1] = portfolio_value[rb_offset]
                position_counts.append(0)
                prev_weights = np.zeros(n_tickers)
                continue
        else:
            top_n = min(params.max_positions, len(valid))
            top_idx = valid[np.argsort(scores[valid])[-top_n:]]

            if params.use_abs_momentum and safe_indices and top_n < params.max_positions:
                n_risk = top_n
                sh_mom = cache.abs_mom_12m.get(rb_abs, np.zeros(n_tickers))
                best_sh = max(safe_indices, key=lambda i: sh_mom[i])

                weights = np.zeros(n_tickers)
                risk_share = n_risk / params.max_positions
                if params.use_vol_scaling and cache is not None:
                    tv = cache.tv[rb_abs]
                    inv_vol = 1.0 / tv[top_idx]
                    weights[top_idx] = risk_share * inv_vol / inv_vol.sum()
                else:
                    weights[top_idx] = risk_share / n_risk
                weights[best_sh] += (1.0 - risk_share)
            elif params.use_vol_scaling and cache is not None:
                tv = cache.tv[rb_abs]
                inv_vol = 1.0 / tv[top_idx]
                weights = np.zeros(n_tickers)
                weights[top_idx] = inv_vol / inv_vol.sum()
            else:
                weights = np.zeros(n_tickers)
                weights[top_idx] = 1.0 / top_n

            position_counts.append(top_n)

        # Compute rebalance costs (commission + slippage + tax on gains)
        current_price_ratio = prices[rb_abs] / prices[oos_start] if prices[oos_start].sum() > 0 else np.ones(n_tickers)
        rebal_cost_frac = _compute_rebalance_cost(
            prev_weights, weights, cost_basis, current_price_ratio,
        )

        # Update cost basis: for newly bought positions, mark entry price
        new_positions = (weights > 0.001) & (prev_weights < 0.001)
        cost_basis[new_positions] = current_price_ratio[new_positions]

        # Apply rebalance cost as immediate drag
        portfolio_value[rb_offset] *= (1.0 - rebal_cost_frac)
        prev_weights = weights.copy()

        # Vectorized daily returns
        day_start = oos_start + rb_offset
        day_end = min(oos_start + next_offset, prices.shape[0] - 1)
        n_hold = day_end - day_start
        if n_hold <= 0:
            continue

        with np.errstate(divide="ignore", invalid="ignore"):
            daily_rets = prices[day_start + 1:day_end + 1] / prices[day_start:day_end] - 1
        daily_rets = np.nan_to_num(daily_rets, nan=0.0)
        port_rets = daily_rets @ weights
        cum = np.cumprod(1 + port_rets)
        actual = min(n_hold, next_offset - rb_offset)
        portfolio_value[rb_offset + 1:rb_offset + 1 + actual] = (
            portfolio_value[rb_offset] * cum[:actual]
        )

    oos_return = portfolio_value[-1] / portfolio_value[0] - 1
    running_max = np.maximum.accumulate(portfolio_value)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdowns = (portfolio_value - running_max) / running_max
    max_dd = np.nan_to_num(drawdowns, nan=0.0).min()
    avg_pos = np.mean(position_counts) if position_counts else 0

    return oos_return, max_dd, avg_pos, portfolio_value


# ── Walk-forward result ──────────────────────────────────────────────────────


@dataclass
class WalkForwardResult:
    oos_total_return: float
    oos_annualized: float
    oos_max_dd: float
    oos_sortino: float
    oos_calmar: float
    oos_romad: float
    oos_win_rate: float
    n_folds: int
    avg_positions: float
    consistency: float
    params: ScoringParams
    fold_returns: list[float] = field(default_factory=list)

    def label(self) -> str:
        return self.params.label()


# ── Walk-forward engine ──────────────────────────────────────────────────────

_G_PRICES: np.ndarray | None = None
_G_DATES: np.ndarray | None = None
_G_EARN_MOM: np.ndarray | None = None
_G_CACHE: PrecomputedSignals | None = None
_G_TICKERS: list[str] | None = None


def _init_worker(
    prices: np.ndarray, dates: np.ndarray, earn_mom: np.ndarray | None,
    rebal_days: list[int], lookbacks: list[int], skips: list[int],
    ticker_names: list[str],
):
    global _G_PRICES, _G_DATES, _G_EARN_MOM, _G_CACHE, _G_TICKERS
    _G_PRICES = prices
    _G_DATES = dates
    _G_EARN_MOM = earn_mom
    _G_TICKERS = ticker_names
    _G_CACHE = precompute_signals(prices, rebal_days, lookbacks, skips)


def _worker_run(args: tuple) -> WalkForwardResult:
    params, folds = args
    return walk_forward_backtest(
        _G_PRICES, params, folds=folds, earn_mom=_G_EARN_MOM,
        cache=_G_CACHE, ticker_names=_G_TICKERS,
    )


def build_folds(
    prices: np.ndarray,
    min_train_days: int,
    oos_window_days: int,
    min_tickers: int = MIN_TICKERS_PER_FOLD,
) -> list[tuple[int, int]]:
    n_days = prices.shape[0]
    folds = []
    train_end = min_train_days
    while train_end + 21 < n_days:
        oos_start = train_end
        oos_end = min(train_end + oos_window_days, n_days - 1)
        if oos_end - oos_start < 21:
            break
        window = prices[:oos_start]
        n_valid = np.sum(~np.all(np.isnan(window), axis=0))
        if n_valid >= min_tickers:
            folds.append((oos_start, oos_end))
        train_end = oos_end
    return folds


def walk_forward_backtest(
    prices: np.ndarray,
    params: ScoringParams,
    folds: list[tuple[int, int]] | None = None,
    earn_mom: np.ndarray | None = None,
    cache: PrecomputedSignals | None = None,
    ticker_names: list[str] | None = None,
    min_train_days: int = 252,
    oos_window_days: int = 126,
) -> WalkForwardResult:
    if folds is None:
        folds = build_folds(prices, min_train_days, oos_window_days)
    if not folds:
        return WalkForwardResult(0, 0, -1, 0, 0, 0, 0, 0, 0, 1.0, params)

    fold_returns = []
    all_daily_values = []
    total_positions = []

    em = earn_mom if params.use_earnings else None
    for oos_start, oos_end in folds:
        ret, dd, avg_pos, daily_vals = run_oos_period(
            prices, params, oos_start, oos_end, cache=cache, earn_mom=em,
            ticker_names=ticker_names,
        )
        fold_returns.append(ret)
        total_positions.append(avg_pos)
        all_daily_values.append(daily_vals)

    oos_total = float(np.prod([1 + r for r in fold_returns]) - 1)

    # Chain daily values
    scaled_segments = []
    cumulative = 1.0
    for dv in all_daily_values:
        scale = cumulative / dv[0] if dv[0] != 0 else cumulative
        scaled_segments.append(dv * scale)
        cumulative = scaled_segments[-1][-1]
    scaled = np.concatenate(scaled_segments)

    running_max = np.maximum.accumulate(scaled)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_series = (scaled - running_max) / running_max
    overall_dd = np.nan_to_num(dd_series, nan=0.0).min()

    total_oos_days = sum(e - s for s, e in folds)
    n_years = total_oos_days / 252
    if n_years > 0 and (1 + oos_total) > 0:
        ann_return = (1 + oos_total) ** (1 / n_years) - 1
    else:
        ann_return = -1.0 if oos_total < 0 else 0.0

    fold_arr = np.array(fold_returns)
    consist = float(fold_arr.std())
    win_rate = float(np.mean(fold_arr > 0))

    daily_rets = np.diff(scaled) / scaled[:-1]
    daily_rets = daily_rets[np.isfinite(daily_rets)]
    neg_rets = daily_rets[daily_rets < 0]
    dn_vol = float(neg_rets.std() * np.sqrt(252)) if len(neg_rets) > 0 else 0.0001
    sortino = ann_return / dn_vol if dn_vol > 0 else 0
    calmar = ann_return / abs(overall_dd) if overall_dd != 0 else 0
    romad = min(oos_total / abs(overall_dd), 1e6) if overall_dd != 0 else 0

    return WalkForwardResult(
        oos_total_return=oos_total, oos_annualized=ann_return,
        oos_max_dd=overall_dd, oos_sortino=sortino, oos_calmar=calmar,
        oos_romad=romad, oos_win_rate=win_rate, n_folds=len(folds),
        avg_positions=float(np.mean(total_positions)), consistency=consist,
        params=params, fold_returns=fold_returns,
    )


# ── Parameter grid ───────────────────────────────────────────────────────────


def build_param_grid() -> list[ScoringParams]:
    """Build grid with all 10 AQR/AA signals + 5 rebal frequencies.

    Uses smart grouping to keep grid manageable (~10K combos).
    """
    configs = []

    # Base: 3 lookbacks × 4 weight schemes × 2 skips = 24 base combos
    lookbacks = [
        (21, 63, 252),    # 1M/3M/12M
        (42, 126, 252),   # 2M/6M/12M
        (63, 126, 252),   # 3M/6M/12M
    ]
    weight_schemes = [
        (0.4, 0.4, 0.2),   # Recency bias (top performer)
        (0.5, 0.3, 0.2),   # Strong recency
        (0.1, 0.3, 0.6),   # Trend-following
        (0.33, 0.34, 0.33), # Equal
    ]
    skips = [0, 21]
    positions = [2, 3, 5, 8, 10, 15, 30]
    rebal_freqs = [5, 10, 21, 42, 63]

    # Signal profiles: predefined combos to avoid full cartesian explosion
    # Each: (sortino, smooth, earnings, LogVariant, consistency, abs_mom, vol_scl, crash)
    LV = LogVariant
    signal_profiles = [
        # Baseline: arithmetic only
        (False, False, False, LV.NONE,    False, False, False, False),
        # Single signals (test each alone)
        (True,  False, False, LV.NONE,    False, False, False, False),  # sortino only
        (False, True,  False, LV.NONE,    False, False, False, False),  # smoothness only
        (False, False, True,  LV.NONE,    False, False, False, False),  # earnings only
        (False, False, False, LV.BASIC,   False, False, False, False),  # basic log
        (False, False, False, LV.EWMA,    False, False, False, False),  # ewma log
        (False, False, False, LV.VOLNORM, False, False, False, False),  # vol-norm log
        (False, False, False, LV.ACCEL,   False, False, False, False),  # accel log
        (False, False, False, LV.TRIMMED, False, False, False, False),  # trimmed log
        (False, False, False, LV.NONE,    True,  False, False, False),  # 8/12 consistency
        (False, False, False, LV.NONE,    False, True,  False, False),  # dual momentum
        (False, False, False, LV.NONE,    False, False, True,  False),  # vol scaling
        (False, False, False, LV.NONE,    False, False, False, True),   # crash prot
        # Best combos from prior sweep
        (True,  False, True,  LV.NONE,    False, False, False, False),  # sortino + earnings
        (False, False, True,  LV.NONE,    True,  False, False, False),  # earnings + 8/12
        (False, False, False, LV.NONE,    False, True,  True,  False),  # dual + vol_scl
        (True,  False, False, LV.NONE,    False, True,  False, False),  # sortino + dual
        (False, False, True,  LV.NONE,    False, True,  False, False),  # earnings + dual
        # AQR-inspired
        (False, False, False, LV.NONE,    False, False, True,  True),   # vol_scl + crash
        (True,  False, False, LV.NONE,    False, True,  True,  False),  # sortino + dual + vol_scl
        (True,  False, False, LV.NONE,    False, True,  True,  True),   # sort + dual + vol_scl + crash
        # Alpha Architect inspired
        (True,  True,  True,  LV.NONE,    True,  False, False, False),  # sort + smooth + earn + 8/12
        (False, False, True,  LV.BASIC,   True,  True,  False, False),  # earn + log + 8/12 + dual
        # Log variant combos — pair new variants with best signals
        (True,  False, False, LV.VOLNORM, False, False, False, False),  # sortino + vol-norm
        (False, False, True,  LV.EWMA,    False, False, False, False),  # earnings + ewma
        (False, False, True,  LV.ACCEL,   False, False, False, False),  # earnings + accel
        (False, False, False, LV.VOLNORM, False, False, True,  False),  # vol-norm + vol_scl
        (False, False, False, LV.TRIMMED, False, False, True,  False),  # trimmed + vol_scl
        (True,  False, True,  LV.VOLNORM, False, False, False, False),  # sort + earn + vol-norm
        (False, False, True,  LV.ACCEL,   True,  False, False, False),  # earn + accel + 8/12
        # Kitchen sink
        (True,  True,  True,  LV.BASIC,   True,  True,  True,  True),   # everything basic log
        (True,  False, True,  LV.VOLNORM, True,  True,  True,  True),   # everything vol-norm
        (True,  False, True,  LV.EWMA,    True,  True,  True,  True),   # everything ewma
    ]

    for lb, ws, skip, profile, n_pos, rf in product(
        lookbacks, weight_schemes, skips, signal_profiles, positions, rebal_freqs
    ):
        if lb[0] <= skip:
            continue
        sort, smth, earn, lv, cons, dual, vscl, crsh = profile
        configs.append(ScoringParams(
            lb_short=lb[0], lb_mid=lb[1], lb_long=lb[2],
            w_short=ws[0], w_mid=ws[1], w_long=ws[2],
            skip=skip,
            use_sortino=sort, use_smoothness=smth, use_earnings=earn,
            log_variant=lv, use_consistency=cons,
            use_abs_momentum=dual, use_vol_scaling=vscl,
            use_crash_prot=crsh,
            max_positions=n_pos, rebal_freq=rf,
        ))

    return configs


# ── Table builder ────────────────────────────────────────────────────────────


def _fmt(r: WalkForwardResult) -> dict[str, str]:
    return {
        "ret": f"{r.oos_total_return * 100:+.1f}%",
        "ann": f"{r.oos_annualized * 100:+.1f}%",
        "dd": f"{r.oos_max_dd * 100:.1f}%",
        "sortino": f"{r.oos_sortino:.2f}",
        "calmar": f"{r.oos_calmar:.2f}",
        "romad": f"{r.oos_romad:.1f}",
        "win": f"{r.oos_win_rate * 100:.0f}%",
        "pos": f"{r.avg_positions:.0f}",
        "params": r.label(),
    }


def build_table(
    title: str, results: list[WalkForwardResult], limit: int,
    highlight_col: str, columns: list[str],
) -> Table:
    style_map = {
        "ret": ("OOS Ret", "bold green"), "ann": ("Ann.", ""),
        "dd": ("MaxDD", "red"), "sortino": ("Sortino", "cyan"),
        "calmar": ("Calmar", "yellow"), "romad": ("RoMAD", ""),
        "win": ("Win%", ""), "pos": ("Pos", ""),
        "params": ("Params", ""),
    }
    table = Table(title=title)
    table.add_column("#", style="dim", width=3)
    for col in columns:
        label, style = style_map[col]
        s = f"bold {style}" if col == highlight_col else style
        table.add_column(label, justify="right" if col != "params" else "left", style=s)
    for i, r in enumerate(results[:limit]):
        f = _fmt(r)
        table.add_row(str(i + 1), *(f[c] for c in columns))
    return table


ALL_COLS = ["ret", "ann", "dd", "sortino", "calmar", "win", "pos", "params"]


# ── CLI ──────────────────────────────────────────────────────────────────────


def _discover_india_mf_schemes(max_per_query: int = 5) -> list[int]:
    """Discover India MF scheme codes by searching common fund categories."""
    seen = set()
    codes = []
    for query in INDIA_MF_QUERIES:
        results = search_mf_schemes(query)
        for r in results[:max_per_query]:
            sc = r["schemeCode"]
            if sc not in seen:
                seen.add(sc)
                codes.append(sc)
    return codes


@click.command()
@click.option("--top", default=20, help="Show top N results.")
@click.option("--period", default="max", help="Price history period.")
@click.option("--workers", default=11, help="Parallel workers.")
@click.option("--min-train", default=252, help="Min training days.")
@click.option("--oos-window", default=126, help="OOS test window days.")
@click.option("--max-dd-cap", default=0.50, help="MaxDD cap for survivable scenario.")
@click.option("--market", default="us", type=click.Choice(["us", "india"]),
              help="Market: 'us' for US equities (yfinance), 'india' for MFs (mfapi.in).")
@click.option("--mf-max-per-query", default=5, help="Max schemes per search query (India).")
def main(top: int, period: str, workers: int, min_train: int, oos_window: int,
         max_dd_cap: float, market: str, mf_max_per_query: int):
    """Walk-forward momentum sweep — AQR + Alpha Architect signals."""
    global PORTFOLIO_VALUE, IBKR_COMMISSION_PER_SHARE, IBKR_MIN_COMMISSION
    global AVG_SHARE_PRICE, HALF_SPREAD_BPS, CCORP_TAX_RATE, SEC_FINRA_FEE_PER_SHARE

    if market == "india":
        # India cost model: no C-Corp tax, lower commissions, wider spreads
        PORTFOLIO_VALUE = 2_500_000.0       # ₹25L starting capital
        IBKR_COMMISSION_PER_SHARE = 0.0     # MF switches are free
        IBKR_MIN_COMMISSION = 0.0           # No per-order min
        AVG_SHARE_PRICE = 100.0             # Avg NAV
        HALF_SPREAD_BPS = 0.0               # MFs trade at NAV (no spread)
        CCORP_TAX_RATE = 0.125              # 12.5% LTCG on equity MFs (>1yr)
        SEC_FINRA_FEE_PER_SHARE = 0.0       # No regulatory fees
        # Exit load: 1% if redeemed within 1 year for most equity MFs
        # We'll model this as a flat cost on sells for rebal < 252 days

        console.print(f"[bold]Discovering India MF schemes...[/]")
        scheme_codes = _discover_india_mf_schemes(mf_max_per_query)
        console.print(f"[green]Found {len(scheme_codes)} schemes[/]")

        console.print(f"[bold]Fetching NAV history ({period})...[/]")
        prices, dates, fetched = fetch_all_mf_numpy(scheme_codes, period)
        n_days = prices.shape[0]
        if n_days == 0:
            console.print("[red]No data fetched![/]")
            return
        console.print(f"[green]Got {len(fetched)} schemes, {n_days} days ({dates[0]} → {dates[-1]})[/]")
        # No earnings data for MFs
        earn_mom = None
    else:
        console.print(f"[bold]Fetching {len(TICKERS)} tickers ({period})...[/]")
        prices, dates, fetched = fetch_all_numpy(TICKERS, period)
        n_days = prices.shape[0]
        console.print(f"[green]Got {len(fetched)} tickers, {n_days} days ({dates[0]} → {dates[-1]})[/]")

        console.print("[bold]Fetching earnings...[/]")
        earnings = fetch_all_earnings(fetched)
        console.print(f"[green]Earnings for {len(earnings)}/{len(fetched)} tickers[/]")
        earn_mom = build_earnings_momentum(earnings, dates, fetched)

    folds = build_folds(prices, min_train, oos_window)
    console.print(f"[bold]{len(folds)} folds[/] ({dates[folds[0][0]]} → {dates[folds[-1][1]]})")

    grid = build_param_grid()
    console.print(f"[bold]Sweeping {len(grid):,} combos × {len(folds)} folds...[/]")

    # Collect all unique rebalance days across all folds × all rebal frequencies
    all_rebal_days = set()
    for oos_start, oos_end in folds:
        period_len = oos_end - oos_start
        for rf in REBAL_FREQS.values():
            for offset in range(0, period_len, rf):
                all_rebal_days.add(oos_start + offset)
    all_rebal_days_sorted = sorted(all_rebal_days)

    # Collect unique lookbacks and skips from grid
    all_lookbacks = sorted({p.lb_short for p in grid} | {p.lb_mid for p in grid} | {p.lb_long for p in grid} | {252})
    all_skips = sorted({p.skip for p in grid} | {0})

    console.print(f"[dim]Precomputing signals at {len(all_rebal_days_sorted)} rebal dates "
                  f"({len(all_lookbacks)} lookbacks × {len(all_skips)} skips)...[/]")

    results: list[WalkForwardResult] = []
    args_list = [(p, folds) for p in grid]

    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker,
        initargs=(prices, dates, earn_mom, all_rebal_days_sorted, all_lookbacks, all_skips, fetched),
    ) as pool:
        futures = {pool.submit(_worker_run, a): i for i, a in enumerate(args_list)}
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 1000 == 0:
                console.print(f"  [dim]{done}/{len(grid)}...[/]")

    # ══════════════════════════════════════════════════════════════════════════
    #  SCENARIO ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════

    results.sort(key=lambda r: r.oos_total_return, reverse=True)

    # ── Scenario 1: YOLO — Unconstrained max return ──────────────────────────
    console.print(build_table(
        f"YOLO: Max OOS Return, No Constraints ({len(folds)} folds)",
        results, top, "ret", ALL_COLS))

    # ── Scenario 2: Risk tiers — What can you buy at each pain level? ────────
    dd_tiers = [0.30, 0.40, 0.50, 0.60, 0.75]
    tier_table = Table(title="RISK TIERS: Best Ann. Return at Each Pain Level")
    tier_table.add_column("Max DD", style="red", justify="right")
    tier_table.add_column("# Combos", justify="right", style="dim")
    tier_table.add_column("Best Ann.", justify="right", style="bold green")
    tier_table.add_column("Calmar", justify="right", style="yellow")
    tier_table.add_column("Sortino", justify="right", style="cyan")
    tier_table.add_column("Win%", justify="right")
    tier_table.add_column("Best Config", style="")

    for dd_cap in dd_tiers:
        tier = [r for r in results if abs(r.oos_max_dd) <= dd_cap]
        if tier:
            best = max(tier, key=lambda r: r.oos_annualized)
            tier_table.add_row(
                f"≤{dd_cap*100:.0f}%", str(len(tier)),
                f"{best.oos_annualized*100:+.1f}%", f"{best.oos_calmar:.2f}",
                f"{best.oos_sortino:.2f}", f"{best.oos_win_rate*100:.0f}%",
                best.label(),
            )
        else:
            tier_table.add_row(f"≤{dd_cap*100:.0f}%", "0", "—", "—", "—", "—", "—")
    console.print(tier_table)

    # ── Scenario 3: NEVER LOSE A FOLD — Highest win rate with decent return ──
    never_lose = sorted(
        [r for r in results if r.oos_win_rate >= 0.90 and r.oos_annualized > 0],
        key=lambda r: r.oos_annualized, reverse=True,
    )
    console.print(build_table(
        "NEVER LOSE: Win Rate ≥ 90% — Best Return", never_lose, 10, "win", ALL_COLS))

    # ── Scenario 4: WORST SINGLE FOLD — No fold loses more than 20% ─────────
    def max_fold_loss(r: WalkForwardResult) -> float:
        return min(r.fold_returns) if r.fold_returns else -1.0

    no_blowup = sorted(
        [r for r in results if max_fold_loss(r) > -0.20],
        key=lambda r: r.oos_annualized, reverse=True,
    )
    console.print(build_table(
        "NO BLOWUP: No Single Fold Loses > 20% — Best Return",
        no_blowup, 10, "ret", ALL_COLS))

    # ── Scenario 5: CONSISTENCY KING — Lowest fold-to-fold variance ──────────
    consistent = sorted(
        [r for r in results if r.oos_annualized > 0.20],
        key=lambda r: r.consistency,
    )
    console.print(build_table(
        "CONSISTENCY: Lowest Variance (Ann > 20%)", consistent, 10, "params", ALL_COLS))

    # ── Scenario 6: EFFICIENT FRONTIER — Best Calmar at each DD tier ─────────
    frontier_table = Table(title="EFFICIENT FRONTIER: Best Calmar at Each DD Level")
    frontier_table.add_column("DD Band", justify="right")
    frontier_table.add_column("Best Calmar", justify="right", style="bold yellow")
    frontier_table.add_column("Ann.", justify="right", style="green")
    frontier_table.add_column("MaxDD", justify="right", style="red")
    frontier_table.add_column("Sortino", justify="right", style="cyan")
    frontier_table.add_column("Config", style="")

    dd_bands = [(0.0, 0.25), (0.25, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.70), (0.70, 1.0)]
    for lo, hi in dd_bands:
        band = [r for r in results if lo < abs(r.oos_max_dd) <= hi]
        if band:
            best = max(band, key=lambda r: r.oos_calmar)
            frontier_table.add_row(
                f"{lo*100:.0f}-{hi*100:.0f}%",
                f"{best.oos_calmar:.2f}",
                f"{best.oos_annualized*100:+.1f}%",
                f"{best.oos_max_dd*100:.1f}%",
                f"{best.oos_sortino:.2f}",
                best.label(),
            )
    console.print(frontier_table)

    # ── Scenario 7: SLEEP AT NIGHT — DD ≤ 30% and 85%+ win rate ─────────────
    sleep_well = sorted(
        [r for r in results if abs(r.oos_max_dd) <= 0.30 and r.oos_win_rate >= 0.85],
        key=lambda r: r.oos_annualized, reverse=True,
    )
    if sleep_well:
        console.print(build_table(
            "SLEEP AT NIGHT: DD ≤ 30% + Win ≥ 85%", sleep_well, 10, "calmar", ALL_COLS))
    else:
        console.print("[dim]SLEEP AT NIGHT: No combos with DD≤30% and Win≥85%[/]")

    # ── Scenario 8: WHAT IF I QUIT? — Recovery from worst drawdown ───────────
    # For top configs: if you hit max DD and quit, what was the subsequent recovery?
    console.print(f"\n[bold]WHAT IF I QUIT AT MAX DD?[/]")
    console.print("  If you quit after the worst fold, here's what you missed:\n")

    quit_table = Table(title="Quitter's Regret: Post-Worst-Fold Returns")
    quit_table.add_column("Config", style="")
    quit_table.add_column("Worst Fold", justify="right", style="red")
    quit_table.add_column("Next 3 Folds", justify="right", style="green")
    quit_table.add_column("Full Ann.", justify="right")
    quit_table.add_column("MaxDD", justify="right", style="red")

    dd_cap_pct = max_dd_cap * 100
    survivable = sorted(
        [r for r in results if abs(r.oos_max_dd) <= max_dd_cap],
        key=lambda r: r.oos_total_return, reverse=True,
    )

    for r in survivable[:8]:
        folds_arr = r.fold_returns
        if len(folds_arr) < 5:
            continue
        worst_idx = int(np.argmin(folds_arr))
        worst_val = folds_arr[worst_idx]
        # Next 3 folds after the worst
        next_3 = folds_arr[worst_idx + 1:worst_idx + 4]
        if next_3:
            recovery = float(np.prod([1 + x for x in next_3]) - 1)
            quit_table.add_row(
                r.label()[:50],
                f"{worst_val*100:+.1f}%",
                f"{recovery*100:+.1f}%",
                f"{r.oos_annualized*100:+.1f}%",
                f"{r.oos_max_dd*100:.1f}%",
            )
    console.print(quit_table)

    # ── Scenario 9: P10/P50/P90 per-fold returns ────────────────────────────
    console.print(f"\n[bold]FOLD RETURN DISTRIBUTION (top 5 survivable):[/]")
    dist_table = Table(title="Per-Fold Return Percentiles")
    dist_table.add_column("Config", style="")
    dist_table.add_column("P10", justify="right", style="red")
    dist_table.add_column("P25", justify="right")
    dist_table.add_column("P50", justify="right", style="bold")
    dist_table.add_column("P75", justify="right")
    dist_table.add_column("P90", justify="right", style="green")
    dist_table.add_column("Worst", justify="right", style="red")
    dist_table.add_column("Best", justify="right", style="green")

    for r in survivable[:5]:
        fa = np.array(r.fold_returns)
        dist_table.add_row(
            r.label()[:45],
            f"{np.percentile(fa, 10)*100:+.1f}%",
            f"{np.percentile(fa, 25)*100:+.1f}%",
            f"{np.percentile(fa, 50)*100:+.1f}%",
            f"{np.percentile(fa, 75)*100:+.1f}%",
            f"{np.percentile(fa, 90)*100:+.1f}%",
            f"{fa.min()*100:+.1f}%",
            f"{fa.max()*100:+.1f}%",
        )
    console.print(dist_table)

    # ── Scenario 10: STREAK RISK — Worst consecutive losing folds ────────────
    def max_losing_streak(fold_returns: list[float]) -> int:
        streak = max_streak = 0
        for r in fold_returns:
            if r < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    console.print(f"\n[bold]STREAK RISK (top 10 survivable):[/]")
    streak_table = Table(title="Max Consecutive Losing Folds (each fold = 6 months)")
    streak_table.add_column("Config", style="")
    streak_table.add_column("Max Losing Streak", justify="right", style="red")
    streak_table.add_column("= Months Underwater", justify="right", style="red")
    streak_table.add_column("Ann.", justify="right", style="green")
    streak_table.add_column("MaxDD", justify="right")

    for r in survivable[:10]:
        streak = max_losing_streak(r.fold_returns)
        streak_table.add_row(
            r.label()[:45],
            f"{streak} folds",
            f"~{streak * 6} months",
            f"{r.oos_annualized*100:+.1f}%",
            f"{r.oos_max_dd*100:.1f}%",
        )
    console.print(streak_table)

    # ── Scenario 11: RETURN & DD DISTRIBUTIONS across all combos ───────────
    console.print(f"\n[bold]RETURN DISTRIBUTION (all {len(results):,} combos):[/]")
    all_ann = np.array([r.oos_annualized for r in results])
    all_dd = np.array([abs(r.oos_max_dd) for r in results])
    all_sortinos = np.array([r.oos_sortino for r in results])
    all_calmars = np.array([r.oos_calmar for r in results])

    dist_all = Table(title="Distribution of Annualized Returns & Max Drawdowns")
    dist_all.add_column("Metric", style="bold")
    for pct in ["P5", "P10", "P25", "P50", "P75", "P90", "P95"]:
        dist_all.add_column(pct, justify="right")

    pcts = [5, 10, 25, 50, 75, 90, 95]
    dist_all.add_row("Ann. Return",
        *[f"{np.percentile(all_ann, p)*100:+.1f}%" for p in pcts])
    dist_all.add_row("Max DD",
        *[f"{np.percentile(all_dd, p)*100:.1f}%" for p in pcts])
    dist_all.add_row("Sortino",
        *[f"{np.percentile(all_sortinos, p):.2f}" for p in pcts])
    dist_all.add_row("Calmar",
        *[f"{np.percentile(all_calmars, p):.2f}" for p in pcts])
    console.print(dist_all)

    # ── Scenario 12: DD DISTRIBUTION within survivable configs ───────────────
    if survivable:
        surv_ann = np.array([r.oos_annualized for r in survivable])
        surv_dd = np.array([abs(r.oos_max_dd) for r in survivable])
        console.print(f"\n[bold]SURVIVABLE DD DISTRIBUTION ({len(survivable)} combos, DD≤{dd_cap_pct:.0f}%):[/]")
        surv_dist = Table(title="Survivable Configs: What to Expect")
        surv_dist.add_column("Metric", style="bold")
        for pct in ["P5", "P25", "Median", "P75", "P95"]:
            surv_dist.add_column(pct, justify="right")
        sp = [5, 25, 50, 75, 95]
        surv_dist.add_row("Ann. Return",
            *[f"{np.percentile(surv_ann, p)*100:+.1f}%" for p in sp])
        surv_dist.add_row("Max DD",
            *[f"{np.percentile(surv_dd, p)*100:.1f}%" for p in sp])
        console.print(surv_dist)

    # ── Scenario 13: HIGH-VOL REGIME — What works when everything is volatile ──
    # Identify folds where cross-asset realized vol was in the top quartile
    fold_vols = []
    for fold_idx, (fs, fe) in enumerate(folds):
        window = prices[fs:fe]
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.diff(window, axis=0) / window[:-1]
        rets = np.nan_to_num(rets, nan=0.0)
        # Cross-asset vol: median of per-ticker annualized vol
        per_ticker_vol = np.nanstd(rets, axis=0) * np.sqrt(252)
        fold_vols.append(float(np.nanmedian(per_ticker_vol)))

    fold_vols_arr = np.array(fold_vols)
    high_vol_threshold = np.percentile(fold_vols_arr, 75)
    high_vol_folds = [i for i, v in enumerate(fold_vols) if v >= high_vol_threshold]
    low_vol_folds = [i for i, v in enumerate(fold_vols) if v < np.percentile(fold_vols_arr, 25)]

    console.print(f"\n[bold]HIGH-VOL REGIME ANALYSIS[/]")
    console.print(f"  Vol threshold (P75): {high_vol_threshold*100:.1f}% ann.  "
                  f"High-vol folds: {len(high_vol_folds)}/{len(folds)}  "
                  f"Low-vol folds: {len(low_vol_folds)}/{len(folds)}")

    # Score each config only on high-vol folds
    if high_vol_folds and len(high_vol_folds) >= 3:
        high_vol_scores = []
        for r in results:
            hv_rets = [r.fold_returns[i] for i in high_vol_folds if i < len(r.fold_returns)]
            if not hv_rets:
                continue
            hv_total = float(np.prod([1 + x for x in hv_rets]) - 1)
            hv_dd = min(hv_rets)
            n_hv_years = len(hv_rets) * 0.5  # each fold ~ 6 months
            hv_ann = (1 + hv_total) ** (1 / n_hv_years) - 1 if n_hv_years > 0 else 0
            high_vol_scores.append((r, hv_ann, hv_dd, hv_total))

        # Best return in high-vol
        high_vol_scores.sort(key=lambda x: x[1], reverse=True)
        hv_table = Table(title=f"BEST IN HIGH-VOL REGIMES ({len(high_vol_folds)} folds, vol ≥ {high_vol_threshold*100:.0f}%)")
        hv_table.add_column("#", style="dim", width=3)
        hv_table.add_column("HV Ann.", justify="right", style="bold green")
        hv_table.add_column("HV Worst Fold", justify="right", style="red")
        hv_table.add_column("Full Ann.", justify="right")
        hv_table.add_column("Full DD", justify="right", style="red")
        hv_table.add_column("Config", style="")

        for i, (r, hv_ann, hv_dd, _) in enumerate(high_vol_scores[:10]):
            hv_table.add_row(
                str(i + 1),
                f"{hv_ann*100:+.1f}%",
                f"{hv_dd*100:+.1f}%",
                f"{r.oos_annualized*100:+.1f}%",
                f"{r.oos_max_dd*100:.1f}%",
                r.label(),
            )
        console.print(hv_table)

        # Signal dominance in high-vol regime
        top20_hv = [x[0] for x in high_vol_scores[:20]]
        console.print(f"\n[bold]Signal dominance in high-vol (top 20):[/]")
        hv_lv = Counter(r.params.log_variant.value for r in top20_hv)
        console.print(f"  log-variant: {' '.join(f'{k}={v}' for k,v in sorted(hv_lv.items()))}")
        for attr, label in [
            ("use_vol_scaling", "vol-scl"), ("use_crash_prot", "crash-prot"),
            ("use_abs_momentum", "dual-mom"), ("use_earnings", "earnings"),
        ]:
            y = sum(getattr(r.params, attr) for r in top20_hv)
            console.print(f"  {label}: on={y}  off={20-y}")
        hv_rf = Counter(r.params.rebal_freq for r in top20_hv)
        console.print(f"  rebal: {' '.join(f'{k}d={v}' for k,v in sorted(hv_rf.items()))}")

    # ── Scenario 14: COST IMPACT — How much do costs drag returns? ────────────
    console.print(f"\n[bold]COST MODEL (IBKR C-Corp, ${PORTFOLIO_VALUE/1000:.0f}K):[/]")
    console.print(f"  Commission: ${IBKR_COMMISSION_PER_SHARE}/share (tiered), min ${IBKR_MIN_COMMISSION}/order")
    console.print(f"  Half-spread: {HALF_SPREAD_BPS:.0f} bps ({HALF_SPREAD_BPS/100:.2f}%)")
    console.print(f"  C-Corp tax: {CCORP_TAX_RATE*100:.0f}% flat on realized gains")
    console.print(f"  [dim]Note: all scenario returns above are AFTER costs[/]")

    # ══════════════════════════════════════════════════════════════════════════
    #  SUMMARY + SIGNAL DOMINANCE
    # ══════════════════════════════════════════════════════════════════════════

    oos_rets = np.array([r.oos_total_return for r in results])
    console.print(f"\n[bold]Summary[/]  combos={len(results):,}  folds={len(folds)}")
    console.print(f"  OOS return — best: {oos_rets.max()*100:+.1f}%  "
                  f"median: {np.median(oos_rets)*100:+.1f}%  "
                  f"worst: {oos_rets.min()*100:+.1f}%")
    console.print(f"  Survivable (DD≤{dd_cap_pct:.0f}%): {len(survivable)}/{len(results)}")

    top50 = survivable[:min(50, len(survivable))]
    if not top50:
        console.print("  [red]No combos survived the DD cap![/]")
        return

    console.print(f"\n[bold]Signal dominance (top 50 survivable):[/]")
    for attr, label in [
        ("skip", "skip"), ("use_sortino", "sortino"), ("use_smoothness", "smooth"),
        ("use_earnings", "earnings"),
        ("use_consistency", "8/12-cons"), ("use_abs_momentum", "dual-mom"),
        ("use_vol_scaling", "vol-scl"), ("use_crash_prot", "crash-prot"),
    ]:
        vals = [getattr(r.params, attr) for r in top50]
        if isinstance(vals[0], bool):
            y = sum(vals)
            console.print(f"  {label}: on={y}  off={len(top50)-y}")
        else:
            c = Counter(vals)
            console.print(f"  {label}: {' '.join(f'{k}={v}' for k,v in sorted(c.items()))}")
    # Log variant breakdown
    lv_counts = Counter(r.params.log_variant.value for r in top50)
    console.print(f"  log-variant: {' '.join(f'{k}={v}' for k,v in sorted(lv_counts.items()))}")

    rf_counts = Counter(r.params.rebal_freq for r in top50)
    console.print(f"  rebal: {' '.join(f'{k}d={v}' for k,v in sorted(rf_counts.items()))}")
    pc = Counter(r.params.max_positions for r in top50)
    console.print(f"  positions: {' '.join(f'{k}={v}' for k,v in sorted(pc.items()))}")
    wc = Counter((r.params.w_short, r.params.w_mid, r.params.w_long) for r in top50)
    for wt, cnt in wc.most_common(3):
        console.print(f"    w={wt[0]:.1f}/{wt[1]:.1f}/{wt[2]:.1f}: {cnt}")


if __name__ == "__main__":
    main()
