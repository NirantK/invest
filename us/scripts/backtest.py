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
import numba
import numpy as np
from rich.console import Console

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_utils import (
    fetch_all_numpy, fetch_all_earnings, build_earnings_momentum,
    fetch_all_mf_numpy,
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

# Indian ETFs tradeable on NSE/BSE (fetched via yfinance with .NS suffix)
INDIA_ETF_TICKERS = [
    # Broad market
    "NIFTYBEES.NS", "JUNIORBEES.NS", "BANKBEES.NS", "SETFNIF50.NS",
    "BSLNIFTY.NS", "NETFNIF100.NS",
    # Thematic / International
    "MAFANG.NS", "MON100.NS", "NASDAQ100.NS", "N100.NS",
    # Gold / Silver / Commodities
    "GOLDBEES.NS", "SILVERBEES.NS", "GOLDCASE.NS", "COMMOIETF.NS",
    # Sector
    "ITBEES.NS", "PHARMABEES.NS", "PSUBNKBEES.NS", "INFRAEES.NS",
    "CONSUMBEES.NS", "CPSEETF.NS",
    "DIVOPPORTUNITY.NS", "HABORNETF.NS",
    # Factor / Smart-beta
    "NIFTYQLTY.NS", "ALPHAETF.NS", "MOVALUE.NS", "MOMENTUM.NS",
    "LOWVOLIETF.NS", "NV20IETF.NS",
    # Debt / Cash proxy
    "LIQUIDBEES.NS", "LIQUIDCASE.NS", "LIQUID.NS",
    # Midcap / Smallcap
    "MIDCAPETF.NS", "MID150BEES.NS",
    # International
    "HNGSNGBEES.NS", "MOMESETF.NS",
    # REITs & InvITs
    "EMBASSY.NS", "MINDSPACE.NS", "BROOKFIELD.NS",
    "IRFC.NS", "POWERGRID.NS",
    # Large-cap singles (high momentum candidates)
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "LT.NS", "SBIN.NS", "ITC.NS", "TATAMOTORS.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "BAJFINANCE.NS", "WIPRO.NS", "HCLTECH.NS",
    # Metals / Mining / Commodities
    "HINDZINC.NS", "HINDCOPPER.NS", "NATIONALUM.NS", "NMDC.NS", "VEDL.NS",
    "COALINDIA.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    # Other high-momentum candidates
    "ZOMATO.NS", "JIOFIN.NS", "TRENT.NS", "HAL.NS", "BEL.NS",
    "DIXON.NS", "POLYCAB.NS", "PERSISTENT.NS", "COFORGE.NS",
]

MIN_TICKERS_PER_FOLD = 15

# Safe-haven tickers for dual momentum risk-off allocation
SAFE_HAVENS_US = {"GLD", "IAU", "SLV", "SGOV", "SHV", "BIL"}
SAFE_HAVENS_INDIA_ETFS = {
    "GOLDBEES.NS", "GOLDCASE.NS", "SILVERBEES.NS", "SILVERCASE.NS",
    "LIQUIDBEES.NS", "LIQUIDCASE.NS", "LIQUID.NS",
}
# MF safe haven keywords: debt, gold, silver funds (matched by scheme name)
_INDIA_SAFE_KEYWORDS = [
    "liquid", "overnight", "money market",
    "gold", "silver",
    "gilt",
]
SAFE_HAVENS = SAFE_HAVENS_US  # default, overridden at runtime for India


def _build_india_safe_havens(fetched: list[str]) -> set[str]:
    """Build safe haven set for India by matching MF scheme names + ETF tickers."""
    import json
    names_file = Path(__file__).parent.parent / "data" / "mf_scheme_names.json"
    safe = set(SAFE_HAVENS_INDIA_ETFS)
    if names_file.exists():
        name_map = json.loads(names_file.read_text())
        for ticker in fetched:
            if ticker in safe:
                continue
            name = name_map.get(ticker, "").lower()
            if any(kw in name for kw in _INDIA_SAFE_KEYWORDS):
                safe.add(ticker)
    return safe

# Rebalance frequencies in trading days
REBAL_FREQS = {
    "1w": 5,
    "2w": 10,
    "1m": 21,
    "2m": 42,
    "1q": 63,
    "1y": 252,
    "18m": 378,
    "2y": 504,
    "3y": 756,
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
    needed_variants: set[LogVariant] | None = None,
    need_smoothness: bool = True,
    need_consistency: bool = True,
    need_crash: bool = True,
) -> PrecomputedSignals:
    """Precompute all signals at each rebalance date. Called once per worker.

    Pass needed_variants to skip unused log variants (major speedup).
    """
    n_tickers = prices.shape[1]

    # Market proxy for crash protection (precompute once)
    with np.errstate(divide="ignore", invalid="ignore"):
        mkt = np.nanmean(prices, axis=1)

    variants = needed_variants if needed_variants else set(LogVariant)
    mom_keys = set()
    for lb in lookbacks:
        for skip in skips:
            for lv in variants:
                mom_keys.add((lb, skip, lv))

    momentum_cache = {k: {} for k in mom_keys}
    smoothness = {}
    dn_vol_cache = {}
    tv_cache = {}
    consistency_cache = {}
    abs_mom_cache = {}
    crash_cache = {}

    momentum_fn_by_variant = {
        LogVariant.EWMA: momentum_log_ewma,
        LogVariant.VOLNORM: momentum_log_volnorm,
        LogVariant.ACCEL: momentum_log_accel,
        LogVariant.TRIMMED: momentum_log_trimmed,
    }

    # ── Batch simple momentum (NONE, BASIC) across all days at once ──────
    # These only need prices[end-1] and prices[start], fully vectorizable
    rebal_arr = np.array(rebal_days)
    for lb, skip in {(lb, sk) for lb, sk, _ in mom_keys}:
        ends = rebal_arr + 1 - skip   # effective end index
        starts = ends - lb             # effective start index
        valid = (starts >= 0) & (ends > 0) & (ends <= prices.shape[0])

        if LogVariant.NONE in variants:
            result = np.zeros((len(rebal_days), n_tickers))
            v_idx = np.where(valid)[0]
            if len(v_idx) > 0:
                end_prices = prices[ends[v_idx] - 1]
                start_prices = prices[starts[v_idx]]
                with np.errstate(divide="ignore", invalid="ignore"):
                    result[v_idx] = np.nan_to_num(end_prices / start_prices - 1, nan=0.0)
            for i, day in enumerate(rebal_days):
                momentum_cache[(lb, skip, LogVariant.NONE)][day] = result[i]

        if LogVariant.BASIC in variants:
            result = np.zeros((len(rebal_days), n_tickers))
            v_idx = np.where(valid)[0]
            if len(v_idx) > 0:
                end_prices = prices[ends[v_idx] - 1]
                start_prices = prices[starts[v_idx]]
                with np.errstate(divide="ignore", invalid="ignore"):
                    result[v_idx] = np.nan_to_num(np.log(end_prices / start_prices), nan=0.0)
            for i, day in enumerate(rebal_days):
                momentum_cache[(lb, skip, LogVariant.BASIC)][day] = result[i]

    # ── Batch ACCEL momentum (same structure as NONE/BASIC) ────────────
    if LogVariant.ACCEL in variants:
        for lb, skip in {(lb, sk) for lb, sk, lv in mom_keys if lv == LogVariant.ACCEL}:
            ends = rebal_arr + 1 - skip
            starts = ends - lb
            mids = starts + lb // 2
            valid = (starts >= 0) & (ends > 0) & (ends <= prices.shape[0])
            result = np.zeros((len(rebal_days), n_tickers))
            v_idx = np.where(valid)[0]
            if len(v_idx) > 0:
                with np.errstate(divide="ignore", invalid="ignore"):
                    first_half = np.log(prices[mids[v_idx]] / prices[starts[v_idx]])
                    second_half = np.log(prices[ends[v_idx] - 1] / prices[mids[v_idx]])
                    base = np.log(prices[ends[v_idx] - 1] / prices[starts[v_idx]])
                result[v_idx] = np.nan_to_num(base + 0.5 * (second_half - first_half), nan=0.0)
            for i, day in enumerate(rebal_days):
                momentum_cache[(lb, skip, LogVariant.ACCEL)][day] = result[i]

    # ── Batch quality signals across all rebal days ──────────────────────
    # Precompute full daily returns once
    with np.errstate(divide="ignore", invalid="ignore"):
        full_daily_rets = np.nan_to_num(prices[1:] / prices[:-1] - 1, nan=0.0)

    # Downside vol and total vol: rolling std of trailing returns
    for day in rebal_days:
        n = day + 1
        w_dn = min(252, n - 1)
        w_tv = min(126, n - 1)

        if w_dn > 1:
            rets_dn = full_daily_rets[day - w_dn:day]
            neg = np.minimum(rets_dn, 0.0)
            dv = np.sqrt(252) * np.std(neg, axis=0)
            dn_vol_cache[day] = np.where(dv > 0, dv, 0.0001)
        else:
            dn_vol_cache[day] = np.full(n_tickers, 0.0001)

        if w_tv > 1:
            rets_tv = full_daily_rets[day - w_tv:day]
            tv = np.sqrt(252) * np.std(rets_tv, axis=0)
            tv_cache[day] = np.where(tv > 0, tv, 0.0001)
        else:
            tv_cache[day] = np.full(n_tickers, 0.0001)

        # Abs 12m momentum
        lb12 = min(252, n)
        with np.errstate(divide="ignore", invalid="ignore"):
            abs_mom_cache[day] = np.nan_to_num(prices[day] / prices[max(0, day - lb12)] - 1, nan=0.0)

        # Crash protection (scalar, fast)
        crash_cache[day] = crash_protection_signal_at(mkt, day) if need_crash else 1.0

    # Smoothness and consistency: skip the expensive per-day functions if not needed
    if need_smoothness:
        # FIP: fraction of positive daily returns in trailing 252 days
        for day in rebal_days:
            w = min(252, day)
            if w > 1:
                rets_w = full_daily_rets[day - w:day]
                fip_val = np.mean(rets_w > 0, axis=0)
                # R² trend quality — vectorized
                log_p = np.log(np.maximum(prices[day - w:day + 1], 1e-10))
                x = np.arange(w + 1, dtype=np.float64)
                x_mean = x.mean()
                x_var = ((x - x_mean) ** 2).sum()
                if x_var > 0:
                    y_mean = log_p.mean(axis=0)
                    slope = ((x - x_mean)[:, np.newaxis] * (log_p - y_mean)).sum(axis=0) / x_var
                    fitted = slope * (x[:, np.newaxis] - x_mean) + y_mean
                    ss_res = ((log_p - fitted) ** 2).sum(axis=0)
                    ss_tot = ((log_p - y_mean) ** 2).sum(axis=0)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        r2 = np.maximum(np.where(ss_tot > 0, 1.0 - ss_res / ss_tot, 0.0), 0.0)
                else:
                    r2 = np.zeros(n_tickers)
                smoothness[day] = np.sqrt(r2 * fip_val)
            else:
                smoothness[day] = np.ones(n_tickers)
    else:
        for day in rebal_days:
            smoothness[day] = np.ones(n_tickers)

    if need_consistency:
        for day in rebal_days:
            n = day + 1
            if n < 252 + 21:
                consistency_cache[day] = np.ones(n_tickers)
                continue
            end = n - 21
            # Vectorized: compute 11 monthly returns at once
            m_ends = np.array([end - m * 21 for m in range(1, 12) if end - (m + 1) * 21 >= 0])
            m_starts = m_ends - 21
            if len(m_ends) < 8:
                consistency_cache[day] = np.ones(n_tickers)
                continue
            with np.errstate(divide="ignore", invalid="ignore"):
                month_rets = np.nan_to_num(prices[m_ends] / prices[m_starts] - 1, nan=0.0)
            pos_count = np.sum(month_rets > 0, axis=0)
            consistency_cache[day] = np.where(pos_count >= 8, 1.0, 0.0)
    else:
        for day in rebal_days:
            consistency_cache[day] = np.ones(n_tickers)

    # ── Batch VOLNORM: log_return / (std * sqrt(lb)) ───────────────────
    # Reuses BASIC log returns + rolling std of daily log returns
    full_log_prices = np.log(np.maximum(prices, 1e-10))
    full_daily_log_rets = np.nan_to_num(np.diff(full_log_prices, axis=0), nan=0.0, posinf=0.0, neginf=0.0)

    if LogVariant.VOLNORM in variants:
        for lb, skip in {(lb, sk) for lb, sk, lv in mom_keys if lv == LogVariant.VOLNORM}:
            ends = rebal_arr + 1 - skip
            starts = ends - lb
            valid = (starts >= 0) & (ends > 0) & (ends <= prices.shape[0])
            result = np.zeros((len(rebal_days), n_tickers))
            v_idx = np.where(valid)[0]
            if len(v_idx) > 0:
                with np.errstate(divide="ignore", invalid="ignore"):
                    log_ret = np.nan_to_num(np.log(prices[ends[v_idx] - 1] / prices[starts[v_idx]]), nan=0.0)
                # Chunked vol to avoid multi-GB intermediate arrays
                window_len = lb - 1
                row_offsets = np.arange(window_len)[None, :]
                chunk_size = max(1, 200_000_000 // (window_len * n_tickers * 8))  # ~200MB per chunk
                vol = np.empty((len(v_idx), n_tickers))
                for c0 in range(0, len(v_idx), chunk_size):
                    c1 = min(c0 + chunk_size, len(v_idx))
                    indices = starts[v_idx[c0:c1], None] + row_offsets
                    windows = full_daily_log_rets[indices]
                    vol[c0:c1] = np.std(windows, axis=1)
                vol = np.where(vol > 0, vol, 0.0001)
                result[v_idx] = np.nan_to_num(log_ret / (vol * np.sqrt(lb)), nan=0.0, posinf=0.0, neginf=0.0)
            for i, day in enumerate(rebal_days):
                momentum_cache[(lb, skip, LogVariant.VOLNORM)][day] = result[i]

    # ── Remaining complex variants: EWMA, TRIMMED (per-day, smaller loops) ──
    remaining_keys = [(lb, skip, lv) for lb, skip, lv in mom_keys
                      if lv in (LogVariant.EWMA, LogVariant.TRIMMED)]

    if remaining_keys:
        # Precompute EWMA weights for each lookback (reusable across days)
        ewma_weights = {}
        for lb, _, lv in remaining_keys:
            if lv == LogVariant.EWMA and lb not in ewma_weights:
                decay = np.log(2) / 63  # halflife=63
                w = np.exp(decay * np.arange(lb - 1, dtype=np.float64))
                ewma_weights[lb] = w / w.sum()

        for day in rebal_days:
            n = day + 1
            for lb, skip, variant in remaining_keys:
                if n < lb + skip + 1:
                    momentum_cache[(lb, skip, variant)][day] = np.zeros(n_tickers)
                elif variant == LogVariant.EWMA:
                    end = n - skip
                    start = end - lb
                    daily_log = full_daily_log_rets[start:end - 1]
                    w = ewma_weights[lb]
                    # Trim weight vector if daily_log is shorter
                    ww = w[:daily_log.shape[0]]
                    ww = ww / ww.sum()
                    momentum_cache[(lb, skip, variant)][day] = (ww[:, np.newaxis] * daily_log).sum(axis=0)
                else:  # TRIMMED
                    momentum_cache[(lb, skip, variant)][day] = momentum_log_trimmed(prices[:n], lb, skip)

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


def _compute_weights(
    scores: np.ndarray,
    valid: np.ndarray,
    n_tickers: int,
    max_positions: int,
    use_vol_scaling: bool,
    use_abs_momentum: bool,
    safe_arr: np.ndarray,
    tv: np.ndarray | None,
    abs_mom_12m: np.ndarray | None,
) -> tuple[np.ndarray, int]:
    """Select top-N positions and compute weights. Returns (weights, n_positions)."""
    if len(valid) == 0:
        # Dual momentum risk-off: allocate to best safe haven
        if len(safe_arr) > 0 and use_abs_momentum and abs_mom_12m is not None:
            best_sh = safe_arr[np.argmax(abs_mom_12m[safe_arr])]
            weights = np.zeros(n_tickers)
            weights[best_sh] = 1.0
            return weights, 1
        return np.zeros(n_tickers), 0

    top_n = min(max_positions, len(valid))
    top_idx = valid[np.argsort(scores[valid])[-top_n:]]

    if use_abs_momentum and len(safe_arr) > 0 and top_n < max_positions:
        n_risk = top_n
        best_sh = safe_arr[np.argmax(abs_mom_12m[safe_arr])] if abs_mom_12m is not None else safe_arr[0]
        weights = np.zeros(n_tickers)
        risk_share = n_risk / max_positions
        if use_vol_scaling and tv is not None:
            inv_vol = 1.0 / tv[top_idx]
            weights[top_idx] = risk_share * inv_vol / inv_vol.sum()
        else:
            weights[top_idx] = risk_share / n_risk
        weights[best_sh] += (1.0 - risk_share)
    elif use_vol_scaling and tv is not None:
        inv_vol = 1.0 / tv[top_idx]
        weights = np.zeros(n_tickers)
        weights[top_idx] = inv_vol / inv_vol.sum()
    else:
        weights = np.zeros(n_tickers)
        weights[top_idx] = 1.0 / top_n

    return weights, top_n


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
    safe_mask = np.zeros(n_tickers, dtype=bool)
    safe_arr = np.empty(0, dtype=np.intp)
    if ticker_names and params.use_abs_momentum:
        safe_arr = np.array([i for i, t in enumerate(ticker_names) if t in SAFE_HAVENS], dtype=np.intp)
        safe_mask[safe_arr] = True

    rebal_offsets = list(range(0, period_len, params.rebal_freq))

    for idx, rb_offset in enumerate(rebal_offsets):
        next_offset = rebal_offsets[idx + 1] if idx + 1 < len(rebal_offsets) else period_len

        rb_abs = oos_start + rb_offset
        earn_row = earn_mom[rb_abs] if earn_mom is not None else None
        scores = score_from_cache(rb_abs, params, cache, earn_row)
        valid = np.where((scores > 0) & ~safe_mask)[0]

        weights, n_pos = _compute_weights(
            scores, valid, n_tickers, params.max_positions,
            params.use_vol_scaling, params.use_abs_momentum,
            safe_arr,
            cache.tv.get(rb_abs) if cache is not None else None,
            cache.abs_mom_12m.get(rb_abs, np.zeros(n_tickers)) if cache is not None else None,
        )
        if n_pos == 0 and len(valid) == 0 and not (len(safe_arr) > 0 and params.use_abs_momentum):
            portfolio_value[rb_offset + 1:next_offset + 1] = portfolio_value[rb_offset]
            position_counts.append(0)
            prev_weights = np.zeros(n_tickers)
            continue
        position_counts.append(n_pos)

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
_G_DAILY_RETS: np.ndarray | None = None  # precomputed: prices[t+1]/prices[t] - 1
_G_DATES: np.ndarray | None = None
_G_EARN_MOM: np.ndarray | None = None
_G_CACHE: PrecomputedSignals | None = None
_G_TICKERS: list[str] | None = None


def _init_worker(
    prices: np.ndarray, dates: np.ndarray,
    earn_mom: np.ndarray | None, ticker_names: list[str],
    rebal_days: list[int], lookbacks: list[int], skips: list[int],
    needed_variants: set, need_smoothness: bool,
    need_consistency: bool, need_crash: bool,
):
    """Initialize worker: precompute signals and daily returns."""
    global _G_PRICES, _G_DAILY_RETS, _G_DATES, _G_EARN_MOM, _G_CACHE, _G_TICKERS
    _G_PRICES = prices
    with np.errstate(divide="ignore", invalid="ignore"):
        _G_DAILY_RETS = np.nan_to_num(prices[1:] / prices[:-1] - 1, nan=0.0)
    _G_DATES = dates
    _G_EARN_MOM = earn_mom
    _G_TICKERS = ticker_names
    _G_CACHE = precompute_signals(
        prices, rebal_days, lookbacks, skips,
        needed_variants=needed_variants,
        need_smoothness=need_smoothness,
        need_consistency=need_consistency,
        need_crash=need_crash,
    )


def _worker_run(args: tuple) -> WalkForwardResult:
    params, folds = args
    return walk_forward_backtest(
        _G_PRICES, params, folds=folds, earn_mom=_G_EARN_MOM,
        cache=_G_CACHE, ticker_names=_G_TICKERS,
    )


def _score_key(p: ScoringParams) -> tuple:
    """Extract the scoring-relevant params (everything except max_positions and rebal_freq)."""
    return (p.lb_short, p.lb_mid, p.lb_long, p.w_short, p.w_mid, p.w_long,
            p.skip, p.use_sortino, p.use_smoothness, p.use_earnings,
            p.log_variant, p.use_consistency, p.use_abs_momentum,
            p.use_vol_scaling, p.use_crash_prot)


@numba.njit(cache=True)
def _run_fold_numba(
    daily_rets: np.ndarray,
    scores_at_offsets: np.ndarray,
    rebal_offsets: np.ndarray,
    period_len: np.int64,
    all_max_pos: np.ndarray,
    safe_mask: np.ndarray,
) -> np.ndarray:
    """Numba-accelerated inner fold loop for equal-weight configs (no vol-scaling, no cost model).

    Args:
        daily_rets: (period_len, n_tickers) daily returns for this fold
        scores_at_offsets: (n_rebal, n_tickers) precomputed scores at each rebal offset
        rebal_offsets: (n_rebal,) offsets within the fold
        period_len: total days in fold
        all_max_pos: (n_sizes,) sorted array of position sizes to evaluate
        safe_mask: (n_tickers,) boolean mask for safe-haven tickers

    Returns:
        portfolio_values: (n_sizes, period_len+1) portfolio value curves
    """
    n_sizes = len(all_max_pos)
    n_tickers = daily_rets.shape[1]
    n_rebal = len(rebal_offsets)
    pv = np.ones((n_sizes, period_len + 1))

    for idx_rb in range(n_rebal):
        rb_offset = rebal_offsets[idx_rb]
        next_offset = rebal_offsets[idx_rb + 1] if idx_rb + 1 < n_rebal else period_len

        scores = scores_at_offsets[idx_rb]

        # Count valid (score > 0 and not safe-haven)
        n_valid = 0
        for j in range(n_tickers):
            if scores[j] > 0 and not safe_mask[j]:
                n_valid += 1

        if n_valid == 0:
            for si in range(n_sizes):
                for d in range(rb_offset + 1, min(next_offset + 1, period_len + 1)):
                    pv[si, d] = pv[si, rb_offset]
            continue

        # Sort valid indices by score ascending (last elements = highest scores)
        valid_indices = np.empty(n_valid, dtype=np.int64)
        vi = 0
        for j in range(n_tickers):
            if scores[j] > 0 and not safe_mask[j]:
                valid_indices[vi] = j
                vi += 1

        # Simple insertion sort (n_valid is typically small, < 100)
        for i in range(1, n_valid):
            key_idx = valid_indices[i]
            key_score = scores[key_idx]
            j = i - 1
            while j >= 0 and scores[valid_indices[j]] > key_score:
                valid_indices[j + 1] = valid_indices[j]
                j -= 1
            valid_indices[j + 1] = key_idx

        n_hold = min(next_offset, period_len) - rb_offset
        if n_hold <= 0:
            continue

        actual = min(n_hold, next_offset - rb_offset)

        for si in range(n_sizes):
            top_n = min(all_max_pos[si], n_valid)
            # Equal weight: 1/top_n for top-N tickers
            w = 1.0 / top_n

            # Compute daily portfolio returns and cumprod inline
            cum = pv[si, rb_offset]
            for d in range(actual):
                port_ret = 0.0
                for k in range(top_n):
                    tidx = valid_indices[n_valid - 1 - k]  # descending
                    port_ret += daily_rets[rb_offset + d, tidx] * w
                cum *= (1.0 + port_ret)
                pv[si, rb_offset + 1 + d] = cum

    return pv


def _worker_run_batch(args: tuple) -> list[WalkForwardResult]:
    """Run a batch of params sharing the same score signature.

    Precomputes scores at all possible rebal days ONCE, then derives
    results for each (max_positions, rebal_freq) variant cheaply.
    """
    params_list, folds = args
    if not params_list:
        return []

    # All params in batch share the same scoring — use first to compute scores
    ref = params_list[0]

    # Collect all rebal days across all folds × all rebal_freqs in this batch
    all_rebal_freqs = sorted({p.rebal_freq for p in params_list})
    rebal_day_set = set()
    for oos_start, oos_end in folds:
        period_len = oos_end - oos_start
        for rf in all_rebal_freqs:
            for offset in range(0, period_len, rf):
                rebal_day_set.add(oos_start + offset)

    # Precompute scores at all needed rebal days (ONCE for the batch)
    em = _G_EARN_MOM if ref.use_earnings else None
    score_at_day = {}
    for day in sorted(rebal_day_set):
        earn_row = em[day] if em is not None else None
        score_at_day[day] = score_from_cache(day, ref, _G_CACHE, earn_row)

    # Group by rebal_freq, then batch all max_positions variants together
    from collections import defaultdict
    by_rebal = defaultdict(list)
    for p in params_list:
        by_rebal[p.rebal_freq].append(p)

    n_tickers = _G_PRICES.shape[1]
    safe_mask = np.zeros(n_tickers, dtype=bool)
    if _G_TICKERS and ref.use_abs_momentum:
        safe_arr = np.array([i for i, t in enumerate(_G_TICKERS) if t in SAFE_HAVENS], dtype=np.intp)
        if len(safe_arr) > 0:
            safe_mask[safe_arr] = True
    cache = _G_CACHE

    results_dict = {}

    for rf, rf_params in by_rebal.items():
        all_max_pos = sorted({p.max_positions for p in rf_params})
        max_max_pos = max(all_max_pos)
        use_vol_scaling = rf_params[0].use_vol_scaling
        use_abs_momentum = rf_params[0].use_abs_momentum

        # For each fold, run the rebal loop ONCE with max(max_positions),
        # and record portfolio values for all position sizes simultaneously
        fold_data = {n: [] for n in all_max_pos}  # n_pos → list of (fold_return, daily_values)

        # Numba fast path: equal-weight only (no vol-scaling, no dual-momentum safe-haven)
        use_numba = not use_vol_scaling and not use_abs_momentum
        all_max_pos_arr = np.array(all_max_pos, dtype=np.int64)

        for oos_start, oos_end in folds:
            period_len = oos_end - oos_start
            rebal_offsets_list = list(range(0, period_len, rf))
            rebal_offsets_arr = np.array(rebal_offsets_list, dtype=np.int64)

            if use_numba:
                # Build scores_at_offsets: (n_rebal, n_tickers)
                n_rebal = len(rebal_offsets_list)
                scores_at_offsets = np.full((n_rebal, n_tickers), -1.0)
                for idx_rb, rb_offset in enumerate(rebal_offsets_list):
                    rb_abs = oos_start + rb_offset
                    scores_at_offsets[idx_rb] = score_at_day.get(rb_abs, np.full(n_tickers, -1.0))

                # daily_rets for this fold period (relative to fold start)
                fold_daily_rets = _G_DAILY_RETS[oos_start:oos_start + period_len]

                pv_all = _run_fold_numba(
                    fold_daily_rets, scores_at_offsets, rebal_offsets_arr,
                    np.int64(period_len), all_max_pos_arr, safe_mask,
                )
                for si, n_pos in enumerate(all_max_pos):
                    ret = pv_all[si, -1] / pv_all[si, 0] - 1
                    fold_data[n_pos].append((ret, pv_all[si].copy(), float(n_pos)))
                continue

            # Python path: vol-scaling or dual-momentum configs
            pv = {n: np.ones(period_len + 1) for n in all_max_pos}
            pos_counts = {n: [] for n in all_max_pos}

            for idx_rb, rb_offset in enumerate(rebal_offsets_list):
                next_offset = rebal_offsets_list[idx_rb + 1] if idx_rb + 1 < len(rebal_offsets_list) else period_len
                rb_abs = oos_start + rb_offset

                scores = score_at_day.get(rb_abs, np.full(n_tickers, -1.0))
                valid = np.where((scores > 0) & ~safe_mask)[0]

                # Sort valid descending by score (once)
                if len(valid) > 0:
                    sorted_valid = valid[np.argsort(scores[valid])]  # ascending
                else:
                    sorted_valid = np.array([], dtype=int)

                # Daily returns slice (shared across all position sizes)
                day_start = oos_start + rb_offset
                day_end = min(oos_start + next_offset, _G_PRICES.shape[0] - 1)
                n_hold = day_end - day_start
                if n_hold <= 0:
                    for n in all_max_pos:
                        pos_counts[n].append(0)
                    continue

                daily_rets_slice = _G_DAILY_RETS[day_start:day_end]

                if len(sorted_valid) == 0:
                    for n in all_max_pos:
                        pv[n][rb_offset + 1:next_offset + 1] = pv[n][rb_offset]
                        pos_counts[n].append(0)
                    continue

                # Build weight matrix for all position sizes at once: (n_sizes, n_tickers)
                n_sizes = len(all_max_pos)
                weight_matrix = np.zeros((n_sizes, n_tickers))
                actual_counts = []

                if use_vol_scaling and cache is not None:
                    tv = cache.tv.get(rb_abs, np.ones(n_tickers) * 0.0001)

                for si, n_pos in enumerate(all_max_pos):
                    top_n = min(n_pos, len(sorted_valid))
                    top_idx = sorted_valid[-top_n:]
                    if use_vol_scaling and cache is not None:
                        inv_vol = 1.0 / tv[top_idx]
                        weight_matrix[si, top_idx] = inv_vol / inv_vol.sum()
                    else:
                        weight_matrix[si, top_idx] = 1.0 / top_n
                    actual_counts.append(top_n)

                # Single matmul: (n_hold, n_tickers) @ (n_tickers, n_sizes) → (n_hold, n_sizes)
                all_port_rets = daily_rets_slice @ weight_matrix.T

                actual = min(n_hold, next_offset - rb_offset)
                # Vectorized cumprod across all position sizes at once
                all_cum = np.cumprod(1 + all_port_rets[:actual], axis=0)  # (actual, n_sizes)
                for si, n_pos in enumerate(all_max_pos):
                    pos_counts[n_pos].append(actual_counts[si])
                    pv[n_pos][rb_offset + 1:rb_offset + 1 + actual] = (
                        pv[n_pos][rb_offset] * all_cum[:, si]
                    )

            for n in all_max_pos:
                ret = pv[n][-1] / pv[n][0] - 1
                fold_data[n].append((ret, pv[n], np.mean(pos_counts[n]) if pos_counts[n] else 0))

        # Build WalkForwardResult for each (max_positions, rebal_freq) combo
        for n_pos in all_max_pos:
            fold_rets = [fd[0] for fd in fold_data[n_pos]]
            all_daily = [fd[1] for fd in fold_data[n_pos]]
            avg_pos_list = [fd[2] for fd in fold_data[n_pos]]
            results_dict[(n_pos, rf)] = _aggregate_folds(
                fold_rets, all_daily, folds, avg_pos_list, None,
            )

    # Map results back to original params
    results = []
    for p in params_list:
        key = (p.max_positions, p.rebal_freq)
        r = results_dict.get(key)
        if r is not None:
            # Create new result with correct params
            results.append(WalkForwardResult(
                oos_total_return=r.oos_total_return, oos_annualized=r.oos_annualized,
                oos_max_dd=r.oos_max_dd, oos_sortino=r.oos_sortino, oos_calmar=r.oos_calmar,
                oos_romad=r.oos_romad, oos_win_rate=r.oos_win_rate, n_folds=r.n_folds,
                avg_positions=r.avg_positions, consistency=r.consistency,
                params=p, fold_returns=r.fold_returns,
            ))
        else:
            results.append(WalkForwardResult(0, 0, -1, 0, 0, 0, 0, 0, 0, 1.0, p))
    return results


def _walk_forward_with_prescored(
    prices: np.ndarray,
    params: ScoringParams,
    folds: list[tuple[int, int]],
    score_at_day: dict[int, np.ndarray],
    cache: PrecomputedSignals,
    ticker_names: list[str] | None,
) -> WalkForwardResult:
    """Walk-forward using precomputed scores (avoids redundant score_from_cache calls)."""
    if not folds:
        return WalkForwardResult(0, 0, -1, 0, 0, 0, 0, 0, 0, 1.0, params)

    fold_returns = []
    all_daily_values = []
    total_positions = []
    n_tickers = prices.shape[1]

    safe_mask = np.zeros(n_tickers, dtype=bool)
    safe_arr = np.empty(0, dtype=np.intp)
    if ticker_names and params.use_abs_momentum:
        safe_arr = np.array([i for i, t in enumerate(ticker_names) if t in SAFE_HAVENS], dtype=np.intp)
        safe_mask[safe_arr] = True

    prev_weights = np.zeros(n_tickers)
    cost_basis = np.ones(n_tickers)

    for oos_start, oos_end in folds:
        period_len = oos_end - oos_start
        portfolio_value = np.ones(period_len + 1)
        position_counts = []
        prev_weights[:] = 0
        cost_basis[:] = 1.0

        rebal_offsets = list(range(0, period_len, params.rebal_freq))

        for idx, rb_offset in enumerate(rebal_offsets):
            next_offset = rebal_offsets[idx + 1] if idx + 1 < len(rebal_offsets) else period_len
            rb_abs = oos_start + rb_offset

            # Use precomputed scores
            scores = score_at_day.get(rb_abs)
            if scores is None:
                scores = np.full(n_tickers, -1.0)

            valid = np.where((scores > 0) & ~safe_mask)[0]

            weights, n_pos = _compute_weights(
                scores, valid, n_tickers, params.max_positions,
                params.use_vol_scaling, params.use_abs_momentum,
                safe_arr,
                cache.tv.get(rb_abs) if cache is not None else None,
                cache.abs_mom_12m.get(rb_abs, np.zeros(n_tickers)),
            )
            if n_pos == 0 and len(valid) == 0 and not (len(safe_arr) > 0 and params.use_abs_momentum):
                portfolio_value[rb_offset + 1:next_offset + 1] = portfolio_value[rb_offset]
                position_counts.append(0)
                prev_weights[:] = 0
                continue
            position_counts.append(n_pos)

            # Rebalance cost
            current_price_ratio = prices[rb_abs] / prices[oos_start] if prices[oos_start].sum() > 0 else np.ones(n_tickers)
            rebal_cost_frac = _compute_rebalance_cost(
                prev_weights, weights, cost_basis, current_price_ratio,
            )
            new_positions = (weights > 0.001) & (prev_weights < 0.001)
            cost_basis[new_positions] = current_price_ratio[new_positions]
            portfolio_value[rb_offset] *= (1.0 - rebal_cost_frac)
            prev_weights = weights.copy()

            # Daily returns (from precomputed matrix — no division needed)
            day_start = oos_start + rb_offset
            day_end = min(oos_start + next_offset, prices.shape[0] - 1)
            n_hold = day_end - day_start
            if n_hold <= 0:
                continue

            daily_rets = _G_DAILY_RETS[day_start:day_end]
            port_rets = daily_rets @ weights
            cum = np.cumprod(1 + port_rets)
            actual = min(n_hold, next_offset - rb_offset)
            portfolio_value[rb_offset + 1:rb_offset + 1 + actual] = (
                portfolio_value[rb_offset] * cum[:actual]
            )

        oos_return = portfolio_value[-1] / portfolio_value[0] - 1
        fold_returns.append(oos_return)
        total_positions.append(np.mean(position_counts) if position_counts else 0)
        all_daily_values.append(portfolio_value)

    return _aggregate_folds(fold_returns, all_daily_values, folds, total_positions, params)


def _aggregate_folds(
    fold_returns: list[float],
    all_daily_values: list[np.ndarray],
    folds: list[tuple[int, int]],
    total_positions: list[float],
    params: ScoringParams | None,
) -> WalkForwardResult:
    """Aggregate per-fold results into a single WalkForwardResult.

    Chains daily portfolio values, computes max drawdown, annualized return,
    sortino, calmar, and romad.
    """
    oos_total = float(np.prod([1 + r for r in fold_returns]) - 1)

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

    dr = np.diff(scaled) / scaled[:-1]
    dr = dr[np.isfinite(dr)]
    neg = dr[dr < 0]
    dn_vol = float(neg.std() * np.sqrt(252)) if len(neg) > 0 else 0.0001
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

    return _aggregate_folds(fold_returns, all_daily_values, folds, total_positions, params)


# ── Parameter grid ───────────────────────────────────────────────────────────


def build_param_grid() -> list[ScoringParams]:
    """Build full parameter grid. Runtime pruning handles the rest."""
    LV = LogVariant
    configs = []

    lookbacks = [
        (10, 42, 126),    # 2W/2M/6M
        (21, 63, 252),    # 1M/3M/12M
        (42, 126, 252),   # 2M/6M/12M
        (63, 126, 252),   # 3M/6M/12M
        (21, 42, 63),     # 1M/2M/3M
        (126, 252, 504),  # 6M/12M/24M
        (252, 504, 756),  # 12M/24M/36M
    ]
    weight_schemes = [
        (0.4, 0.4, 0.2),
        (0.5, 0.3, 0.2),
        (0.7, 0.2, 0.1),
        (0.1, 0.3, 0.6),
        (0.33, 0.34, 0.33),
    ]
    skips = [0, 21]
    positions = [2, 3, 5, 8, 10, 15, 30]
    rebal_freqs = [5, 10, 21, 42, 63, 252, 378, 504, 756]

    signal_profiles = [
        (False, False, False, LV.NONE,    False, False, False, False),  # baseline
        (True,  False, False, LV.NONE,    False, False, False, False),  # sortino
        (False, True,  False, LV.NONE,    False, False, False, False),  # smooth
        (False, False, True,  LV.NONE,    False, False, False, False),  # earnings
        (False, False, False, LV.BASIC,   False, False, False, False),  # basic log
        (False, False, False, LV.EWMA,    False, False, False, False),  # ewma
        (False, False, False, LV.VOLNORM, False, False, False, False),  # vol-norm
        (False, False, False, LV.ACCEL,   False, False, False, False),  # accel
        (False, False, False, LV.TRIMMED, False, False, False, False),  # trimmed
        (False, False, False, LV.NONE,    True,  False, False, False),  # 8/12
        (False, False, False, LV.NONE,    False, True,  False, False),  # dual
        (False, False, False, LV.NONE,    False, False, True,  False),  # vol_scl
        (False, False, False, LV.NONE,    False, False, False, True),   # crash
        (True,  False, True,  LV.NONE,    False, False, False, False),  # sort+earn
        (False, False, True,  LV.NONE,    True,  False, False, False),  # earn+8/12
        (False, False, False, LV.NONE,    False, True,  True,  False),  # dual+vscl
        (False, False, False, LV.NONE,    False, False, True,  True),   # vscl+crash
        (True,  True,  True,  LV.NONE,    True,  False, False, False),  # AA kitchen
        (False, False, True,  LV.EWMA,    False, False, False, False),  # earn+ewma
        (False, False, True,  LV.ACCEL,   False, False, False, False),  # earn+accel
        (False, False, False, LV.EWMA,    False, False, True,  False),  # ewma+vscl
        (False, False, False, LV.TRIMMED, False, False, True,  False),  # trim+vscl
        (True,  False, False, LV.VOLNORM, False, False, False, False),  # sort+vnorm
        (True,  False, True,  LV.VOLNORM, False, False, False, False),  # sort+earn+vnorm
        (True,  True,  True,  LV.EWMA,    True,  True,  True,  True),   # everything ewma
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


PRUNE_INTERVAL_SEC = 120  # prune every 2 minutes wall clock
PRUNE_KEEP_RATIO = 0.5    # keep top 50% at each prune pass
PRUNE_MIN_RESULTS = 500   # need at least this many results before first prune


def _prune_grid(
    results_so_far: list[WalkForwardResult],
    remaining_params: set[int],  # indices into grid
    grid: list[ScoringParams],
) -> set[int]:
    """Drop bottom-half param dimensions based on results so far.

    Identifies which param values (skip, positions, rebal_freq, log_variant)
    are consistently in the bottom quartile, and removes all grid entries
    that use those values.
    """
    if len(results_so_far) < PRUNE_MIN_RESULTS:
        return remaining_params

    # Sort by annualized return
    sorted_results = sorted(results_so_far, key=lambda r: r.oos_annualized, reverse=True)
    n_top = max(len(sorted_results) // 4, 20)
    top_results = sorted_results[:n_top]
    bottom_results = sorted_results[-n_top:]

    # Count param values in top vs bottom quartile
    prune_dims = [
        ("skip", lambda p: p.skip),
        ("max_positions", lambda p: p.max_positions),
        ("rebal_freq", lambda p: p.rebal_freq),
        ("log_variant", lambda p: p.log_variant),
        ("lb_short", lambda p: p.lb_short),
    ]

    dead_values = {}  # {dim_name: set of values to kill}
    for dim_name, accessor in prune_dims:
        top_counts = Counter(accessor(r.params) for r in top_results)
        bottom_counts = Counter(accessor(r.params) for r in bottom_results)
        all_values = set(top_counts.keys()) | set(bottom_counts.keys())

        for val in all_values:
            top_n = top_counts.get(val, 0)
            bot_n = bottom_counts.get(val, 0)
            # Kill values that appear 5x+ more in bottom than top
            if bot_n >= 5 and top_n == 0:
                dead_values.setdefault(dim_name, set()).add(val)
            elif bot_n > 0 and top_n > 0 and bot_n / max(top_n, 1) >= 5:
                dead_values.setdefault(dim_name, set()).add(val)

    if not dead_values:
        return remaining_params

    # Filter remaining grid indices
    pruned = set()
    accessors = {name: fn for name, fn in prune_dims}
    for idx in remaining_params:
        p = grid[idx]
        keep = True
        for dim_name, dead_vals in dead_values.items():
            if accessors[dim_name](p) in dead_vals:
                keep = False
                break
        if keep:
            pruned.add(idx)

    return pruned


# ── CLI ──────────────────────────────────────────────────────────────────────


MF_MASTER_PARQUET = Path(__file__).parent.parent / "data" / "mf_schemes_direct_growth.parquet"


def _discover_india_mf_schemes() -> list[int]:
    """Load Direct Growth MF scheme codes from pre-built parquet.

    Run `uv run python us/scripts/fetch_mf_master.py` to regenerate.
    """
    import polars as pl

    if not MF_MASTER_PARQUET.exists():
        raise FileNotFoundError(
            f"{MF_MASTER_PARQUET} not found. Run: uv run python us/scripts/fetch_mf_master.py"
        )

    df = pl.read_parquet(MF_MASTER_PARQUET)
    return df["scheme_code"].to_list()


@dataclass
class MarketConfig:
    portfolio_value: float
    commission_per_share: float
    min_commission: float
    avg_share_price: float
    half_spread_bps: float
    tax_rate: float
    sec_finra_fee: float
    label: str


def _load_market_data(
    market: str, period: str,
) -> tuple[np.ndarray, np.ndarray, list[str], np.ndarray | None, MarketConfig]:
    """Load prices, dates, tickers, earnings, and cost config for a market."""
    global PORTFOLIO_VALUE, IBKR_COMMISSION_PER_SHARE, IBKR_MIN_COMMISSION
    global AVG_SHARE_PRICE, HALF_SPREAD_BPS, CCORP_TAX_RATE, SEC_FINRA_FEE_PER_SHARE

    global SAFE_HAVENS
    if market == "india":
        pass  # SAFE_HAVENS set after fetched list is built
        # India cost model (2026 rates)
        # STT 0.1% buy+sell, exchange fees, stamp duty, STCG 20%
        # Blended (70% MF exit load, 30% stocks): ~38 bps half-spread
        cfg = MarketConfig(
            portfolio_value=2_500_000.0, commission_per_share=0.0,
            min_commission=0.0, avg_share_price=500.0,
            half_spread_bps=38.0, tax_rate=0.20, sec_finra_fee=0.0,
            label="India (Zerodha/Groww, ₹25L)",
        )

        console.print("[bold]Discovering India MF schemes...[/]")
        scheme_codes = _discover_india_mf_schemes()
        console.print(f"[green]Found {len(scheme_codes)} schemes[/]")

        console.print(f"[bold]Fetching MF NAV history ({period})...[/]")
        mf_prices, mf_dates, mf_fetched = fetch_all_mf_numpy(scheme_codes, period)

        console.print(f"[bold]Fetching {len(INDIA_ETF_TICKERS)} Indian ETFs...[/]")
        etf_prices, etf_dates, etf_fetched = fetch_all_numpy(INDIA_ETF_TICKERS, period)
        console.print(f"[green]Got {len(etf_fetched)} ETFs[/]")

        # Merge MF + ETF data on common dates
        if mf_prices.shape[0] > 0 and etf_prices.shape[0] > 0:
            all_dates_set = sorted(set(mf_dates.tolist()) | set(etf_dates.tolist()))
            date_to_idx = {d: i for i, d in enumerate(all_dates_set)}
            n_combined = len(mf_fetched) + len(etf_fetched)
            prices = np.full((len(all_dates_set), n_combined), np.nan)
            mf_row_idx = np.array([date_to_idx[d] for d in mf_dates], dtype=np.intp)
            for j in range(len(mf_fetched)):
                prices[mf_row_idx, j] = mf_prices[:, j]
            etf_row_idx = np.array([date_to_idx[d] for d in etf_dates], dtype=np.intp)
            for j in range(len(etf_fetched)):
                prices[etf_row_idx, len(mf_fetched) + j] = etf_prices[:, j]
            from data_utils import _forward_fill_columns
            _forward_fill_columns(prices)
            dates = np.array(all_dates_set)
            fetched = mf_fetched + etf_fetched
        elif mf_prices.shape[0] > 0:
            prices, dates, fetched = mf_prices, mf_dates, mf_fetched
        else:
            prices, dates, fetched = etf_prices, etf_dates, etf_fetched

        if prices.shape[0] == 0:
            console.print("[red]No data fetched![/]")
            raise SystemExit(1)
        console.print(f"[green]Got {len(fetched)} total ({len(mf_fetched)} MFs + {len(etf_fetched)} ETFs), "
                      f"{prices.shape[0]} days ({dates[0]} → {dates[-1]})[/]")
        SAFE_HAVENS = _build_india_safe_havens(fetched)
        console.print(f"[dim]India safe havens: {len(SAFE_HAVENS)} tickers (debt/gold/silver)[/]")
        earn_mom = None
    else:
        cfg = MarketConfig(
            portfolio_value=PORTFOLIO_VALUE, commission_per_share=IBKR_COMMISSION_PER_SHARE,
            min_commission=IBKR_MIN_COMMISSION, avg_share_price=AVG_SHARE_PRICE,
            half_spread_bps=HALF_SPREAD_BPS, tax_rate=CCORP_TAX_RATE,
            sec_finra_fee=SEC_FINRA_FEE_PER_SHARE,
            label=f"US (IBKR C-Corp, ${PORTFOLIO_VALUE/1000:.0f}K)",
        )

        console.print(f"[bold]Fetching {len(TICKERS)} tickers ({period})...[/]")
        prices, dates, fetched = fetch_all_numpy(TICKERS, period)
        console.print(f"[green]Got {len(fetched)} tickers, {prices.shape[0]} days ({dates[0]} → {dates[-1]})[/]")

        console.print("[bold]Fetching earnings...[/]")
        earnings = fetch_all_earnings(fetched)
        console.print(f"[green]Earnings for {len(earnings)}/{len(fetched)} tickers[/]")
        earn_mom = build_earnings_momentum(earnings, dates, fetched)

    # Apply cost config to globals (used by _compute_rebalance_cost)
    PORTFOLIO_VALUE = cfg.portfolio_value
    IBKR_COMMISSION_PER_SHARE = cfg.commission_per_share
    IBKR_MIN_COMMISSION = cfg.min_commission
    AVG_SHARE_PRICE = cfg.avg_share_price
    HALF_SPREAD_BPS = cfg.half_spread_bps
    CCORP_TAX_RATE = cfg.tax_rate
    SEC_FINRA_FEE_PER_SHARE = cfg.sec_finra_fee

    return prices, dates, fetched, earn_mom, cfg


def _sweep_cache_path(market: str) -> Path:
    return Path(__file__).parent.parent / "data" / f"sweep_results_{market}.pkl"


def _save_sweep_results(results: list[WalkForwardResult], market: str) -> None:
    import pickle
    path = _sweep_cache_path(market)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(results, f, protocol=pickle.HIGHEST_PROTOCOL)
    console.print(f"[dim]Saved {len(results):,} sweep results to {path.name}[/]")


def _load_sweep_results(market: str) -> list[WalkForwardResult] | None:
    import pickle
    from datetime import datetime, timedelta
    path = _sweep_cache_path(market)
    if not path.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    if age > timedelta(hours=24):
        console.print(f"[dim]Sweep cache stale ({age.total_seconds()/3600:.1f}h old), re-running[/]")
        return None
    with open(path, "rb") as f:
        results = pickle.load(f)
    console.print(f"[green]Loaded {len(results):,} cached sweep results ({age.total_seconds()/60:.0f}m old)[/]")
    return results


@click.command()
@click.option("--top", default=20, help="Show top N results.")
@click.option("--period", default="max", help="Price history period.")
@click.option("--workers", default=4, help="Parallel workers.")
@click.option("--min-train", default=252, help="Min training days.")
@click.option("--oos-window", default=126, help="OOS test window days.")
@click.option("--max-dd-cap", default=1.0, help="MaxDD cap for survivable scenario (1.0 = no cap).")
@click.option("--market", default="us", type=click.Choice(["us", "india"]),
              help="Market: 'us' for US equities (yfinance), 'india' for MFs (mfapi.in).")
@click.option("--mc-only", is_flag=True, help="Skip sweep, reuse cached results for MC + allocation.")
def main(top: int, period: str, workers: int, min_train: int, oos_window: int,
         max_dd_cap: float, market: str, mc_only: bool):
    """Walk-forward momentum sweep — AQR + Alpha Architect signals."""
    import time as _time
    t0 = _time.monotonic()

    prices, dates, fetched, earn_mom, cfg = _load_market_data(market, period)

    folds = build_folds(prices, min_train, oos_window)
    console.print(f"[bold]{len(folds)} folds[/] ({dates[folds[0][0]]} → {dates[folds[-1][1]]})")

    from backtest_reports import (
        print_scenario_analysis, print_holdings_trace,
        print_efficient_frontier, print_portfolio_allocation,
    )

    # ── Try loading cached sweep results ──
    results = None
    if mc_only:
        results = _load_sweep_results(market)
        if results is None:
            console.print("[red]No valid sweep cache found, running full sweep[/]")

    if results is None:
        grid = build_param_grid()
        # Prune earnings profiles when no earnings data available
        if earn_mom is None:
            before = len(grid)
            grid = [p for p in grid if not p.use_earnings]
            console.print(f"[dim]Pruned {before - len(grid):,} earnings combos (no earnings data)[/]")
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

        # Determine which signals the grid actually needs
        needed_variants = {p.log_variant for p in grid}
        need_smoothness = any(p.use_smoothness for p in grid)
        need_consistency = any(p.use_consistency for p in grid)
        need_crash = any(p.use_crash_prot for p in grid)

        console.print(f"[dim]Precomputing signals at {len(all_rebal_days_sorted)} rebal dates "
                      f"({len(all_lookbacks)} lb × {len(all_skips)} sk × {len(needed_variants)} variants)...[/]")

        import time

        # ── Group by score signature, batch position/rebal variants ────────
        from collections import defaultdict

        score_groups = defaultdict(list)
        for p in grid:
            score_groups[_score_key(p)].append(p)

        n_groups = len(score_groups)
        console.print(f"[dim]{len(grid):,} combos → {n_groups:,} score groups "
                      f"(avg {len(grid)/n_groups:.0f} variants each)[/]")

        batch_args = [(params_list, folds) for params_list in score_groups.values()]

        results = []

        # Each worker precomputes its own signals (avoids pickling 630MB cache)
        console.print(f"[dim]Workers will precompute signals on init ({len(all_rebal_days_sorted)} rebal dates, "
                      f"{len(needed_variants)} variants)...[/]")

        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker,
            initargs=(prices, dates, earn_mom, fetched,
                      all_rebal_days_sorted, all_lookbacks, all_skips,
                      needed_variants, need_smoothness, need_consistency, need_crash),
        ) as pool:
            futures = {pool.submit(_worker_run_batch, a): i for i, a in enumerate(batch_args)}
            done_groups = 0

            for future in as_completed(futures):
                batch_results = future.result()
                results.extend(batch_results)
                done_groups += 1
                if done_groups % 200 == 0:
                    console.print(f"  [dim]{done_groups}/{n_groups} groups, {len(results):,} results[/]")

        console.print(f"[green]Done: {len(results):,} combos from {n_groups:,} groups[/]")
        results.sort(key=lambda r: r.oos_total_return, reverse=True)
        _save_sweep_results(results, market)

    t_sweep = _time.monotonic()
    console.print(f"[dim]Sweep phase: {t_sweep - t0:.0f}s[/]")

    survivable = print_scenario_analysis(results, folds, prices, dates, top, max_dd_cap, cfg)

    if not survivable:
        return

    if not mc_only:
        # Recompute grid-derived info needed for holdings trace
        grid = build_param_grid()
        if earn_mom is None:
            grid = [p for p in grid if not p.use_earnings]
        all_rebal_days = set()
        for oos_start, oos_end in folds:
            period_len = oos_end - oos_start
            for rf in REBAL_FREQS.values():
                for offset in range(0, period_len, rf):
                    all_rebal_days.add(oos_start + offset)
        all_rebal_days_sorted = sorted(all_rebal_days)
        all_lookbacks = sorted({p.lb_short for p in grid} | {p.lb_mid for p in grid} | {p.lb_long for p in grid} | {252})
        all_skips = sorted({p.skip for p in grid} | {0})
        needed_variants = {p.log_variant for p in grid}
        need_smoothness = any(p.use_smoothness for p in grid)
        need_consistency = any(p.use_consistency for p in grid)
        need_crash = any(p.use_crash_prot for p in grid)

        print_holdings_trace(
            survivable, prices, dates, folds, fetched, earn_mom,
            all_rebal_days_sorted, all_lookbacks, all_skips,
            needed_variants, need_smoothness, need_consistency, need_crash,
        )
    print_efficient_frontier(results, folds, fetched)

    t_mc_start = _time.monotonic()
    print_portfolio_allocation(results, prices, dates, fetched, earn_mom, cfg=cfg)
    t_mc_end = _time.monotonic()
    console.print(f"[dim]MC + allocation: {t_mc_end - t_mc_start:.0f}s[/]")
    console.print(f"[bold]Total: {t_mc_end - t0:.0f}s[/]")

    # Write results to file
    from datetime import datetime
    out_dir = Path(__file__).parent.parent / "data" / "backtest_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_file = out_dir / f"{market}_{ts}.txt"
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_scenario_analysis(results, folds, prices, dates, top, max_dd_cap, cfg)
        print_efficient_frontier(results, folds, fetched)
        print_portfolio_allocation(results, prices, dates, fetched, earn_mom, cfg=cfg)
    buf.write(f"\n--- Run completed in {t_mc_end - t0:.0f}s ({market}, {period}) ---\n")
    out_file.write_text(buf.getvalue())
    console.print(f"[dim]Results saved to {out_file}[/]")


if __name__ == "__main__":
    main()

