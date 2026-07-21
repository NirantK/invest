"""Short-window momentum scorer for tactical 3-month sleeves.

No skip-1M (we want recent acceleration, not the 12-1 academic signal).
Lookbacks: 5d (1W), 10d (2W), 20d (4W), 40d (8W).

Vectorized: precompute_scores(prices) → (n_days, n_tick) arrays for every
score variant, plus a (n_days,) breadth signal. Cheap enough to run over
4500-day × 162-ticker matrices in a few seconds.
"""

from __future__ import annotations

import numpy as np

LB_1W = 5
LB_2W = 10
LB_4W = 20
LB_8W = 40

SCORE_VARIANTS = (
    "score_1w", "score_2w", "score_4w", "score_8w",
    "score_eq", "score_tilt", "score_sortino",
)


def _rolling_smoothness_dnvol(
    prices: np.ndarray, returns: np.ndarray, lookback: int = LB_8W
) -> tuple[np.ndarray, np.ndarray]:
    """Rolling smoothness = sqrt(R² × FIP) and downside vol over `lookback` window.

    prices  shape (n_days, n_tick)  forward-filled, no NaN beyond ticker IPO
    returns shape (n_days-1, n_tick)  returns[t-1, j] = ret of day t

    Both outputs shape (n_days, n_tick), NaN where window not available.
    """
    n_days, n_tick = prices.shape
    smoothness = np.full((n_days, n_tick), np.nan)
    dn_vol = np.full((n_days, n_tick), np.nan)
    sqrt_252 = float(np.sqrt(252))
    x = np.arange(lookback, dtype=float)
    x_mean = x.mean()
    x_dev = x - x_mean
    ss_xx = float((x_dev ** 2).sum())

    for t in range(lookback, n_days):
        # Returns window: returns rows [t-lookback : t] correspond to days t-lookback+1..t
        w_rets = returns[t - lookback : t]
        # Downside vol: std of negative returns only
        neg_mask = w_rets < 0
        neg_count = neg_mask.sum(axis=0)
        zero_filled = np.where(neg_mask, w_rets, 0.0)
        neg_sum = zero_filled.sum(axis=0)
        neg_sqsum = (zero_filled ** 2).sum(axis=0)
        safe_count = np.clip(neg_count, 1, None)
        neg_mean = neg_sum / safe_count
        neg_var = np.clip(neg_sqsum / safe_count - neg_mean ** 2, 0, None)
        dnv = np.sqrt(neg_var) * sqrt_252
        dn_vol[t] = np.where(neg_count > 0, dnv, 1e-4)

        # Smoothness over price window (length=lookback). Use prices[t-lookback+1:t+1].
        w_p = prices[t - lookback + 1 : t + 1]
        valid_mask = np.isfinite(w_p).all(axis=0) & (w_p > 0).all(axis=0)
        if not valid_mask.any():
            continue
        log_p = np.full(w_p.shape, np.nan)
        log_p[:, valid_mask] = np.log(w_p[:, valid_mask])
        y_mean = log_p.mean(axis=0)
        y_dev = log_p - y_mean
        ss_xy = (x_dev[:, None] * y_dev).sum(axis=0)
        slope = np.where(ss_xx > 0, ss_xy / ss_xx, 0.0)
        intercept = y_mean - slope * x_mean
        fitted = slope * x[:, None] + intercept
        ss_res = ((log_p - fitted) ** 2).sum(axis=0)
        ss_tot = (y_dev ** 2).sum(axis=0)
        r2 = np.where(ss_tot > 0, np.clip(1 - ss_res / ss_tot, 0, None), 0.0)
        # FIP from returns window
        fip = (w_rets > 0).mean(axis=0)
        smoothness[t] = np.sqrt(np.clip(r2 * fip, 0, None))

    return smoothness, dn_vol


def precompute_scores(
    prices: np.ndarray,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Compute all score variants + breadth signal.

    prices shape (n_days, n_tick) forward-filled.

    Returns:
      scores: {name: (n_days, n_tick) array}
      breadth: (n_days,) fraction of universe with positive 4W momentum
    """
    n_days, n_tick = prices.shape
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(prices, axis=0) / prices[:-1]

    def mom_window(lb: int) -> np.ndarray:
        m = np.full((n_days, n_tick), np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            m[lb:] = prices[lb:] / prices[:-lb] - 1
        return m

    m1w = mom_window(LB_1W)
    m2w = mom_window(LB_2W)
    m4w = mom_window(LB_4W)
    m8w = mom_window(LB_8W)

    eq = (m1w + m2w + m4w + m8w) / 4
    tilt = 0.4 * m1w + 0.3 * m2w + 0.2 * m4w + 0.1 * m8w

    smoothness, dn_vol = _rolling_smoothness_dnvol(prices, rets, LB_8W)
    with np.errstate(divide="ignore", invalid="ignore"):
        sortino = (tilt * smoothness) / dn_vol

    scores = {
        "score_1w": m1w, "score_2w": m2w, "score_4w": m4w, "score_8w": m8w,
        "score_eq": eq, "score_tilt": tilt, "score_sortino": sortino,
    }

    valid = np.isfinite(m4w)
    pos = (m4w > 0) & valid
    valid_count = np.clip(valid.sum(axis=1), 1, None)
    breadth = pos.sum(axis=1) / valid_count

    return scores, breadth
