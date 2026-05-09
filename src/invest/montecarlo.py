"""
Shared Monte Carlo primitives: block-bootstrap, regime stress, percentiles, batched metrics.

Vectorized with numpy 2D — ~10-30x faster than per-path Python loops.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel

PERIODS_PER_YEAR = 252
EPS_ULCER = 1e-6


REGIME_SCALARS: dict[str, tuple[float | None, float]] = {
    "bull":    (None, 1.0),
    "neutral": (0.10, 1.2),
    "bear":   (-0.20, 1.5),
    "shock":  (-0.40, 2.0),
}


class Percentiles(BaseModel):
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    mean: float
    std: float

    @classmethod
    def from_array(cls, arr: np.ndarray) -> "Percentiles":
        a = np.asarray(arr)
        return cls(
            p5=float(np.percentile(a, 5)),
            p25=float(np.percentile(a, 25)),
            p50=float(np.percentile(a, 50)),
            p75=float(np.percentile(a, 75)),
            p95=float(np.percentile(a, 95)),
            mean=float(np.mean(a)),
            std=float(np.std(a)),
        )

    def to_dict(self) -> dict[str, float]:
        return self.model_dump()


def block_bootstrap(
    daily_returns: np.ndarray,
    n_paths: int,
    horizon_days: int,
    block_size: int = 10,
    seed: int = 42,
    drift_target_annual: float | None = None,
    vol_mult: float = 1.0,
) -> np.ndarray:
    """Vectorized block-bootstrap: returns (n_paths, horizon_days) of resampled returns.

    drift_target_annual: if set, additive shift on each path's mean to hit target drift.
    vol_mult: multiplicative scaling on (return - mean) — widens distribution for stress.
    """
    rng = np.random.default_rng(seed)
    n = len(daily_returns)
    if n < block_size:
        return np.zeros((n_paths, horizon_days))

    n_blocks = (horizon_days + block_size - 1) // block_size
    starts = rng.integers(0, n - block_size + 1, size=(n_paths, n_blocks))
    block_offsets = np.arange(block_size)
    indices = starts[:, :, None] + block_offsets[None, None, :]   # (paths, blocks, block)
    indices = indices.reshape(n_paths, n_blocks * block_size)[:, :horizon_days]
    out = daily_returns[indices]

    if vol_mult != 1.0:
        path_mean = out.mean(axis=1, keepdims=True)
        out = (out - path_mean) * vol_mult + path_mean

    if drift_target_annual is not None:
        target_daily = (1 + drift_target_annual) ** (1 / PERIODS_PER_YEAR) - 1
        out = out + (target_daily - out.mean())

    return out


def batched_metrics(returns_2d: np.ndarray) -> dict[str, np.ndarray]:
    """Compute CAGR, Ulcer, MaxDD, Martin for each path (row). Vectorized along axis=1."""
    eq = np.cumprod(1 + returns_2d, axis=1)
    n_days = eq.shape[1]
    n_years = n_days / PERIODS_PER_YEAR

    final = eq[:, -1]
    valid = final > 0
    cagr = np.where(valid, np.power(np.maximum(final, 1e-12), 1 / max(n_years, 1e-9)) - 1, -1.0)
    total = final - 1

    rmax = np.maximum.accumulate(eq, axis=1)
    dd = (eq - rmax) / rmax
    max_dd = dd.min(axis=1)
    ulcer = np.sqrt(np.mean(dd ** 2, axis=1))
    martin = np.where(ulcer > EPS_ULCER, cagr / np.maximum(ulcer, EPS_ULCER), 0.0)

    return dict(cagr=cagr, ulcer=ulcer, max_dd=max_dd, martin=martin, total_return=total)


def simulate_regimes(
    daily_returns: np.ndarray,
    n_paths: int,
    horizon_days: int,
    block_size: int = 10,
    seed: int = 42,
    regimes: tuple[str, ...] = ("bull", "neutral", "bear", "shock"),
) -> dict[str, dict[str, Percentiles]]:
    """Run block-bootstrap MC across all named regimes. Returns nested dict
    {regime: {metric: Percentiles}}."""
    out: dict[str, dict[str, Percentiles]] = {}
    for regime in regimes:
        drift, vol = REGIME_SCALARS[regime]
        sims = block_bootstrap(daily_returns, n_paths, horizon_days, block_size,
                                seed=seed, drift_target_annual=drift, vol_mult=vol)
        m = batched_metrics(sims)
        out[regime] = {k: Percentiles.from_array(v) for k, v in m.items()}
    return out
