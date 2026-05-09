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
def _compute_scores(prices_window: np.ndarray, lookbacks, weights, skip,
                    variant: str) -> np.ndarray:
    """Per-ticker score; nan-safe; -inf for insufficient data; higher = better.

    Lightweight — does not depend on score_one's full feature set since the
    autoresearch loop sweeps multiple `variant`s and needs flexibility.
    """
    n_days, n = prices_window.shape
    scores = np.full(n, -np.inf)
    if n_days < max(lookbacks) + skip + 5:
        return scores

    end = max(n_days - skip, max(lookbacks) + 1)
    min_lb = min(lookbacks)

    for t in range(n):
        p = prices_window[:, t]
        # Survivorship-friendly: only require end + shortest lookback to be available.
        # Longer lookbacks may be NaN (newer IPO); they'll contribute 0 to wt_mom.
        if np.isnan(p[end - 1]) or end - min_lb < 0 or np.isnan(p[end - min_lb]):
            continue
        moms = []
        avail_weights = []
        for lb, w in zip(lookbacks, weights):
            start = end - lb
            if start < 0 or np.isnan(p[start]) or p[start] <= 0:
                moms.append(0.0)
                avail_weights.append(0.0)
            else:
                moms.append(p[end - 1] / p[start] - 1)
                avail_weights.append(w)
        # Renormalise weights over available lookbacks so partial-history names
        # aren't penalised vs full-history names with the same direction.
        avail_sum = sum(avail_weights)
        if avail_sum <= 0:
            continue
        wt_mom = sum((aw / avail_sum) * m for aw, m in zip(avail_weights, moms))

        rets = np.diff(p) / p[:-1]
        rets = rets[~np.isnan(rets) & np.isfinite(rets)]
        neg = rets[rets < 0]
        dn_vol = neg.std() * np.sqrt(252) if len(neg) else 1e-4

        if variant == "sortino_pricemom":
            scores[t] = wt_mom / dn_vol if dn_vol > 0 else 0
        elif variant == "sortino_vnorm":
            vol = rets.std() * np.sqrt(252) if len(rets) else 1e-4
            scores[t] = (wt_mom / vol) / dn_vol if dn_vol > 0 else 0
        elif variant == "martin":
            running_max = np.maximum.accumulate(p)
            dd = (p - running_max) / running_max
            ulcer = np.sqrt(np.mean(dd ** 2))
            scores[t] = wt_mom / max(ulcer, 1e-3)
        elif variant == "wtmf":
            signs = sum(1.0 if m > 0 else -1.0 if m < 0 else 0.0 for m in moms)
            wtmf_w = abs(signs) / 3.0
            scores[t] = (wtmf_w * wt_mom) / dn_vol if dn_vol > 0 else 0
        elif variant == "baltas":
            log_p = np.log(p[~np.isnan(p) & (p > 0)])
            if len(log_p) >= 20:
                x = np.arange(len(log_p))
                slope, _ = np.polyfit(x, log_p, 1)
                scores[t] = (slope * 252) / dn_vol if dn_vol > 0 else 0
    return scores


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
                weights = np.ones(len(current_picks)) / len(current_picks)
                days_since_last = 0
                rebal_count += 1

        seg_end = min(cur_idx + check_every, n_days)
        if current_picks:
            seg = prices[cur_idx:seg_end, current_picks].copy()
            for j in range(seg.shape[1]):
                for i in range(1, seg.shape[0]):
                    if np.isnan(seg[i, j]):
                        seg[i, j] = seg[i - 1, j]
            if not np.isnan(seg[0]).any():
                normed = seg / seg[0]
                port = (normed * weights).sum(axis=1)
                last = portfolio_values[-1]
                portfolio_values.extend([last * v for v in port])
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
    return {"sortino": float(sortino), "calmar": float(calmar),
            "max_dd": max_dd, "cagr": float(cagr),
            "rebal_count": rebal_count,
            "avg_hold": float(np.mean(holds)) if holds else 0.0}


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
    rng = np.random.default_rng(seed)
    n_hist = daily_rets.shape[0]
    p_rets = daily_rets @ weights
    idx = rng.integers(0, n_hist, size=(n_sims, days))
    sampled = p_rets[idx]

    yrs = days / 252.0
    for params in calib.values():
        if not isinstance(params, dict):
            continue
        if "annual_freq" not in params:
            continue
        p_event = min(0.99, params["annual_freq"] * yrs * p_mult)
        mag = params["magnitude"]
        dur = max(1, int(params["duration_days"]))
        hit = rng.random(n_sims) < p_event
        for i in np.where(hit)[0]:
            start = rng.integers(0, max(1, days - dur))
            end = min(days, start + dur)
            n_dd = end - start
            daily_drag = (1 + mag) ** (1 / n_dd) - 1
            sampled[i, start:end] = sampled[i, start:end] + daily_drag

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
    )


def mutate_strategy(base: Strategy, rng) -> Strategy:
    new = Strategy(**asdict(base))
    field = rng.choice([
        "lookbacks", "weights", "skip_days", "score_variant", "n_positions",
        "rebal_trigger", "rebal_min_hold", "rebal_max_hold", "rebal_jitter",
        "score_gap_pct", "max_dd_cap", "crash_p_mult",
        "regime_ma", "dd_stop_pct",
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
def composite(bt: dict, mc: dict) -> float:
    """Calmar-weighted composite: sortino × calmar² × (1 - p_dd_30).

    Squaring calmar pushes the loop hard toward strategies that earn returns
    cheaply (low MaxDD per unit CAGR). Sortino still matters for path quality.
    Tail-risk gate via stress MC keeps overfit configs out.
    """
    if bt["rebal_count"] < 3 or bt["sortino"] <= 0 or bt["calmar"] <= 0:
        return -1.0
    return bt["sortino"] * (bt["calmar"] ** 2) * (1.0 - mc["p_dd_30"])


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
