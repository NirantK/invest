"""
Vectorized signal panels for momentum scoring.

Each function takes a (n_days, n_tickers) numpy panel and returns a same-shape
panel of the rolling signal. NaN for days before the signal is computable.

Replaces the per-ticker Python loop in build_scores_at — for a 162-ticker universe
× 25 rebal dates, this drops scoring from ~4s/backtest to ~500ms.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from invest.momentum import LOOKBACK_3M, LOOKBACK_6M, LOOKBACK_12M, SKIP_1M

PERIODS_PER_YEAR = 252
EPS_VOL = 1e-4
EPS_ULCER = 1e-3


def _shifted_momentum(prices: np.ndarray, lookback: int, skip: int) -> np.ndarray:
    """Vectorized momentum with skip-1M: prices[t-skip] / prices[t-skip-lookback] - 1.

    Output shape (n_days, n_tickers); NaN for days < lookback + skip.
    """
    n_days = prices.shape[0]
    out = np.full_like(prices, np.nan, dtype=float)
    end = n_days - skip
    if end <= lookback:
        return out
    end_prices = prices[lookback:end]
    start_prices = prices[:end - lookback]
    out[lookback + skip:end + skip] = end_prices / start_prices - 1
    return out


def _rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling max over `window` days, axis=0. NaN-safe (uses fmax)."""
    n_days = arr.shape[0]
    out = np.full_like(arr, np.nan, dtype=float)
    if n_days < window:
        return out
    windows = sliding_window_view(arr, window, axis=0)  # (n_days-w+1, window, n_tickers) actually (n-w+1, n_tickers, w)
    rolled = np.nanmax(windows, axis=-1)
    out[window - 1:] = rolled
    return out


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    n_days = arr.shape[0]
    out = np.full_like(arr, np.nan, dtype=float)
    if n_days < window:
        return out
    windows = sliding_window_view(arr, window, axis=0)
    out[window - 1:] = np.nanmean(windows, axis=-1)
    return out


def _rolling_dn_vol(rets: np.ndarray, window: int) -> np.ndarray:
    """Rolling annualized stdev of negative returns only."""
    n_days = rets.shape[0]
    out = np.full_like(rets, np.nan, dtype=float)
    if n_days < window:
        return out
    neg_rets = np.where(rets < 0, rets, np.nan)
    windows = sliding_window_view(neg_rets, window, axis=0)
    with np.errstate(invalid="ignore"):
        std = np.nanstd(windows, axis=-1)
    annualized = std * np.sqrt(PERIODS_PER_YEAR)
    annualized = np.where(np.isnan(annualized) | (annualized < EPS_VOL), EPS_VOL, annualized)
    out[window - 1:] = annualized
    return out


def _rolling_log_slope(arr: np.ndarray, window: int) -> np.ndarray:
    """Annualized slope of log(arr) over rolling window, via closed-form least squares."""
    n_days, n_tickers = arr.shape
    out = np.zeros_like(arr, dtype=float)
    if n_days < window:
        return out

    log_arr = np.log(np.maximum(arr, EPS_VOL))
    windows = sliding_window_view(log_arr, window, axis=0)  # (n-w+1, n_tickers, w)
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_centered = x - x_mean
    x_var = (x_centered ** 2).sum()

    y_mean = windows.mean(axis=-1, keepdims=True)
    y_centered = windows - y_mean
    cov = (y_centered * x_centered).sum(axis=-1)
    slope = cov / x_var
    out[window - 1:] = slope * PERIODS_PER_YEAR
    return out


def _rolling_quality_fip(prices: np.ndarray, rets: np.ndarray, window: int, skip: int
                         ) -> tuple[np.ndarray, np.ndarray]:
    """Rolling R² (log-price linear fit) and Frog-In-Pan (fraction positive returns).

    Computed on the [t-skip-window, t-skip] window, attached to day t.
    """
    n_days, n_tickers = prices.shape
    quality = np.full_like(prices, np.nan, dtype=float)
    fip = np.full_like(prices, np.nan, dtype=float)
    if n_days < window + skip:
        return quality, fip

    log_prices = np.log(np.maximum(prices, EPS_VOL))
    p_windows = sliding_window_view(log_prices, window, axis=0)  # (n_days-w+1, n_tickers, w)
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    x_centered = x - x_mean
    x_var = (x_centered ** 2).sum()

    y_mean = p_windows.mean(axis=-1, keepdims=True)
    y_centered = p_windows - y_mean
    slope = (y_centered * x_centered).sum(axis=-1) / x_var
    intercept = y_mean.squeeze(-1) - slope * x_mean
    fitted = slope[..., None] * x + intercept[..., None]
    ss_res = ((p_windows - fitted) ** 2).sum(axis=-1)
    ss_tot = (y_centered ** 2).sum(axis=-1)
    r2 = np.where(ss_tot > 0, 1.0 - ss_res / ss_tot, 0.0)
    r2 = np.clip(r2, 0.0, 1.0)

    r_windows = sliding_window_view(rets, window, axis=0)
    fip_w = np.mean(r_windows > 0, axis=-1)

    # Anchor to day t (where window ends at t-skip)
    target_start = window - 1 + skip
    n_valid = min(r2.shape[0], n_days - target_start)
    quality[target_start:target_start + n_valid] = r2[:n_valid]
    fip[target_start:target_start + n_valid] = fip_w[:n_valid]
    return quality, fip


