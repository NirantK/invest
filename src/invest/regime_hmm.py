"""
Gaussian HMM regime detection for portfolio walk-forward.

Fit a Gaussian HMM on benchmark daily features (returns + rolling vol),
identify N latent states, then expose a predict_state() callable that's
look-ahead-safe (uses only data ≤ t-1 to predict state at t).

States are sorted by **mean vol descending** so the labeling is stable across
refits AND aligned with intuition:
  state 0          = highest-vol (crisis / bear)
  state N-1        = lowest-vol  (calm   / bull)

Empirically: in financial regimes, high-vol clusters span both crashes (-50%)
and the violent recoveries that follow. Sorting by mean RETURN puts these
recovery rallies at "bull" — wrong, because risk is still elevated. Sorting
by VOL captures the underlying regime correctly.

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

# Module-level fit cache (process-local). Keyed on hyperparams + train fingerprint.
# Sweep often re-fits identical config across strategy iters → cuts ~70% EM cost.
_FIT_CACHE: dict = {}
_FIT_CACHE_MAX = 64

# Suppress hmmlearn convergence warnings — harmless for our short fits
warnings.filterwarnings("ignore", category=RuntimeWarning, module="hmmlearn")
warnings.filterwarnings("ignore", message=".*Model is not converging.*")


@dataclass
class HMMRegime:
    n_states: int = 3
    feature_window: int = 21          # days for rolling vol feature
    refit_every_days: int = 252       # refit HMM annually
    min_train_days: int = 504         # need 2y history before first fit
    macro_features: np.ndarray | None = None  # optional (n_days, k) macro stack
    _model: GaussianHMM | None = None
    _state_order: np.ndarray = field(default_factory=lambda: np.arange(0))
    _last_fit_idx: int = -1
    _vol_col: int = 1                 # column index used for state-sort by vol

    def _features(self, prices: np.ndarray, macro_slice: np.ndarray | None = None) -> np.ndarray:
        """Return (n_aligned, 2+k) array: [daily_log_ret, rolling_vol, *macro_features].
        macro_slice (if given) must be aligned to the prices array; trailing
        feature_window rows are dropped to match the rolling-vol alignment.
        """
        # NaN-aware filter — keep aligned indices into the original array
        valid_mask = ~np.isnan(prices) & (prices > 0)
        p = prices[valid_mask]
        if len(p) < self.feature_window + 5:
            return np.zeros((0, 2 + (macro_slice.shape[1] if macro_slice is not None else 0)))
        log_rets = np.diff(np.log(p))
        n = len(log_rets)
        if n < self.feature_window:
            return np.zeros((0, 2 + (macro_slice.shape[1] if macro_slice is not None else 0)))
        windows = np.lib.stride_tricks.sliding_window_view(log_rets, self.feature_window)
        rolling_vol = windows.std(axis=1)
        returns_aligned = log_rets[self.feature_window - 1:]
        base = np.column_stack([returns_aligned, rolling_vol])

        if macro_slice is None:
            return base
        # Align macro to base: macro has same length as `prices`. After
        # filtering valid_mask + diff(log) + sliding_window, base length =
        # len(p) - self.feature_window. Take last `len(base)` macro rows
        # corresponding to the same prices indices (approximation: tail-align).
        m = macro_slice
        if m.shape[0] >= len(base):
            m = m[-len(base):, :]
        else:
            # pad with zeros at front
            pad = np.zeros((len(base) - m.shape[0], m.shape[1]))
            m = np.vstack([pad, m])
        # Replace NaN with 0 (neutral)
        m = np.nan_to_num(m, nan=0.0, posinf=0.0, neginf=0.0)
        return np.column_stack([base, m])


    def fit(self, prices: np.ndarray, macro_slice: np.ndarray | None = None) -> None:
        X = self._features(prices, macro_slice)
        if len(X) < self.min_train_days:
            self._model = None
            return
        # Cache key: hyperparams + a cheap fingerprint of training data
        cksum = float(X[-1].sum() + X[0].sum() + len(X))
        cache_key = (self.n_states, self.feature_window, X.shape[1], len(X), cksum)
        cached = HMMRegime._FIT_CACHE.get(cache_key)
        if cached is not None:
            self._model, self._state_order = cached
            return
        try:
            model = GaussianHMM(
                n_components=self.n_states,
                covariance_type="diag",
                n_iter=30,
                random_state=42,
                tol=1e-3,
            )
            model.fit(X)
            mean_vols = model.means_[:, self._vol_col]
            order = np.argsort(mean_vols)[::-1]
            self._model = model
            self._state_order = order
            # LRU-evict if over budget
            if len(HMMRegime._FIT_CACHE) >= HMMRegime._FIT_CACHE_MAX:
                HMMRegime._FIT_CACHE.pop(next(iter(HMMRegime._FIT_CACHE)))
            HMMRegime._FIT_CACHE[cache_key] = (model, order)
        except Exception:
            self._model = None

    def maybe_refit(self, prices_to_idx: np.ndarray, cur_idx: int) -> None:
        """Refit if it's been >= refit_every_days since last fit. If
        macro_features is set on the dataclass, slice it to cur_idx."""
        if self._model is None or cur_idx - self._last_fit_idx >= self.refit_every_days:
            if cur_idx >= self.min_train_days:
                macro_slice = (
                    self.macro_features[:cur_idx, :]
                    if self.macro_features is not None else None
                )
                self.fit(prices_to_idx[:cur_idx], macro_slice=macro_slice)
                self._last_fit_idx = cur_idx

    def predict_state(self, recent_prices: np.ndarray, recent_macro: np.ndarray | None = None) -> int:
        """Return current state in [0, n_states-1] sorted by mean vol descending.
        Returns -1 if model not fit yet."""
        if self._model is None:
            return -1
        X = self._features(recent_prices, recent_macro)
        if len(X) < 5:
            return -1
        # If feature dim doesn't match the trained model, drop macro slice
        if X.shape[1] != self._model.n_features:
            X = X[:, : self._model.n_features]
        # Use forward (filtering) — only past data, no look-ahead
        try:
            posteriors = self._model.predict_proba(X)
            raw_state = int(np.argmax(posteriors[-1]))
            # Map to sorted state
            inv_order = np.argsort(self._state_order)
            return int(inv_order[raw_state])
        except Exception:
            return -1
