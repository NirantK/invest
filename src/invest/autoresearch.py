"""
Universe-agnostic autoresearch engine — used by both US and India strategy sweeps.

Provides:
  - Strategy dataclass + random/mutation samplers
  - walk_forward backtest (weekly trigger check, min/max hold, jitter)
  - stress_mc with EM crash injection
  - composite scoring
  - run_loop driver with greedy + random search

Wrappers under us/scripts and india/scripts pass their own universe + crash
calibration. The loop is identical otherwise.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from invest.momentum import score_one

# ─── Search space ────────────────────────────────────────────────────────────
SCORE_VARIANTS = ["sortino_pricemom", "sortino_vnorm", "martin", "wtmf", "baltas"]
LOOKBACK_CHOICES = [
    (21, 63, 252), (42, 126, 252), (63, 126, 252),
    (126, 252, 504), (252, 504, 756),
    (252, 504, 1260),  # 1Y / 2Y / 5Y — regime-spanning
    (504, 756, 1260),  # 2Y / 3Y / 5Y — multi-cycle
]
WEIGHT_CHOICES = [
    (0.7, 0.2, 0.1), (0.5, 0.3, 0.2), (0.4, 0.4, 0.2),
    (0.3, 0.3, 0.3), (0.1, 0.3, 0.6),
]
REBAL_TRIGGERS    = ["fixed", "name_change", "score_gap"]
REBAL_MIN_HOLD    = [15, 20, 25, 30]
REBAL_MAX_HOLD    = [35, 40, 50, 60, 80]
REBAL_JITTER      = [0, 3, 5, 10]
SCORE_GAP_CHOICES = [0.05, 0.10, 0.15, 0.25, 0.40]
N_POSITION_CHOICES = [3, 4, 5, 7, 10, 15]
REGIME_MA_CHOICES = [0, 100, 150, 200]   # 0 = no regime filter
DD_STOP_CHOICES   = [0.0, 0.15, 0.20, 0.30]  # 0 = no DD stop
TARGET_VOL_CHOICES = [0.0, 0.15, 0.20, 0.25, 0.30]  # 0 = no vol-targeting; else target annualised
WEIGHT_MODE_CHOICES = ["equal", "score", "sqrt_score"]
VOL_LOOKBACK_CHOICES = [21, 42, 63]  # days for realised vol estimate
# Vol-state regime scaling: classify benchmark vol as low/mid/high, scale target_vol per state
# off       — no scaling (static target_vol)
# moderate  — low: ×1.3, mid: ×1.0, high: ×0.6
# aggressive — low: ×1.6, mid: ×1.0, high: ×0.3 (defensive in high-vol regimes)
# defensive — low: ×1.0, mid: ×0.7, high: ×0.4 (asymmetric — only cuts down)
VOL_STATE_CHOICES = ["off", "moderate", "aggressive", "defensive"]


@dataclass
class Strategy:
    lookbacks:        tuple[int, int, int]
    weights:          tuple[float, float, float]
    skip_days:        int
    score_variant:    str
    n_positions:      int
    rebal_trigger:    str
    rebal_min_hold:   int
    rebal_max_hold:   int
    rebal_jitter:     int
    score_gap_pct:    float
    max_dd_cap:       float
    crash_p_mult:     float = 1.0
    # Defensive overlays (loop discovers their value)
    regime_ma:        int = 0   # 0=off, else benchmark MA window in days; cash if below
    dd_stop_pct:      float = 0.0  # 0=off, else pause to cash if portfolio DD > this
    # Position sizing + vol targeting
    target_vol:       float = 0.0   # 0=off; else target annualised portfolio vol
    vol_lookback:     int = 42      # days for realised-vol estimate
    weight_mode:      str = "equal" # equal | score | sqrt_score
    vol_state_mode:   str = "off"   # off | moderate | aggressive | defensive

    def to_dict(self):
        d = asdict(self)
        d["lookbacks"] = list(self.lookbacks)
        d["weights"] = list(self.weights)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Strategy":
        return cls(
            lookbacks=tuple(d["lookbacks"]),
            weights=tuple(d["weights"]),
            skip_days=int(d["skip_days"]),
            score_variant=str(d["score_variant"]),
            n_positions=int(d["n_positions"]),
            rebal_trigger=str(d["rebal_trigger"]),
            rebal_min_hold=int(d["rebal_min_hold"]),
            rebal_max_hold=int(d["rebal_max_hold"]),
            rebal_jitter=int(d["rebal_jitter"]),
            score_gap_pct=float(d["score_gap_pct"]),
            max_dd_cap=float(d["max_dd_cap"]),
            crash_p_mult=float(d.get("crash_p_mult", 1.0)),
            regime_ma=int(d.get("regime_ma", 0)),
            dd_stop_pct=float(d.get("dd_stop_pct", 0.0)),
            target_vol=float(d.get("target_vol", 0.0)),
            vol_lookback=int(d.get("vol_lookback", 42)),
            weight_mode=str(d.get("weight_mode", "equal")),
            vol_state_mode=str(d.get("vol_state_mode", "off")),
        )


# ─── Default crash calibration if no JSON file present ───────────────────────
DEFAULT_CRASH_CALIBRATION = {
    "mild":          {"magnitude": -0.17, "duration_days": 80,  "annual_freq": 0.50},
    "severe":        {"magnitude": -0.35, "duration_days": 180, "annual_freq": 0.15},
    "catastrophic":  {"magnitude": -0.55, "duration_days": 360, "annual_freq": 0.04},
}


def load_crash_calibration(path: Path) -> dict:
    """Normalise the JSON schema (avg_magnitude_pct, avg_duration_pk_to_tr_months,
    annual_freq_per_market) into our internal contract."""
    if not path.exists():
        return DEFAULT_CRASH_CALIBRATION
    d = json.loads(path.read_text())
    raw = d.get("calibration", {})
    out = {}
    for bucket in ("mild", "severe", "catastrophic"):
        b = raw.get(bucket)
        if not isinstance(b, dict):
            continue
        dur_d = max(1, int(round(b.get("avg_duration_pk_to_tr_months", 6) * 21)))
        out[bucket] = {
            "magnitude":     float(b.get("avg_magnitude_pct", -20)) / 100.0,
            "duration_days": dur_d,
            "annual_freq":   float(b.get("annual_freq_per_market", 0.10)),
            "recovery_months": float(b.get("avg_recovery_months", 12)),
        }
    return out or DEFAULT_CRASH_CALIBRATION


# ─── Scoring ─────────────────────────────────────────────────────────────────
SQRT_252 = np.sqrt(252)
_MIN_DN_VOL = 1e-4


def _baltas_slopes(prices_window: np.ndarray) -> np.ndarray:
    """Per-ticker annualised log-price slope (×252). NaN-aware via masked polyfit.

    For each column we drop NaN/non-positive entries, then fit log(p) ~ a + b*t.
    Vectorised columnwise via `np.polyfit` with mask handling — falls back to
    per-ticker only for the few series with insufficient data.
    """
    n_days, n = prices_window.shape
    slopes = np.zeros(n)
    with np.errstate(invalid="ignore", divide="ignore"):
        log_p_all = np.where(prices_window > 0, np.log(prices_window), np.nan)
    # Per ticker mask + polyfit — Python loop here is unavoidable because the
    # valid index set differs per column. But this variant is one of five and
    # the rest are vectorised, so the amortised cost is small.
    x = np.arange(n_days, dtype=float)
    for t in range(n):
        col = log_p_all[:, t]
        mask = np.isfinite(col)
        if mask.sum() < 20:
            continue
        xv = x[mask]
        yv = col[mask]
        # closed-form linear regression slope
        xm = xv.mean()
        ym = yv.mean()
        denom = ((xv - xm) ** 2).sum()
        if denom <= 0:
            continue
        slopes[t] = ((xv - xm) * (yv - ym)).sum() / denom
    return slopes * 252.0


def _compute_scores(prices_window: np.ndarray, lookbacks, weights, skip,
                    variant: str) -> np.ndarray:
    """Per-ticker score; nan-safe; -inf for insufficient data; higher = better.

    Vectorised across tickers via numpy broadcasting. Identical semantics to
    the previous per-ticker loop.
    """
    n_days, n = prices_window.shape
    scores = np.full(n, -np.inf)
    if n_days < max(lookbacks) + skip + 5:
        return scores

    lbs = np.asarray(lookbacks, dtype=int)
    ws = np.asarray(weights, dtype=float)
    end = max(n_days - skip, max(lookbacks) + 1)
    min_lb = int(lbs.min())

    # End price + shortest-lookback price must be present (matches old gate).
    p_end = prices_window[end - 1, :]
    p_min = prices_window[end - min_lb, :]
    eligible = np.isfinite(p_end) & np.isfinite(p_min)
    if not eligible.any():
        return scores

    # ── Multi-lookback weighted momentum (vectorised across tickers) ──────────
    # For each lookback, ticker is "available" if start price exists and >0.
    starts = end - lbs                    # (k,)
    p_starts = prices_window[starts, :]   # (k, n)
    avail = np.isfinite(p_starts) & (p_starts > 0) & (starts >= 0)[:, None]
    safe_starts = np.where(avail, p_starts, 1.0)
    moms = np.where(avail, p_end[None, :] / safe_starts - 1.0, 0.0)  # (k, n)
    avail_w = np.where(avail, ws[:, None], 0.0)
    avail_sum = avail_w.sum(axis=0)
    eligible &= avail_sum > 0
    safe_sum = np.where(avail_sum > 0, avail_sum, 1.0)
    wt_mom = (avail_w * moms).sum(axis=0) / safe_sum  # (n,)

    # ── Daily returns matrix; downside vol per ticker (NaN-aware) ────────────
    p = prices_window
    with np.errstate(invalid="ignore", divide="ignore"):
        rets = np.diff(p, axis=0) / p[:-1, :]
    finite = np.isfinite(rets)
    rets_clean = np.where(finite, rets, 0.0)

    neg_mask = finite & (rets < 0)
    neg_count = neg_mask.sum(axis=0).astype(float)
    neg_sum = np.where(neg_mask, rets, 0.0).sum(axis=0)
    neg_mean = np.where(neg_count > 0, neg_sum / np.maximum(neg_count, 1), 0.0)
    neg_sq = np.where(neg_mask, (rets - neg_mean[None, :]) ** 2, 0.0).sum(axis=0)
    # population std (matches numpy default ddof=0 used in the old loop)
    dn_var = np.where(neg_count > 0, neg_sq / np.maximum(neg_count, 1), 0.0)
    dn_vol = np.where(neg_count > 0, np.sqrt(dn_var) * SQRT_252, _MIN_DN_VOL)
    dn_vol_safe = np.where(dn_vol > 0, dn_vol, _MIN_DN_VOL)

    base = np.zeros(n)
    if variant == "sortino_pricemom":
        base = wt_mom / dn_vol_safe
    elif variant == "sortino_vnorm":
        fin_count = finite.sum(axis=0).astype(float)
        fin_sum = rets_clean.sum(axis=0)
        fin_mean = np.where(fin_count > 0, fin_sum / np.maximum(fin_count, 1), 0.0)
        fin_sq = np.where(finite, (rets - fin_mean[None, :]) ** 2, 0.0).sum(axis=0)
        full_var = np.where(fin_count > 0, fin_sq / np.maximum(fin_count, 1), 0.0)
        full_vol = np.where(fin_count > 0, np.sqrt(full_var) * SQRT_252, _MIN_DN_VOL)
        full_vol_safe = np.where(full_vol > 0, full_vol, _MIN_DN_VOL)
        base = (wt_mom / full_vol_safe) / dn_vol_safe
    elif variant == "martin":
        # Match legacy semantics: cumulative max with NaN propagation. Tickers
        # with leading NaN end up with NaN score → eligibility mask leaves -inf
        # in the same places as the old loop's NaN scores (which are filtered
        # downstream by _topk_from_scores's isfinite gate).
        with np.errstate(invalid="ignore", divide="ignore"):
            rmax = np.maximum.accumulate(p, axis=0)
            dd = (p - rmax) / rmax
            ulcer = np.sqrt(np.mean(dd ** 2, axis=0))
        base = wt_mom / np.maximum(ulcer, 1e-3)
    elif variant == "wtmf":
        signs = np.where(avail, np.sign(moms), 0.0).sum(axis=0)
        wtmf_w = np.abs(signs) / 3.0
        base = (wtmf_w * wt_mom) / dn_vol_safe
    elif variant == "baltas":
        slopes_ann = _baltas_slopes(prices_window)
        base = slopes_ann / dn_vol_safe
    else:  # unknown variant → 0
        base = np.zeros(n)

    # When dn_vol==0 the legacy code returned 0 for sortino-flavoured variants;
    # base already evaluates to 0 there because wt_mom/EPS is finite — keep
    # the legacy gate explicit for parity:
    if variant in ("sortino_pricemom", "sortino_vnorm", "wtmf", "baltas"):
        base = np.where(dn_vol > 0, base, 0.0)

    scores = np.where(eligible, base, -np.inf)
    return scores


def _ffill_2d(arr: np.ndarray) -> np.ndarray:
    """Vectorised columnwise forward-fill of NaN."""
    mask = np.isfinite(arr)
    n_rows = arr.shape[0]
    idx = np.where(mask, np.arange(n_rows)[:, None], 0)
    np.maximum.accumulate(idx, axis=0, out=idx)
    return np.take_along_axis(arr, idx, axis=0)


def _topk_from_scores(scores, n_positions):
    valid = np.where(np.isfinite(scores) & (scores > 0))[0]
    if len(valid) == 0:
        return np.array([], dtype=int)
    order = valid[np.argsort(scores[valid])[::-1]]
    return order[:n_positions]


# ─── Walk-forward (weekly check, min/max hold, jitter) ───────────────────────
def walk_forward(prices: np.ndarray, strat: Strategy,
                 train_days: int = 252, check_every: int = 5,
                 seed_offset: int = 0) -> dict:
    rng = np.random.default_rng(42 + seed_offset)
    n_days, n = prices.shape
    min_history = max(strat.lookbacks) + strat.skip_days + 21
    start = max(min_history, train_days)
    if start >= n_days:
        return {"sortino": 0, "calmar": 0, "max_dd": 0, "cagr": 0,
                "rebal_count": 0, "avg_hold": 0}

    portfolio_values = [1.0]
    cur_idx = start
    rebal_count = 0
    holds = []
    days_since_last = 10**6
    current_picks = []
    weights = np.array([])
    in_cash_until = -1  # absolute cur_idx; if > cur_idx, force cash

    # Optional regime benchmark = equal-weight all-name proxy
    benchmark = np.nanmean(prices, axis=1) if strat.regime_ma else None

    while cur_idx < n_days:
        # Defensive overlays
        regime_off = False
        if benchmark is not None and cur_idx >= strat.regime_ma:
            ma = np.nanmean(benchmark[cur_idx - strat.regime_ma:cur_idx])
            if benchmark[cur_idx - 1] < ma:
                regime_off = True

        # DD-stop check on the realised equity curve
        if strat.dd_stop_pct > 0 and len(portfolio_values) > 1:
            pv_arr = np.array(portfolio_values)
            current_dd = (pv_arr[-1] / pv_arr.max()) - 1.0
            if current_dd <= -strat.dd_stop_pct and in_cash_until < cur_idx:
                in_cash_until = cur_idx + max(strat.rebal_max_hold, 60)

        force_cash = regime_off or (cur_idx < in_cash_until)

        win_depth = max(train_days, max(strat.lookbacks) + strat.skip_days + 5)
        window = prices[max(0, cur_idx - win_depth):cur_idx, :]
        scores = _compute_scores(window, strat.lookbacks, strat.weights,
                                  strat.skip_days, strat.score_variant)
        topk = _topk_from_scores(scores, strat.n_positions)

        if force_cash:
            do_rebal = bool(current_picks)  # exit positions
        elif not current_picks:
            do_rebal = (len(topk) > 0)
        else:
            do_rebal = _should_rebal(strat, current_picks, topk, scores,
                                      days_since_last, rng)

        if do_rebal:
            if force_cash:
                if rebal_count > 0 and current_picks:
                    holds.append(days_since_last)
                current_picks = []
                weights = np.array([])
                days_since_last = 0
            elif len(topk):
                if rebal_count > 0:
                    holds.append(days_since_last)
                current_picks = list(topk)
                # Position sizing
                k = len(current_picks)
                if strat.weight_mode == "equal" or k == 0:
                    weights = np.ones(k) / max(k, 1)
                else:
                    raw = np.maximum(scores[current_picks], 1e-6)
                    if strat.weight_mode == "sqrt_score":
                        raw = np.sqrt(raw)
                    weights = raw / raw.sum()
                # Vol targeting: scale gross exposure to hit target portfolio vol
                if strat.target_vol > 0 and cur_idx > strat.vol_lookback + 5:
                    vw = prices[cur_idx - strat.vol_lookback:cur_idx, current_picks]
                    vw = _ffill_2d(vw.copy())
                    if not np.isnan(vw).any():
                        vrets = np.diff(vw, axis=0) / vw[:-1, :]
                        port_rets = vrets @ weights
                        realised_vol = port_rets.std() * SQRT_252
                        if realised_vol > 1e-4:
                            scale = min(1.5, strat.target_vol / realised_vol)
                            weights = weights * scale
                days_since_last = 0
                rebal_count += 1

        seg_end = min(cur_idx + check_every, n_days)
        if current_picks:
            # Use prior bar so the first segment day produces a return, not a price-jump.
            anchor = max(0, cur_idx - 1)
            seg = prices[anchor:seg_end, current_picks].copy()
            seg = _ffill_2d(seg)
            if not np.isnan(seg).any() and seg.shape[0] >= 2:
                # Weighted daily returns (weights may sum >1 = leverage, <1 = cash drag)
                drets = np.diff(seg, axis=0) / seg[:-1, :]
                basket_rets = drets @ weights        # (seg_days,)
                last = portfolio_values[-1]
                pv_seg = last * np.cumprod(1.0 + basket_rets)
                portfolio_values.extend(pv_seg.tolist())
            else:
                portfolio_values.extend([portfolio_values[-1]] * (seg_end - cur_idx))
        else:
            portfolio_values.extend([portfolio_values[-1]] * (seg_end - cur_idx))
        days_since_last += seg_end - cur_idx
        cur_idx = seg_end

    pv = np.array(portfolio_values)
    if len(pv) < 2:
        return {"sortino": 0, "calmar": 0, "max_dd": 0, "cagr": 0,
                "rebal_count": 0, "avg_hold": 0}
    rets = np.diff(pv) / pv[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) == 0:
        return {"sortino": 0, "calmar": 0, "max_dd": 0, "cagr": 0,
                "rebal_count": 0, "avg_hold": 0}
    cagr = (pv[-1] / pv[0]) ** (252 / len(pv)) - 1
    rmax = np.maximum.accumulate(pv)
    dd = (pv - rmax) / rmax
    max_dd = float(dd.min())
    neg = rets[rets < 0]
    dn_vol = neg.std() * np.sqrt(252) if len(neg) else 1e-4
    sortino = (rets.mean() * 252) / dn_vol if dn_vol > 0 else 0
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0

    # ── Drawdown DURATION (the pain that matters) ──────────────────────────
    # Run-length of consecutive days underwater. Convert to months (≈21d).
    in_dd = dd < -0.005  # >0.5% DD threshold to ignore noise
    runs = []
    cur = 0
    for v in in_dd:
        if v:
            cur += 1
        elif cur > 0:
            runs.append(cur)
            cur = 0
    if cur > 0:  # path ended underwater — open run
        runs.append(cur)
    max_dd_dur_days = max(runs) if runs else 0
    avg_dd_dur_days = float(np.mean(runs)) if runs else 0.0
    n_dd_episodes = len(runs)

    # Ulcer Index = sqrt(mean(DD²)) — depth² × time, depth-biased
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    martin = cagr / max(ulcer, 1e-3)

    # Pain Index = mean(|DD|) — area between curve and HWM, divided by time.
    # Becker & Moore (Zephyr Assoc., ~mid-2000s); R PerformanceAnalytics::PainIndex.
    # Linear in both depth and duration → matches "5% DD × 24mo > 20% DD × 3mo".
    pain_index = float(np.abs(dd).mean())
    pain_ratio = cagr / max(pain_index, 1e-4)

    return {"sortino": float(sortino), "calmar": float(calmar),
            "max_dd": max_dd, "cagr": float(cagr),
            "rebal_count": rebal_count,
            "avg_hold": float(np.mean(holds)) if holds else 0.0,
            "max_dd_dur_days":   int(max_dd_dur_days),
            "max_dd_dur_months": max_dd_dur_days / 21.0,
            "avg_dd_dur_days":   avg_dd_dur_days,
            "avg_dd_dur_months": avg_dd_dur_days / 21.0,
            "n_dd_episodes":     n_dd_episodes,
            "ulcer":             ulcer,
            "martin":            float(martin),
            "pain_index":        pain_index,
            "pain_ratio":        float(pain_ratio)}


def _should_rebal(strat, current_picks, new_topk, scores, days_since_last, rng):
    if days_since_last < strat.rebal_min_hold:
        return False
    jitter = rng.integers(-strat.rebal_jitter, strat.rebal_jitter + 1) if strat.rebal_jitter else 0
    if days_since_last >= strat.rebal_max_hold + jitter:
        return True
    if strat.rebal_trigger == "fixed":
        return False
    if strat.rebal_trigger == "name_change":
        return set(new_topk) != set(current_picks)
    if strat.rebal_trigger == "score_gap":
        incumbent = set(current_picks)
        challengers = [i for i in new_topk if i not in incumbent]
        for ch in challengers:
            ch_score = scores[ch]
            for inc in current_picks:
                if scores[inc] > 0 and ch_score >= scores[inc] * (1 + strat.score_gap_pct):
                    return True
    return False


# ─── Stress MC with crash injection ──────────────────────────────────────────
def stress_mc(daily_rets: np.ndarray, weights: np.ndarray, days: int,
              n_sims: int, calib: dict, p_mult: float = 1.0,
              seed: int = 42) -> dict:
    """Bootstrap MC with per-bucket crash injection. Fully vectorised."""
    rng = np.random.default_rng(seed)
    n_hist = daily_rets.shape[0]
    p_rets = daily_rets @ weights
    idx = rng.integers(0, n_hist, size=(n_sims, days))
    sampled = p_rets[idx].astype(float, copy=True)

    yrs = days / 252.0
    day_arange = np.arange(days)

    for params in calib.values():
        if not isinstance(params, dict) or "annual_freq" not in params:
            continue
        p_event = min(0.99, params["annual_freq"] * yrs * p_mult)
        mag = params["magnitude"]
        dur = max(1, int(params["duration_days"]))
        hit = rng.random(n_sims) < p_event
        if not hit.any():
            continue
        n_hit = int(hit.sum())
        max_start = max(1, days - dur)
        starts = rng.integers(0, max_start, size=n_hit)  # (n_hit,)
        ends = np.minimum(days, starts + dur)
        n_dd = ends - starts                              # (n_hit,)
        daily_drag = (1 + mag) ** (1.0 / n_dd) - 1.0      # (n_hit,)

        # Build (n_hit, days) injection matrix via broadcasting; one row per crash.
        in_window = (day_arange[None, :] >= starts[:, None]) & \
                    (day_arange[None, :] < ends[:, None])
        # daily_drag broadcast to row-wise scaling
        injection = in_window * daily_drag[:, None]

        hit_idx = np.where(hit)[0]
        sampled[hit_idx] += injection

    paths = np.cumprod(1.0 + sampled, axis=1)
    cum = paths[:, -1] - 1.0
    rmax = np.maximum.accumulate(paths, axis=1)
    dd = ((paths - rmax) / rmax).min(axis=1)
    return {
        "p5":  float(np.percentile(cum, 5)),
        "p25": float(np.percentile(cum, 25)),
        "p50": float(np.percentile(cum, 50)),
        "p75": float(np.percentile(cum, 75)),
        "p95": float(np.percentile(cum, 95)),
        "dd_wst":     float(np.percentile(dd, 5)),
        "p_loss":     float(np.mean(cum < 0)),
        "p_dd_30":    float(np.mean(dd < -0.30)),
        "p_dd_50":    float(np.mean(dd < -0.50)),
    }


# ─── Strategy samplers ───────────────────────────────────────────────────────
def random_strategy(rng) -> Strategy:
    min_h = int(rng.choice(REBAL_MIN_HOLD))
    max_h_choices = [m for m in REBAL_MAX_HOLD if m > min_h]
    max_h = int(rng.choice(max_h_choices))
    return Strategy(
        lookbacks=LOOKBACK_CHOICES[rng.integers(len(LOOKBACK_CHOICES))],
        weights=WEIGHT_CHOICES[rng.integers(len(WEIGHT_CHOICES))],
        skip_days=int(rng.choice([0, 21])),
        score_variant=str(rng.choice(SCORE_VARIANTS)),
        n_positions=int(rng.choice(N_POSITION_CHOICES)),
        rebal_trigger=str(rng.choice(REBAL_TRIGGERS)),
        rebal_min_hold=min_h,
        rebal_max_hold=max_h,
        rebal_jitter=int(rng.choice(REBAL_JITTER)),
        score_gap_pct=float(rng.choice(SCORE_GAP_CHOICES)),
        max_dd_cap=float(rng.choice([0.30, 0.50, 0.75])),
        crash_p_mult=float(rng.choice([0.5, 1.0, 2.0])),
        regime_ma=int(rng.choice(REGIME_MA_CHOICES)),
        dd_stop_pct=float(rng.choice(DD_STOP_CHOICES)),
        target_vol=float(rng.choice(TARGET_VOL_CHOICES)),
        vol_lookback=int(rng.choice(VOL_LOOKBACK_CHOICES)),
        weight_mode=str(rng.choice(WEIGHT_MODE_CHOICES)),
        vol_state_mode=str(rng.choice(VOL_STATE_CHOICES)),
    )


def mutate_strategy(base: Strategy, rng) -> Strategy:
    new = Strategy(**asdict(base))
    field = rng.choice([
        "lookbacks", "weights", "skip_days", "score_variant", "n_positions",
        "rebal_trigger", "rebal_min_hold", "rebal_max_hold", "rebal_jitter",
        "score_gap_pct", "max_dd_cap", "crash_p_mult",
        "regime_ma", "dd_stop_pct",
        "target_vol", "vol_lookback", "weight_mode", "vol_state_mode",
    ])
    if field == "lookbacks":
        new.lookbacks = LOOKBACK_CHOICES[rng.integers(len(LOOKBACK_CHOICES))]
    elif field == "weights":
        new.weights = WEIGHT_CHOICES[rng.integers(len(WEIGHT_CHOICES))]
    elif field == "skip_days":
        new.skip_days = int(rng.choice([0, 21]))
    elif field == "score_variant":
        new.score_variant = str(rng.choice(SCORE_VARIANTS))
    elif field == "n_positions":
        new.n_positions = int(rng.choice(N_POSITION_CHOICES))
    elif field == "regime_ma":
        new.regime_ma = int(rng.choice(REGIME_MA_CHOICES))
    elif field == "dd_stop_pct":
        new.dd_stop_pct = float(rng.choice(DD_STOP_CHOICES))
    elif field == "target_vol":
        new.target_vol = float(rng.choice(TARGET_VOL_CHOICES))
    elif field == "vol_lookback":
        new.vol_lookback = int(rng.choice(VOL_LOOKBACK_CHOICES))
    elif field == "weight_mode":
        new.weight_mode = str(rng.choice(WEIGHT_MODE_CHOICES))
    elif field == "rebal_trigger":
        new.rebal_trigger = str(rng.choice(REBAL_TRIGGERS))
    elif field == "rebal_min_hold":
        new.rebal_min_hold = int(rng.choice(REBAL_MIN_HOLD))
    elif field == "rebal_max_hold":
        new.rebal_max_hold = int(rng.choice(REBAL_MAX_HOLD))
    elif field == "rebal_jitter":
        new.rebal_jitter = int(rng.choice(REBAL_JITTER))
    elif field == "score_gap_pct":
        new.score_gap_pct = float(rng.choice(SCORE_GAP_CHOICES))
    elif field == "max_dd_cap":
        new.max_dd_cap = float(rng.choice([0.30, 0.50, 0.75]))
    elif field == "crash_p_mult":
        new.crash_p_mult = float(rng.choice([0.5, 1.0, 2.0]))
    if new.rebal_min_hold >= new.rebal_max_hold:
        new.rebal_max_hold = new.rebal_min_hold + 20
    return new


# ─── Composite + helpers ─────────────────────────────────────────────────────
def _duration_penalty(months: float) -> float:
    """Pain penalty as a function of TIME UNDERWATER (months).

    Calibrated to user feedback (memory: feedback_dd_duration_not_depth):
      < 6 months   → 0% penalty (sharp DDs are fine; rebal hill-climbs out)
      6–18 months  → linear 0%→50% penalty
      18–24 months → linear 50%→90% penalty
      > 24 months  → 95%+ penalty (essentially disqualifying)
    Returns multiplier in [0.05, 1.0] (higher = better).
    """
    if months <= 6:
        return 1.0
    if months <= 18:
        return 1.0 - 0.5 * (months - 6) / 12.0       # 1.0 → 0.5
    if months <= 24:
        return 0.5 - 0.4 * (months - 18) / 6.0       # 0.5 → 0.1
    return 0.05


def _underwater_penalty(max_dd_months: float) -> float:
    """Steep but smooth penalty for max underwater duration.
       <12mo  → 1.00
       18mo   → 0.70
       24mo   → 0.40   (user said "24mo+ is unacceptable")
       30mo   → 0.15
       36mo+  → 0.03
    """
    if max_dd_months <= 12:
        return 1.0
    if max_dd_months <= 24:
        return 1.0 - 0.6 * (max_dd_months - 12) / 12.0
    if max_dd_months <= 36:
        return 0.4 - 0.37 * (max_dd_months - 24) / 12.0
    return 0.03


def _nerve_penalty(max_dd_pct: float, max_dd_months: float) -> float:
    """Product (depth × years) penalty calibrated to user's stated breaking point.
       50% × 12mo = 0.50 → penalty 0.50
       50% × 6mo  = 0.25 → penalty 0.85
       40% × 2mo  = 0.067 → penalty ~1.0 (sharp DDs OK)
       20% × 24mo = 0.40 → penalty 0.65
    """
    product = max_dd_pct * (max_dd_months / 12.0)
    if product <= 0.10:
        return 1.0
    if product <= 0.50:
        return 1.0 - 0.5 * (product - 0.10) / 0.40   # → 0.50
    if product <= 0.80:
        return 0.5 - 0.45 * (product - 0.50) / 0.30  # → 0.05
    return 0.05


def composite(bt: dict, mc: dict) -> float:
    """Pain Ratio (Becker) with smooth duration + nerve penalties.

    Primary signal: pain_ratio = CAGR / mean(|DD|). Linear in depth and time, so
    "5% × 24mo > 20% × 3mo" pricing matches user's framing.

    Multiplied by:
      _underwater_penalty(max_dd_dur_months)  — discourages >24mo stretches
      _nerve_penalty(max_dd, max_dd_months)   — calibrated to "50% × 12mo = breaking point"
      (1 - p_dd_50_in_MC)                     — tail-risk gate from stress MC
    """
    if bt["rebal_count"] < 3 or bt.get("cagr", 0) <= 0:
        return -1.0

    pain_ratio = bt.get("pain_ratio", 0.0)
    if pain_ratio <= 0:
        return -1.0

    uw_pen   = _underwater_penalty(bt.get("max_dd_dur_months", 0))
    nerve_pen = _nerve_penalty(abs(bt.get("max_dd", 0)),
                                bt.get("max_dd_dur_months", 0))
    tail_pen = 1.0 - mc.get("p_dd_50", 0)
    return pain_ratio * uw_pen * nerve_pen * tail_pen


def current_picks(prices: np.ndarray, fetched: list[str], strat: Strategy) -> list[str]:
    scores = _compute_scores(prices, strat.lookbacks, strat.weights,
                              strat.skip_days, strat.score_variant)
    topk = _topk_from_scores(scores, strat.n_positions)
    return [fetched[i] for i in topk]


def evaluate(strat: Strategy, prices: np.ndarray, fetched: list[str],
             daily_rets: np.ndarray, calib: dict, seed: int = 42) -> tuple:
    bt = walk_forward(prices, strat)
    picks = current_picks(prices, fetched, strat)
    if not picks or bt["rebal_count"] < 3:
        mc = {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0,
              "dd_wst": 0, "p_loss": 0, "p_dd_30": 0, "p_dd_50": 0}
        score = -1.0
    else:
        pick_idx = [fetched.index(p) for p in picks]
        w = np.ones(len(pick_idx)) / len(pick_idx)
        sub_rets = daily_rets[:, pick_idx]
        mc = stress_mc(sub_rets, w, days=252, n_sims=2000,
                       calib=calib, p_mult=strat.crash_p_mult, seed=seed)
        score = composite(bt, mc)
    return bt, mc, picks, score


# ─── Main loop ───────────────────────────────────────────────────────────────
def run_loop(prices: np.ndarray, fetched: list[str], dates: np.ndarray,
             calib: dict, *, n_iters: int, log_path: Path, best_path: Path,
             seed: int = 42, print_every: int = 25,
             pending_provider=None, batch_callback=None,
             batch_size: int = 0) -> dict:
    """Universal loop. pending_provider/batch_callback/batch_size enable karpathy mode.

    pending_provider: optional list[Strategy] consumed first before random/greedy
    batch_callback(it, top, bottom) -> list[Strategy] new candidates after each batch
    """
    rng = np.random.default_rng(seed)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.unlink(missing_ok=True)

    daily_rets = np.diff(prices, axis=0) / prices[:-1, :]
    daily_rets = np.nan_to_num(daily_rets, nan=0.0, posinf=0.0, neginf=0.0)

    pending = list(pending_provider) if pending_provider else []
    best = None
    best_score = -np.inf
    t0 = time.time()
    log_f = open(log_path, "a")

    for it in range(1, n_iters + 1):
        if pending:
            strat = pending.pop(0)
            origin = "karpathy"
        elif best is None or rng.random() < 0.30:
            strat = random_strategy(rng)
            origin = "random"
        else:
            base = best["strategy"]
            if isinstance(base, dict):
                base = Strategy.from_dict(base)
            strat = mutate_strategy(base, rng)
            origin = "greedy"

        bt, mc, picks, score = evaluate(strat, prices, fetched, daily_rets,
                                         calib, seed)
        rec = {
            "iter": it, "origin": origin,
            "strategy": strat.to_dict(),
            "backtest": bt, "mc12m": mc,
            "score": float(score), "picks": picks,
        }
        log_f.write(json.dumps(rec) + "\n")
        log_f.flush()

        if score > best_score:
            best_score = score
            best = {**rec, "strategy": strat}
            best_path.write_text(json.dumps(rec, indent=2))
            print(f"[{it:5d}] NEW BEST score={score:.2f}  origin={origin}  "
                  f"variant={strat.score_variant} n={strat.n_positions} "
                  f"trigger={strat.rebal_trigger} hold=[{strat.rebal_min_hold},{strat.rebal_max_hold}]")

        if it % print_every == 0:
            elapsed = time.time() - t0
            rate = it / elapsed
            print(f"[{it:5d}/{n_iters}] best={best_score:.2f} rate={rate:.1f}/s "
                  f"elapsed={elapsed/60:.1f}min")

        if batch_callback and batch_size > 0 and it % batch_size == 0 and it < n_iters:
            top, bottom = _read_top_bottom(log_path, 10, 5)
            new_strats = batch_callback(it, top, bottom)
            for s in new_strats:
                pending.append(s)

    log_f.close()
    return best


def _read_top_bottom(log_path: Path, top_n: int, bottom_n: int):
    if not log_path.exists():
        return [], []
    rows = []
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:top_n], rows[-bottom_n:][::-1]