def _rolling_ulcer_dd(prices: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Rolling Ulcer Index (sqrt mean DD²) and rolling max DD over window."""
    n_days, n_tickers = prices.shape
    ulcer = np.full_like(prices, np.nan, dtype=float)
    max_dd = np.full_like(prices, np.nan, dtype=float)
    if n_days < window:
        return ulcer, max_dd

    p_windows = sliding_window_view(prices, window, axis=0)  # (n-w+1, n_tickers, w)
    rmax = np.maximum.accumulate(p_windows, axis=-1)
    dd = (p_windows - rmax) / rmax
    ulcer_w = np.sqrt((dd ** 2).mean(axis=-1))
    ulcer_w = np.where(ulcer_w < EPS_ULCER, EPS_ULCER, ulcer_w)
    max_dd_w = dd.min(axis=-1)
    ulcer[window - 1:] = ulcer_w
    max_dd[window - 1:] = max_dd_w
    return ulcer, max_dd


def _current_dd_panel(prices: np.ndarray) -> np.ndarray:
    """Per-day drawdown vs full-history running max."""
    rmax = np.maximum.accumulate(prices, axis=0)
    return (prices - rmax) / rmax


def compute_signal_panels(
    prices: np.ndarray,
    closes: np.ndarray | None = None,
    dvols: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """All rolling signals as (n_days, n_tickers) panels.

    `prices` should be total-return-adjusted. `closes` is raw close (for 52WH),
    `dvols` is daily $-volume. Both optional — without them, vol_factor = high_factor = 1.
    """
    n_days = prices.shape[0]
    rets = np.full_like(prices, np.nan, dtype=float)
    rets[1:] = (prices[1:] - prices[:-1]) / prices[:-1]

    skip = SKIP_1M
    mom_3m = _shifted_momentum(prices, LOOKBACK_3M, skip)
    mom_6m = _shifted_momentum(prices, LOOKBACK_6M, skip)
    mom_12m = _shifted_momentum(prices, LOOKBACK_12M, skip)
    wt_mom = 0.2 * mom_3m + 0.4 * mom_6m + 0.4 * mom_12m

    dn_vol = _rolling_dn_vol(rets, LOOKBACK_12M)
    quality, fip = _rolling_quality_fip(prices, rets, LOOKBACK_12M, skip)
    smoothness = np.sqrt(np.maximum(quality * fip, 0.0))

    ulcer_1y, max_dd_1y = _rolling_ulcer_dd(prices, LOOKBACK_12M)
    current_dd = _current_dd_panel(prices)

    if closes is not None:
        max_252 = _rolling_max(closes, LOOKBACK_12M)
        dist52 = 1.0 - closes / np.where(max_252 > 0, max_252, np.nan)
    else:
        dist52 = np.full_like(prices, np.nan, dtype=float)

    if dvols is not None:
        dv_slope = _rolling_log_slope(dvols, LOOKBACK_3M)
        adv60 = _rolling_mean(dvols, 60)
        vol_factor = np.clip(1.0 + 0.15 * dv_slope, 0.7, 1.3)
    else:
        dv_slope = np.zeros_like(prices)
        adv60 = np.zeros_like(prices)
        vol_factor = np.ones_like(prices)

    with np.errstate(invalid="ignore"):
        high_factor = np.where(np.isnan(dist52), 1.0,
                       np.where(dist52 < 0.10, 1.10,
                       np.where(dist52 < 0.25, 1.00,
                                np.maximum(0.85, 1.00 - 0.50 * (dist52 - 0.25)))))

    martin = np.where(ulcer_1y > EPS_ULCER, wt_mom / np.maximum(ulcer_1y, EPS_ULCER), 0.0)
    score_pricemom = np.where(dn_vol > 0, wt_mom * smoothness / np.maximum(dn_vol, EPS_VOL), 0.0)
    score_sortino = score_pricemom * vol_factor * high_factor
    score_martin = martin * smoothness * vol_factor * high_factor

    return {
        "mom_3m": mom_3m, "mom_6m": mom_6m, "mom_12m": mom_12m, "wt_mom": wt_mom,
        "dn_vol": dn_vol, "quality": quality, "fip": fip, "smoothness": smoothness,
        "ulcer_1y": ulcer_1y, "max_dd_1y": max_dd_1y, "current_dd": current_dd,
        "dist52": dist52, "dv_slope": dv_slope, "adv60": adv60,
        "vol_factor": vol_factor, "high_factor": high_factor,
        "martin": martin, "score_pricemom": score_pricemom,
        "score_sortino": score_sortino, "score_martin": score_martin,
        "score": score_martin,
    }
