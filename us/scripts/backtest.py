"""
Momentum Parameter Sweep — Walk-Forward Validated, Vectorized

Signals from AQR, Alpha Architect (Wes Gray), and academic research.
All hot paths use numpy. ProcessPoolExecutor with shared-memory initializer.

Usage:
    uv run python us/scripts/backtest.py
    uv run python us/scripts/backtest.py --top 20 --period 5y
    uv run python us/scripts/backtest.py --period max --max-dd-cap 0.50
"""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import product

import click
import numpy as np
from rich.console import Console
from rich.table import Table

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_utils import fetch_all_numpy, fetch_all_earnings, build_earnings_momentum

console = Console()

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
    # Momentum: keyed by (lookback, skip, is_log) → {day: array}
    momentum_cache: dict  # {(lb, skip, log): {day: np.ndarray}}
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

    # Unique (lookback, skip, is_log) combos
    mom_keys = set()
    for lb in lookbacks:
        for skip in skips:
            mom_keys.add((lb, skip, False))  # arithmetic
            mom_keys.add((lb, skip, True))   # log

    momentum_cache = {k: {} for k in mom_keys}
    smoothness = {}
    dn_vol_cache = {}
    tv_cache = {}
    consistency_cache = {}
    abs_mom_cache = {}
    crash_cache = {}

    for day in rebal_days:
        pw = prices[:day + 1]
        n = pw.shape[0]

        # Momentum for all (lookback, skip, log) combos
        for lb, skip, is_log in mom_keys:
            if n < lb + skip:
                momentum_cache[(lb, skip, is_log)][day] = np.zeros(n_tickers)
            else:
                fn = momentum_log if is_log else momentum_arithmetic
                momentum_cache[(lb, skip, is_log)][day] = fn(pw, lb, skip)

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
    use_log_returns: bool   # Log returns instead of arithmetic
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
        if self.use_log_returns: flags.append("log")
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
    is_log = params.use_log_returns
    mc = cache.momentum_cache

    mom_s = mc.get((params.lb_short, params.skip, is_log), {}).get(day)
    mom_m = mc.get((params.lb_mid, params.skip, is_log), {}).get(day)
    mom_l = mc.get((params.lb_long, params.skip, is_log), {}).get(day)

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
                # Pick safe haven with best positive momentum
                sh_mom = cache.abs_mom_12m.get(rb_abs, np.zeros(n_tickers))
                best_sh = max(safe_indices, key=lambda i: sh_mom[i])
                weights = np.zeros(n_tickers)
                weights[best_sh] = 1.0
                position_counts.append(1)
            else:
                portfolio_value[rb_offset + 1:next_offset + 1] = portfolio_value[rb_offset]
                position_counts.append(0)
                continue
        else:
            top_n = min(params.max_positions, len(valid))
            top_idx = valid[np.argsort(scores[valid])[-top_n:]]

            # Dual momentum: redistribute weight from filtered-out positions to safe havens
            if params.use_abs_momentum and safe_indices and top_n < params.max_positions:
                # Some risky positions were filtered by abs momentum
                # Allocate their share to the best safe haven
                n_risk = top_n
                n_safe_slots = params.max_positions - n_risk
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
    ann_return = (1 + oos_total) ** (1 / n_years) - 1 if n_years > 0 else 0

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
    positions = [8, 10, 15]
    rebal_freqs = [5, 10, 21, 42, 63]

    # Signal profiles: predefined combos to avoid full cartesian explosion
    # Each profile: (sortino, smooth, earnings, log, consistency, abs_mom, vol_scl, crash)
    signal_profiles = [
        # Baseline: no signals
        (False, False, False, False, False, False, False, False),
        # Single signals (test each alone)
        (True,  False, False, False, False, False, False, False),  # sortino only
        (False, True,  False, False, False, False, False, False),  # smoothness only
        (False, False, True,  False, False, False, False, False),  # earnings only
        (False, False, False, True,  False, False, False, False),  # log returns only
        (False, False, False, False, True,  False, False, False),  # 8/12 consistency only
        (False, False, False, False, False, True,  False, False),  # dual momentum only
        (False, False, False, False, False, False, True,  False),  # vol scaling only
        (False, False, False, False, False, False, False, True),   # crash prot only
        # Best combos from prior research
        (True,  False, True,  False, False, False, False, False),  # sortino + earnings
        (False, False, True,  False, True,  False, False, False),  # earnings + 8/12
        (False, False, False, False, False, True,  True,  False),  # dual + vol_scl
        (True,  False, False, False, False, True,  False, False),  # sortino + dual
        (False, False, True,  False, False, True,  False, False),  # earnings + dual
        # AQR-inspired
        (False, False, False, False, False, False, True,  True),   # vol_scl + crash
        (True,  False, False, False, False, True,  True,  False),  # sortino + dual + vol_scl
        (True,  False, False, False, False, True,  True,  True),   # sortino + dual + vol_scl + crash
        # Alpha Architect inspired
        (True,  True,  True,  False, True,  False, False, False),  # sort + smooth + earn + 8/12
        (False, False, True,  True,  True,  True,  False, False),  # earn + log + 8/12 + dual
        # Kitchen sink
        (True,  True,  True,  True,  True,  True,  True,  True),   # everything
        (True,  False, True,  True,  True,  True,  True,  True),   # everything minus smooth
    ]

    for lb, ws, skip, profile, n_pos, rf in product(
        lookbacks, weight_schemes, skips, signal_profiles, positions, rebal_freqs
    ):
        if lb[0] <= skip:
            continue
        sort, smth, earn, log, cons, dual, vscl, crsh = profile
        configs.append(ScoringParams(
            lb_short=lb[0], lb_mid=lb[1], lb_long=lb[2],
            w_short=ws[0], w_mid=ws[1], w_long=ws[2],
            skip=skip,
            use_sortino=sort, use_smoothness=smth, use_earnings=earn,
            use_log_returns=log, use_consistency=cons,
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


@click.command()
@click.option("--top", default=20, help="Show top N results.")
@click.option("--period", default="max", help="Price history period.")
@click.option("--workers", default=11, help="Parallel workers.")
@click.option("--min-train", default=252, help="Min training days.")
@click.option("--oos-window", default=126, help="OOS test window days.")
@click.option("--max-dd-cap", default=0.50, help="MaxDD cap for survivable scenario.")
def main(top: int, period: str, workers: int, min_train: int, oos_window: int, max_dd_cap: float):
    """Walk-forward momentum sweep — AQR + Alpha Architect signals."""
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
        ("use_earnings", "earnings"), ("use_log_returns", "log-ret"),
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

    rf_counts = Counter(r.params.rebal_freq for r in top50)
    console.print(f"  rebal: {' '.join(f'{k}d={v}' for k,v in sorted(rf_counts.items()))}")
    pc = Counter(r.params.max_positions for r in top50)
    console.print(f"  positions: {' '.join(f'{k}={v}' for k,v in sorted(pc.items()))}")
    wc = Counter((r.params.w_short, r.params.w_mid, r.params.w_long) for r in top50)
    for wt, cnt in wc.most_common(3):
        console.print(f"    w={wt[0]:.1f}/{wt[1]:.1f}/{wt[2]:.1f}: {cnt}")


if __name__ == "__main__":
    main()
