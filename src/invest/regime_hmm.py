"""
Gaussian HMM regime detection for portfolio walk-forward.

Fit a Gaussian HMM on benchmark daily features (returns + rolling vol),
identify N latent states, then expose a predict_state() callable that's
look-ahead-safe (uses only data ≤ t-1 to predict state at t).

States are sorted by mean return so they're stable across refits:
  state 0 = lowest-return / highest-vol (bear)
  state N-1 = highest-return / lowest-vol (bull)

Caching: fitting is O(n × n_states²); a refit every 252 days is cheap enough.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError as e:
    raise ImportError("Install hmmlearn: `uv add hmmlearn`") from e

# Suppress hmmlearn convergence warnings — harmless for our short fits
warnings.filterwarnings("ignore", category=RuntimeWarning, module="hmmlearn")
warnings.filterwarnings("ignore", message=".*Model is not converging.*")


@dataclass
class HMMRegime:
    n_states: int = 3
    feature_window: int = 21          # days for rolling vol feature
    refit_every_days: int = 252       # refit HMM annually
    min_train_days: int = 504         # need 2y history before first fit
    _model: GaussianHMM | None = None
    _state_order: np.ndarray = field(default_factory=lambda: np.arange(0))
    _last_fit_idx: int = -1

    def _features(self, prices: np.ndarray) -> np.ndarray:
        """Return (n_days-feature_window, 2) array: [daily_log_ret, rolling_vol]."""
        p = prices[~np.isnan(prices) & (prices > 0)]
        if len(p) < self.feature_window + 5:
            return np.zeros((0, 2))
        log_rets = np.diff(np.log(p))
        # Rolling std using cumulative-sum trick
        n = len(log_rets)
        if n < self.feature_window:
            return np.zeros((0, 2))
        # Use cumulative variance for speed
        rolling_vol = np.zeros(n - self.feature_window + 1)
        for i in range(len(rolling_vol)):
            rolling_vol[i] = log_rets[i:i + self.feature_window].std()
        # Align: returns_aligned starts at feature_window-1
        returns_aligned = log_rets[self.feature_window - 1:]
        return np.column_stack([returns_aligned, rolling_vol])

    def fit(self, prices: np.ndarray) -> None:
        """Fit on the entire prices array. Call rarely (annually)."""
        X = self._features(prices)
        if len(X) < self.min_train_days:
            self._model = None
            return
        try:
            model = GaussianHMM(
                n_components=self.n_states,
                covariance_type="diag",
                n_iter=100,
                random_state=42,
                tol=1e-3,
            )
            model.fit(X)
            # Sort states by mean return (column 0): low → high
            mean_rets = model.means_[:, 0]
            self._state_order = np.argsort(mean_rets)
            self._model = model
        except Exception:
            # On singular cov / non-convergence, leave model as None
            self._model = None

    def maybe_refit(self, prices_to_idx: np.ndarray, cur_idx: int) -> None:
        """Refit if it's been >= refit_every_days since last fit."""
        if self._model is None or cur_idx - self._last_fit_idx >= self.refit_every_days:
            if cur_idx >= self.min_train_days:
                self.fit(prices_to_idx[:cur_idx])
                self._last_fit_idx = cur_idx

    def predict_state(self, recent_prices: np.ndarray) -> int:
        """Return current state in [0, n_states-1] sorted by mean return.
        Returns -1 if model not fit yet."""
        if self._model is None:
            return -1
        X = self._features(recent_prices)
        if len(X) < 5:
            return -1
        # Use forward (filtering) — only past data, no look-ahead
        try:
            posteriors = self._model.predict_proba(X)
            raw_state = int(np.argmax(posteriors[-1]))
            # Map to sorted state
            inv_order = np.argsort(self._state_order)
            return int(inv_order[raw_state])
        except Exception:
            return -1
