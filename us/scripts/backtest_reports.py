"""Reporting functions for backtest.py — LLM-parseable markdown + xml output."""

import json as _json
from collections import Counter, defaultdict
from pathlib import Path

import httpx as _hx
import numpy as np

import backtest as backtest_engine
from backtest import (
    MarketConfig,
    WalkForwardResult,
    precompute_signals,
    score_from_cache,
)

# ── MF name resolution (shared across all report functions) ──────────────────

_MF_NAMES_FILE = Path(__file__).parent.parent / "data" / "mf_scheme_names.json"
_MF_NAME_CACHE: dict[str, str] = {}
if _MF_NAMES_FILE.exists():
    _MF_NAME_CACHE = _json.loads(_MF_NAMES_FILE.read_text())


def _resolve_name(ticker_id: str) -> str:
    """Resolve ticker ID to human-readable name. Caches MF lookups."""
    if ticker_id in _MF_NAME_CACHE:
        return _MF_NAME_CACHE[ticker_id]
    # ETF tickers: strip .NS suffix
    if not ticker_id.isdigit():
        name = ticker_id.replace(".NS", "")
        _MF_NAME_CACHE[ticker_id] = name
        return name
    # MF scheme code: look up from mfapi.in
    resp = _hx.get(f"https://api.mfapi.in/mf/{ticker_id}", timeout=5)
    if resp.status_code == 200:
        name = resp.json().get("meta", {}).get("scheme_name", ticker_id)
        for drop in [" - Direct Plan", " Direct Plan", "-Direct Plan",
                     " - Growth Option", " - Growth", "-Growth",
                     " Growth", " Option", " Fund"]:
            name = name.replace(drop, "")
        _MF_NAME_CACHE[ticker_id] = name[:45]
    return _MF_NAME_CACHE.get(ticker_id, ticker_id)


def _save_name_cache():
    _MF_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MF_NAMES_FILE.write_text(
        _json.dumps(_MF_NAME_CACHE, indent=2, sort_keys=True)
    )


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a markdown table. Compact, parseable by LLMs."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    sep = " | ".join("-" * w for w in widths)
    hdr = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    lines = [hdr, sep]
    for row in rows:
        lines.append(" | ".join(c.ljust(w) for c, w in zip(row, widths)))
    return "\n".join(lines)


def _results_table(title: str, results: list[WalkForwardResult], limit: int) -> str:
    """Standard results table: #, OOS Ret, Ann, MaxDD, Sortino, Calmar, Win%, Pos, Params."""
    headers = ["#", "OOS Ret", "Ann.", "MaxDD", "Sortino", "Calmar", "Win%", "Pos", "Params"]
    rows = []
    for i, r in enumerate(results[:limit]):
        rows.append([
            str(i + 1),
            f"{r.oos_total_return * 100:+.1f}%",
            f"{r.oos_annualized * 100:+.1f}%",
            f"{r.oos_max_dd * 100:.1f}%",
            f"{r.oos_sortino:.2f}",
            f"{r.oos_calmar:.2f}",
            f"{r.oos_win_rate * 100:.0f}%",
            f"{r.avg_positions:.0f}",
            r.label(),
        ])
    return f"### {title}\n\n{_md_table(headers, rows)}"


def print_scenario_analysis(
    results: list[WalkForwardResult],
    folds: list[tuple[int, int]],
    prices: np.ndarray,
    dates: np.ndarray,
    top: int,
    max_dd_cap: float,
    cfg: MarketConfig,
) -> list[WalkForwardResult]:
    """Scenarios 1-14. Returns survivable list."""

    print("<scenario-analysis>")

    # 1. YOLO
    print(_results_table(f"YOLO: Max OOS Return ({len(folds)} folds)", results, top))

    # 2. Risk tiers
    dd_tiers = [0.30, 0.40, 0.50, 0.60, 0.75]
    rows = []
    for dd_cap in dd_tiers:
        tier = [r for r in results if abs(r.oos_max_dd) <= dd_cap]
        if tier:
            best = max(tier, key=lambda r: r.oos_annualized)
            rows.append([
                f"<={dd_cap*100:.0f}%", str(len(tier)),
                f"{best.oos_annualized*100:+.1f}%", f"{best.oos_calmar:.2f}",
                f"{best.oos_sortino:.2f}", f"{best.oos_win_rate*100:.0f}%",
                best.label(),
            ])
        else:
            rows.append([f"<={dd_cap*100:.0f}%", "0", "—", "—", "—", "—", "—"])
    print(f"\n### Risk Tiers\n\n{_md_table(['MaxDD', '#Combos', 'BestAnn', 'Calmar', 'Sortino', 'Win%', 'Config'], rows)}")

    # 3. Never lose
    never_lose = sorted(
        [r for r in results if r.oos_win_rate >= 0.90 and r.oos_annualized > 0],
        key=lambda r: r.oos_annualized, reverse=True,
    )
    print(f"\n{_results_table('Never Lose: Win >= 90%', never_lose, 10)}")

    # 4. No blowup
    no_blowup = sorted(
        [r for r in results if (min(r.fold_returns) if r.fold_returns else -1.0) > -0.20],
        key=lambda r: r.oos_annualized, reverse=True,
    )
    print(f"\n{_results_table('No Blowup: No fold > -20%', no_blowup, 10)}")

    # 5. Consistency
    consistent = sorted(
        [r for r in results if r.oos_annualized > 0.20],
        key=lambda r: r.consistency,
    )
    print(f"\n{_results_table('Consistency: Lowest Variance (Ann>20%)', consistent, 10)}")

    # 6. Efficient frontier by DD band
    dd_bands = [(0.0, 0.25), (0.25, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.70), (0.70, 1.0)]
    rows = []
    for lo, hi in dd_bands:
        band = [r for r in results if lo < abs(r.oos_max_dd) <= hi]
        if band:
            best = max(band, key=lambda r: r.oos_calmar)
            rows.append([
                f"{lo*100:.0f}-{hi*100:.0f}%", f"{best.oos_calmar:.2f}",
                f"{best.oos_annualized*100:+.1f}%", f"{best.oos_max_dd*100:.1f}%",
                f"{best.oos_sortino:.2f}", best.label(),
            ])
    print(f"\n### Efficient Frontier by DD Band\n\n{_md_table(['DD Band', 'Calmar', 'Ann.', 'MaxDD', 'Sortino', 'Config'], rows)}")

    # 7. Sleep at night
    sleep_well = sorted(
        [r for r in results if abs(r.oos_max_dd) <= 0.30 and r.oos_win_rate >= 0.85],
        key=lambda r: r.oos_annualized, reverse=True,
    )
    if sleep_well:
        print(f"\n{_results_table('Sleep at Night: DD<=30% + Win>=85%', sleep_well, 10)}")
    else:
        print("\n### Sleep at Night: No combos with DD<=30% and Win>=85%")

    # 8. Quitter's regret
    dd_cap_pct = max_dd_cap * 100
    survivable = sorted(
        [r for r in results if abs(r.oos_max_dd) <= max_dd_cap],
        key=lambda r: r.oos_total_return, reverse=True,
    )

    rows = []
    for r in survivable[:8]:
        fa = r.fold_returns
        if len(fa) < 5:
            continue
        worst_idx = int(np.argmin(fa))
        next_3 = fa[worst_idx + 1:worst_idx + 4]
        if next_3:
            recovery = float(np.prod([1 + x for x in next_3]) - 1)
            rows.append([
                r.label()[:50], f"{fa[worst_idx]*100:+.1f}%",
                f"{recovery*100:+.1f}%", f"{r.oos_annualized*100:+.1f}%",
                f"{r.oos_max_dd*100:.1f}%",
            ])
    print(f"\n### Quitter's Regret\n\n{_md_table(['Config', 'WorstFold', 'Next3Folds', 'FullAnn', 'MaxDD'], rows)}")

    # 9. Fold return percentiles
    rows = []
    for r in survivable[:5]:
        fa = np.array(r.fold_returns)
        rows.append([
            r.label()[:45],
            f"{np.percentile(fa, 10)*100:+.1f}%", f"{np.percentile(fa, 25)*100:+.1f}%",
            f"{np.percentile(fa, 50)*100:+.1f}%", f"{np.percentile(fa, 75)*100:+.1f}%",
            f"{np.percentile(fa, 90)*100:+.1f}%",
            f"{fa.min()*100:+.1f}%", f"{fa.max()*100:+.1f}%",
        ])
    print(f"\n### Fold Return Percentiles\n\n{_md_table(['Config', 'P10', 'P25', 'P50', 'P75', 'P90', 'Worst', 'Best'], rows)}")

    # 10. Streak risk
    def max_losing_streak(fold_returns: list[float]) -> int:
        streak = max_streak = 0
        for r in fold_returns:
            streak = streak + 1 if r < 0 else 0
            max_streak = max(max_streak, streak)
        return max_streak

    rows = []
    for r in survivable[:10]:
        streak = max_losing_streak(r.fold_returns)
        rows.append([r.label()[:45], f"{streak}", f"~{streak*6}mo",
                     f"{r.oos_annualized*100:+.1f}%", f"{r.oos_max_dd*100:.1f}%"])
    print(f"\n### Streak Risk\n\n{_md_table(['Config', 'MaxStreak', 'Underwater', 'Ann.', 'MaxDD'], rows)}")

    # 11. Return distribution
    all_ann = np.array([r.oos_annualized for r in results])
    all_dd = np.array([abs(r.oos_max_dd) for r in results])
    all_sortinos = np.array([r.oos_sortino for r in results])
    all_calmars = np.array([r.oos_calmar for r in results])
    pcts = [5, 10, 25, 50, 75, 90, 95]
    pct_hdrs = ["Metric"] + [f"P{p}" for p in pcts]
    dist_rows = [
        ["Ann. Return"] + [f"{np.percentile(all_ann, p)*100:+.1f}%" for p in pcts],
        ["Max DD"] + [f"{np.percentile(all_dd, p)*100:.1f}%" for p in pcts],
        ["Sortino"] + [f"{np.percentile(all_sortinos, p):.2f}" for p in pcts],
        ["Calmar"] + [f"{np.percentile(all_calmars, p):.2f}" for p in pcts],
    ]
    print(f"\n### Return Distribution ({len(results):,} combos)\n\n{_md_table(pct_hdrs, dist_rows)}")

    # 12. Survivable distribution
    if survivable:
        surv_ann = np.array([r.oos_annualized for r in survivable])
        surv_dd = np.array([abs(r.oos_max_dd) for r in survivable])
        sp = [5, 25, 50, 75, 95]
        sd_rows = [
            ["Ann. Return"] + [f"{np.percentile(surv_ann, p)*100:+.1f}%" for p in sp],
            ["Max DD"] + [f"{np.percentile(surv_dd, p)*100:.1f}%" for p in sp],
        ]
        print(f"\n### Survivable Distribution ({len(survivable)} combos, DD<={dd_cap_pct:.0f}%)\n\n"
              f"{_md_table(['Metric', 'P5', 'P25', 'P50', 'P75', 'P95'], sd_rows)}")

    # 13. High-vol regime
    fold_vols = []
    for fs, fe in folds:
        window = prices[fs:fe]
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.nan_to_num(np.diff(window, axis=0) / window[:-1], nan=0.0)
        fold_vols.append(float(np.nanmedian(np.nanstd(rets, axis=0) * np.sqrt(252))))

    fold_vols_arr = np.array(fold_vols)
    hv_threshold = np.percentile(fold_vols_arr, 75)
    hv_folds = [i for i, v in enumerate(fold_vols) if v >= hv_threshold]
    print(f"\n### High-Vol Regime (P75={hv_threshold*100:.1f}%, {len(hv_folds)}/{len(folds)} folds)")

    if hv_folds and len(hv_folds) >= 3:
        hv_scores = []
        for r in results:
            hv_rets = [r.fold_returns[i] for i in hv_folds if i < len(r.fold_returns)]
            if not hv_rets:
                continue
            hv_total = float(np.prod([1 + x for x in hv_rets]) - 1)
            n_hv_years = len(hv_rets) * 0.5
            hv_ann = (1 + hv_total) ** (1 / n_hv_years) - 1 if n_hv_years > 0 else 0
            hv_scores.append((r, hv_ann, min(hv_rets)))
        hv_scores.sort(key=lambda x: x[1], reverse=True)

        rows = []
        for i, (r, hv_ann, hv_dd) in enumerate(hv_scores[:10]):
            rows.append([str(i+1), f"{hv_ann*100:+.1f}%", f"{hv_dd*100:+.1f}%",
                         f"{r.oos_annualized*100:+.1f}%", f"{r.oos_max_dd*100:.1f}%", r.label()])
        print(f"\n{_md_table(['#', 'HV Ann.', 'HV Worst', 'Full Ann.', 'Full DD', 'Config'], rows)}")

        top20 = [x[0] for x in hv_scores[:20]]
        print(f"\nHV signal dominance (top 20):")
        hv_lv = Counter(r.params.log_variant.value for r in top20)
        print(f"  log-variant: {' '.join(f'{k}={v}' for k,v in sorted(hv_lv.items()))}")
        for attr, label in [("use_vol_scaling", "vol-scl"), ("use_crash_prot", "crash"),
                            ("use_abs_momentum", "dual-mom"), ("use_earnings", "earn")]:
            y = sum(getattr(r.params, attr) for r in top20)
            print(f"  {label}: on={y} off={20-y}")

    # 14. Cost model
    print(f"\n### Cost Model: {cfg.label}")
    print(f"  commission=${cfg.commission_per_share}/sh min=${cfg.min_commission} "
          f"spread={cfg.half_spread_bps:.0f}bps tax={cfg.tax_rate*100:.0f}%")
    print(f"  (all returns above are AFTER costs)")

    # Summary
    oos_rets = np.array([r.oos_total_return for r in results])
    print(f"\n### Summary")
    print(f"  combos={len(results):,} folds={len(folds)}")
    print(f"  OOS return: best={oos_rets.max()*100:+.1f}% median={np.median(oos_rets)*100:+.1f}% worst={oos_rets.min()*100:+.1f}%")
    print(f"  survivable (DD<={dd_cap_pct:.0f}%): {len(survivable)}/{len(results)}")

    top50 = survivable[:min(50, len(survivable))]
    if not top50:
        print("  NO combos survived the DD cap")
        print("</scenario-analysis>")
        return []

    print(f"\n### Signal Dominance (top 50 survivable)")
    for attr, label in [
        ("skip", "skip"), ("use_sortino", "sortino"), ("use_smoothness", "smooth"),
        ("use_earnings", "earn"), ("use_consistency", "8/12"),
        ("use_abs_momentum", "dual"), ("use_vol_scaling", "vscl"), ("use_crash_prot", "crash"),
    ]:
        vals = [getattr(r.params, attr) for r in top50]
        if isinstance(vals[0], bool):
            print(f"  {label}: on={sum(vals)} off={len(top50)-sum(vals)}")
        else:
            print(f"  {label}: {' '.join(f'{k}={v}' for k,v in sorted(Counter(vals).items()))}")
    print(f"  log-variant: {' '.join(f'{k}={v}' for k,v in sorted(Counter(r.params.log_variant.value for r in top50).items()))}")
    print(f"  rebal: {' '.join(f'{k}d={v}' for k,v in sorted(Counter(r.params.rebal_freq for r in top50).items()))}")
    print(f"  positions: {' '.join(f'{k}={v}' for k,v in sorted(Counter(r.params.max_positions for r in top50).items()))}")

    print("</scenario-analysis>")
    return survivable


def _compute_score_direct(
    prices: np.ndarray, day: int, p, earn_row=None,
) -> np.ndarray:
    """Compute momentum scores directly from price data (no cache)."""
    n_tickers = prices.shape[1]
    n_days = prices.shape[0]

    def _mom_arith(lb, skip):
        end = day + 1 - skip
        start = end - lb
        if start < 0 or end <= 0 or end > n_days:
            return np.zeros(n_tickers)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.nan_to_num(prices[end - 1] / prices[start] - 1, nan=0.0)

    def _mom_ewma(lb, skip):
        end = day + 1 - skip
        start = end - lb
        if start < 0 or end <= 0 or end > n_days:
            return np.zeros(n_tickers)
        log_p = np.log(np.maximum(prices[start:end], 1e-10))
        daily_log = np.diff(log_p, axis=0)
        decay = np.log(2) / 63
        w = np.exp(decay * np.arange(daily_log.shape[0], dtype=np.float64))
        w = w / w.sum()
        return (w[:, np.newaxis] * daily_log).sum(axis=0)

    def _mom_log(lb, skip):
        end = day + 1 - skip
        start = end - lb
        if start < 0 or end <= 0 or end > n_days:
            return np.zeros(n_tickers)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.nan_to_num(np.log(prices[end - 1] / prices[start]), nan=0.0)

    def _mom_vnorm(lb, skip):
        end = day + 1 - skip
        start = end - lb
        if start < 0 or end <= 0 or end > n_days:
            return np.zeros(n_tickers)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_ret = np.nan_to_num(np.log(prices[end - 1] / prices[start]), nan=0.0)
        log_p = np.log(np.maximum(prices[start:end], 1e-10))
        daily = np.diff(log_p, axis=0)
        vol = np.std(daily, axis=0)
        vol = np.where(vol > 0, vol, 0.0001)
        return np.nan_to_num(log_ret / (vol * np.sqrt(lb)), nan=0.0, posinf=0.0, neginf=0.0)

    def _mom_accel(lb, skip):
        end = day + 1 - skip
        start = end - lb
        mid = start + lb // 2
        if start < 0 or end <= 0 or end > n_days:
            return np.zeros(n_tickers)
        with np.errstate(divide="ignore", invalid="ignore"):
            first = np.log(prices[mid] / prices[start])
            second = np.log(prices[end - 1] / prices[mid])
            base = np.log(prices[end - 1] / prices[start])
        return np.nan_to_num(base + 0.5 * (second - first), nan=0.0)

    def _mom_trim(lb, skip):
        end = day + 1 - skip
        start = end - lb
        if start < 0 or end <= 0 or end > n_days:
            return np.zeros(n_tickers)
        log_p = np.log(np.maximum(prices[start:end], 1e-10))
        daily = np.diff(log_p, axis=0)
        n = daily.shape[0]
        trim_n = max(1, int(n * 0.05))
        sorted_d = np.sort(daily, axis=0)
        trimmed = sorted_d[trim_n:-trim_n]
        return trimmed.sum(axis=0) if trimmed.shape[0] > 0 else np.zeros(n_tickers)

    mom_fn_map = {
        "arith": _mom_arith,
        "log": _mom_log,
        "ewma": _mom_ewma,
        "vnorm": _mom_vnorm,
        "accel": _mom_accel,
        "trim": _mom_trim,
    }
    mom_fn = mom_fn_map[p.log_variant.value]

    mom_s = mom_fn(p.lb_short, p.skip)
    mom_m = mom_fn(p.lb_mid, p.skip)
    mom_l = mom_fn(p.lb_long, p.skip)

    wt_mom = p.w_short * mom_s + p.w_mid * mom_m + p.w_long * mom_l
    scores = wt_mom.copy()

    if p.use_smoothness:
        # Compute R² × FIP inline
        w = min(252, day)
        if w > 21:
            log_p = np.log(np.maximum(prices[day - w:day + 1], 1e-10))
            daily = np.diff(log_p, axis=0)
            fip = np.mean(daily > 0, axis=0)
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
                scores *= np.sqrt(r2 * fip)

    if p.use_sortino:
        w = min(252, day)
        if w > 1:
            with np.errstate(divide="ignore", invalid="ignore"):
                rets = np.nan_to_num(prices[day - w + 1:day + 1] / prices[day - w:day] - 1, nan=0.0)
            neg = np.where(rets < 0, rets, 0.0)
            dn_vol = np.sqrt(np.mean(neg ** 2, axis=0)) * np.sqrt(252)
            dn_vol = np.where(dn_vol > 0, dn_vol, 0.0001)
            scores /= dn_vol

    if p.use_earnings and earn_row is not None:
        earn = np.nan_to_num(earn_row, nan=0.0)
        scores *= (1 + np.clip(earn, -0.5, 2.0))

    if p.use_abs_momentum:
        mom_12m = _mom_arith(252, 0)
        scores = np.where(mom_12m > 0, scores, -1.0)

    return np.where(wt_mom > 0, scores, -1.0)


def print_holdings_trace(
    survivable: list[WalkForwardResult],
    prices: np.ndarray,
    dates: np.ndarray,
    folds: list[tuple[int, int]],
    fetched: list[str],
    earn_mom: np.ndarray | None,
    all_rebal_days_sorted: list[int],
    all_lookbacks: list[int],
    all_skips: list[int],
    needed_variants: set,
    need_smoothness: bool,
    need_consistency: bool,
    need_crash: bool,
) -> None:
    """Holdings trace + holding period analysis for top 3 survivable configs."""

    print("<holdings-trace>")

    # Pre-populate ETF names
    for ticker_id in fetched:
        if not ticker_id.isdigit():
            _MF_NAME_CACHE[ticker_id] = ticker_id.replace(".NS", "")

    for rank, r in enumerate(survivable[:3]):
        p = r.params
        print(f"\n### Config #{rank+1}: {p.label()}")
        print(f"  ann={r.oos_annualized*100:+.1f}% dd={r.oos_max_dd*100:.1f}%")

        em = earn_mom if p.use_earnings else None
        n_tk = prices.shape[1]
        safe_mask = np.zeros(n_tk, dtype=bool)
        if fetched and p.use_abs_momentum:
            safe_mask[np.array([i for i, t in enumerate(fetched) if t in backtest_engine.SAFE_HAVENS], dtype=np.intp)] = True

        target_dates = ["2009-03", "2009-06", "2009-09", "2016-01", "2016-06", "2016-11",
                        "2020-02", "2020-03", "2020-04", "2020-06"]
        target_folds = set()
        for fi, (os, oe) in enumerate(folds):
            sd = dates[os] if os < len(dates) else ""
            ed = dates[oe] if oe < len(dates) else ""
            for td in target_dates:
                if sd <= td <= ed or sd[:7] == td[:7]:
                    target_folds.add(fi)
            if fi >= len(folds) - 4:
                target_folds.add(fi)

        rows = []
        for fi, (os, oe) in enumerate(folds):
            if fi not in target_folds:
                continue
            period_len = oe - os
            for rb_offset in list(range(0, period_len, p.rebal_freq))[:4]:
                rb_abs = os + rb_offset
                earn_row = em[rb_abs] if em is not None else None
                scores = _compute_score_direct(prices, rb_abs, p, earn_row)
                valid = np.where((scores > 0) & ~safe_mask)[0]

                dt = dates[rb_abs] if rb_abs < len(dates) else "?"
                if len(valid) == 0:
                    rows.append([dt, str(fi), "CASH", "—"])
                    continue
                sorted_valid = valid[np.argsort(scores[valid])]
                top_n = min(p.max_positions, len(sorted_valid))
                top_idx = sorted_valid[-top_n:][::-1]
                names = [_resolve_name(fetched[i]) for i in top_idx]
                sc = [f"{scores[i]:.3f}" for i in top_idx]
                holdings_str = ", ".join(names[:5]) + (f" +{len(names)-5}" if len(names) > 5 else "")
                rows.append([dt, str(fi), holdings_str, ", ".join(sc[:5])])

        print(f"\n{_md_table(['Date', 'Fold', 'Holdings', 'Scores'], rows)}")

    # Holding period analysis
    print(f"\n### Holding Period Analysis (Config #1)")
    best_p = survivable[0].params
    em_trace = earn_mom if best_p.use_earnings else None
    safe_mask_trace = np.zeros(prices.shape[1], dtype=bool)
    if fetched and best_p.use_abs_momentum:
        safe_mask_trace[np.array([i for i, t in enumerate(fetched) if t in backtest_engine.SAFE_HAVENS])] = True

    all_holdings = []
    for os, oe in folds:
        for rb_offset in range(0, oe - os, best_p.rebal_freq):
            rb_abs = os + rb_offset
            earn_row = em_trace[rb_abs] if em_trace is not None else None
            scores = _compute_score_direct(prices, rb_abs, best_p, earn_row)
            valid = np.where((scores > 0) & ~safe_mask_trace)[0]
            if len(valid) == 0:
                all_holdings.append((dates[rb_abs], ["CASH"]))
                continue
            sorted_valid = valid[np.argsort(scores[valid])]
            top_n = min(best_p.max_positions, len(sorted_valid))
            top_idx = sorted_valid[-top_n:][::-1]
            all_holdings.append((dates[rb_abs], [_resolve_name(fetched[i]) for i in top_idx]))

    streak_counts = defaultdict(list)
    prev_set = set()
    current_streaks = defaultdict(int)
    for _, names in all_holdings:
        current_set = set(names)
        for t in prev_set - current_set:
            if current_streaks[t] > 0:
                streak_counts[t].append(current_streaks[t])
                current_streaks[t] = 0
        for t in current_set:
            current_streaks[t] += 1
        prev_set = current_set
    for t, c in current_streaks.items():
        if c > 0:
            streak_counts[t].append(c)

    rd = best_p.rebal_freq
    rows = []
    ticker_stats = []
    for t, streaks in streak_counts.items():
        if t == "CASH":
            continue
        total_periods = sum(streaks)
        ticker_stats.append((t, len(streaks), np.mean(streaks), max(streaks), total_periods))
    ticker_stats.sort(key=lambda x: x[4], reverse=True)

    for t, n_times, avg_hold, max_hold, total in ticker_stats[:25]:
        rows.append([t[:35], str(n_times), f"{avg_hold*rd/21:.1f}mo",
                     f"{max_hold*rd/21:.1f}mo", f"{total*rd}d"])
    print(f"\n{_md_table(['Ticker', 'TimesHeld', 'AvgHold', 'MaxHold', 'TotalDays'], rows)}")

    if "CASH" in streak_counts:
        cs = streak_counts["CASH"]
        print(f"  cash: {len(cs)}x, avg={np.mean(cs)*rd/21:.1f}mo, max={max(cs)*rd/21:.1f}mo")

    all_streaks = [s * rd / 21 for streaks in streak_counts.values() for s in streaks if streaks]
    if all_streaks:
        arr = np.array(all_streaks)
        print(f"  overall: median={np.median(arr):.1f}mo mean={np.mean(arr):.1f}mo "
              f"P25={np.percentile(arr, 25):.1f}mo P75={np.percentile(arr, 75):.1f}mo")

    # Save name cache
    _save_name_cache()
    print(f"  saved {len(_MF_NAME_CACHE)} scheme names to {_MF_NAMES_FILE}")

    print("</holdings-trace>")


def print_efficient_frontier(
    results: list[WalkForwardResult],
    folds: list[tuple[int, int]],
    fetched: list[str],
) -> None:
    """Plot efficient frontier: return vs drawdown."""
    import pandas as pd
    from plotnine import (
        ggplot, aes, geom_point, geom_label, geom_line,
        labs, scale_x_continuous, scale_y_continuous,
        theme, element_rect, element_text, element_blank,
    )

    plot_df = pd.DataFrame({
        "ann_return": [r.oos_annualized * 100 for r in results],
        "max_dd": [abs(r.oos_max_dd) * 100 for r in results],
        "log_variant": [r.params.log_variant.value for r in results],
    })

    plot_df["dd_bin"] = (plot_df["max_dd"] // 2) * 2
    frontier = plot_df.groupby("dd_bin").agg(
        best_return=("ann_return", "max"), count=("ann_return", "count"),
    ).reset_index()
    frontier = frontier[frontier["count"] >= 3]

    top_labels = []
    for _, row in frontier.iterrows():
        mask = (plot_df["max_dd"] >= row["dd_bin"]) & (plot_df["max_dd"] < row["dd_bin"] + 2)
        candidates = plot_df[mask]
        if len(candidates) == 0:
            continue
        best_idx = candidates["ann_return"].idxmax()
        r = results[best_idx]
        top_labels.append({
            "dd": float(candidates.loc[best_idx, "max_dd"]),
            "ret": float(candidates.loc[best_idx, "ann_return"]),
            "label": r.params.label()[:25],
        })
    labels_df = pd.DataFrame(top_labels).drop_duplicates(subset="label").head(6)
    sample_df = plot_df.sample(min(4000, len(plot_df)), random_state=42)

    p = (
        ggplot(sample_df, aes("max_dd", "ann_return"))
        + geom_point(aes(color="log_variant"), alpha=0.25, size=0.8)
        + geom_line(aes("dd_bin", "best_return"), frontier, color="#F40D0D", size=1.3)
        + geom_label(aes("dd", "ret", label="label"), labels_df, color="#DEE2E6", fill="black", size=7)
        + labs(x="Max Drawdown (%)", y="Annualized Return (%)",
               title="Efficient Frontier: Return vs Drawdown",
               subtitle=f"{len(results):,} combos | {len(folds)} folds | {len(fetched)} instruments | after costs",
               color="Momentum")
        + scale_x_continuous(expand=(0.02, 0))
        + scale_y_continuous(expand=(0.02, 0))
        + theme(figure_size=(12, 7), plot_margin=0.02,
                panel_background=element_rect(fill="#1a1a2e"),
                plot_background=element_rect(fill="#0f0f1a"),
                plot_title=element_text(size=16, color="#E0E0E0"),
                plot_subtitle=element_text(size=10, color="#888888"),
                text=element_text(color="#D7DADD"),
                panel_grid=element_blank(), axis_ticks=element_blank(),
                legend_background=element_rect(fill="#1a1a2e"))
    )

    plot_path = Path(__file__).parent.parent / "data" / "efficient_frontier.png"
    p.save(plot_path, dpi=150, verbose=False)
    print(f"\nEfficient frontier saved: {plot_path}")


def _max_underwater_streak(dd: np.ndarray) -> int:
    """Max consecutive days below peak. Vectorized."""
    underwater = dd < -0.001
    if not underwater.any():
        return 0
    # Diff trick: transitions from False→True start a streak
    padded = np.concatenate([[False], underwater, [False]])
    diffs = np.diff(padded.astype(np.int8))
    starts = np.where(diffs == 1)[0]
    ends = np.where(diffs == -1)[0]
    if len(starts) == 0:
        return 0
    return int((ends - starts).max())


def _batch_compute_scores(prices, params, earn_mom, safe_mask, days_arr):
    """Compute scores at many days at once, reusing rolling computations.

    Returns dict {day: scores_array} for all days in days_arr.
    Much faster than calling _compute_score_direct per-day because
    rolling momentum/vol/smoothness are computed once across the range.
    """
    n_days_total = prices.shape[0]
    n_tickers = prices.shape[1]
    em = earn_mom if params.use_earnings else None
    variant = params.log_variant.value

    # Precompute log prices once
    log_prices = np.log(np.maximum(prices, 1e-10))

    def _rolling_mom_and_vol(lb, skip):
        """Compute momentum and vol for all days at once using vectorized ops."""
        # For each day d, we need prices[d+1-skip-lb] to prices[d+1-skip]
        # This is a rolling window computation
        end_offsets = days_arr + 1 - skip
        start_offsets = end_offsets - lb
        valid = (start_offsets >= 0) & (end_offsets > 0) & (end_offsets <= n_days_total)

        mom = np.zeros((len(days_arr), n_tickers))
        vol = np.full((len(days_arr), n_tickers), 0.0001)

        v_idx = np.where(valid)[0]
        if len(v_idx) == 0:
            return mom, vol, valid

        with np.errstate(divide="ignore", invalid="ignore"):
            if variant == "arith":
                mom[v_idx] = np.nan_to_num(
                    prices[end_offsets[v_idx] - 1] / prices[start_offsets[v_idx]] - 1, nan=0.0)
            elif variant in ("log", "vnorm", "accel"):
                mom[v_idx] = np.nan_to_num(
                    log_prices[end_offsets[v_idx] - 1] - log_prices[start_offsets[v_idx]], nan=0.0)

        if variant == "vnorm":
            # Batch compute rolling std — chunk to limit memory
            daily_log_rets = np.diff(log_prices, axis=0)
            window_len = lb - 1
            chunk_size = max(1, 200_000_000 // (window_len * n_tickers * 8))
            for c0 in range(0, len(v_idx), chunk_size):
                c1 = min(c0 + chunk_size, len(v_idx))
                row_offsets = np.arange(window_len)[None, :]
                indices = start_offsets[v_idx[c0:c1], None] + row_offsets
                windows = daily_log_rets[indices]
                v = np.std(windows, axis=1)
                vol[v_idx[c0:c1]] = np.where(v > 0, v, 0.0001)
            mom[v_idx] = np.nan_to_num(
                mom[v_idx] / (vol[v_idx] * np.sqrt(lb)), nan=0.0, posinf=0.0, neginf=0.0)

        if variant == "accel":
            mid_offsets = start_offsets + lb // 2
            with np.errstate(divide="ignore", invalid="ignore"):
                first = np.nan_to_num(log_prices[mid_offsets[v_idx]] - log_prices[start_offsets[v_idx]], nan=0.0)
                second = np.nan_to_num(log_prices[end_offsets[v_idx] - 1] - log_prices[mid_offsets[v_idx]], nan=0.0)
            mom[v_idx] = np.nan_to_num(mom[v_idx] + 0.5 * (second - first), nan=0.0)

        return mom, vol, valid

    # Compute 3 momentum timeframes
    mom_s, _, _ = _rolling_mom_and_vol(params.lb_short, params.skip)
    mom_m, _, _ = _rolling_mom_and_vol(params.lb_mid, params.skip)
    mom_l, _, _ = _rolling_mom_and_vol(params.lb_long, params.skip)

    wt_mom = params.w_short * mom_s + params.w_mid * mom_m + params.w_long * mom_l
    all_scores = wt_mom.copy()

    if params.use_smoothness:
        # Vectorized R² × FIP using rolling cumulative sums
        w = 252
        n_pts = w + 1  # window has w+1 price points

        # x constants (fixed for all windows of same size)
        x = np.arange(n_pts, dtype=np.float64)
        x_mean = x.mean()
        x_var = ((x - x_mean) ** 2).sum()  # scalar
        # For R²: need sum_y, sum_y², sum_xy per window
        # y = log_prices, window [day-w .. day] inclusive = n_pts points

        # Cumulative sums for rolling computation
        cs_y = np.zeros((n_days_total + 1, n_tickers))     # cumsum of log_prices
        cs_y2 = np.zeros((n_days_total + 1, n_tickers))    # cumsum of log_prices²
        # For sum(x*y): x_i = i for i in 0..w, but x changes relative position
        # Use: sum(i * y_{start+i}) = sum(i * y_i) where i is local index
        # This can't use a simple cumsum trick since x resets per window.
        # But: sum(i * y_{s+i}) for i=0..w = sum((s+i)*y_{s+i}) - s*sum(y_{s+i})
        # And sum(j * y_j) for global j can be cumsummed.
        cs_jy = np.zeros((n_days_total + 1, n_tickers))    # cumsum of j * log_prices[j]
        np.cumsum(log_prices, axis=0, out=cs_y[1:])
        np.cumsum(log_prices ** 2, axis=0, out=cs_y2[1:])
        j_weights = np.arange(n_days_total, dtype=np.float64)[:, np.newaxis]
        np.cumsum(j_weights * log_prices, axis=0, out=cs_jy[1:])

        # FIP: fraction of positive daily returns in window
        daily_log = np.diff(log_prices, axis=0)  # shape (n_days-1, n_tickers)
        pos_daily = (daily_log > 0).astype(np.float64)
        cs_pos = np.zeros((pos_daily.shape[0] + 1, n_tickers))
        np.cumsum(pos_daily, axis=0, out=cs_pos[1:])

        for di, day in enumerate(days_arr):
            if day < w:
                continue
            s = day - w  # start index (inclusive)
            e = day + 1  # end index (exclusive), so window = [s, s+1, ..., day]

            # Rolling sums via cumsum
            sum_y = cs_y[e] - cs_y[s]          # sum of log_prices in window
            sum_y2 = cs_y2[e] - cs_y2[s]       # sum of log_prices² in window
            sum_jy = cs_jy[e] - cs_jy[s]       # sum of j * log_prices[j] for j in [s, e)
            # Convert to local x: sum(x_i * y_{s+i}) = sum((j-s)*y_j) = sum_jy - s*sum_y
            sum_xy = sum_jy - s * sum_y

            y_mean = sum_y / n_pts
            # R² = 1 - SS_res/SS_tot
            # SS_tot = sum_y2 - n_pts * y_mean²
            ss_tot = sum_y2 - n_pts * y_mean ** 2
            # slope = (sum_xy - n_pts * x_mean * y_mean) / x_var
            # SS_res = SS_tot - slope² * x_var
            numerator = sum_xy - n_pts * x_mean * y_mean
            with np.errstate(divide="ignore", invalid="ignore"):
                r2 = np.where(ss_tot > 0, numerator ** 2 / (x_var * ss_tot), 0.0)
                r2 = np.maximum(np.minimum(r2, 1.0), 0.0)

            # FIP from rolling sum
            fip_start = day - w  # daily_log index range: [day-w, day-1]
            fip_end = day
            fip = (cs_pos[fip_end] - cs_pos[fip_start]) / w

            all_scores[di] *= np.sqrt(r2 * fip)

    if params.use_sortino:
        # Precompute daily returns once, then use rolling window
        with np.errstate(divide="ignore", invalid="ignore"):
            all_daily_rets = np.nan_to_num(prices[1:] / prices[:-1] - 1, nan=0.0)
        neg_sq = np.where(all_daily_rets < 0, all_daily_rets ** 2, 0.0)

        # Use cumsum for rolling mean of neg_sq (fixed 252-day window)
        w = 252
        cumsum_neg_sq = np.zeros((neg_sq.shape[0] + 1, n_tickers))
        np.cumsum(neg_sq, axis=0, out=cumsum_neg_sq[1:])

        for di, day in enumerate(days_arr):
            ww = min(w, day)
            if ww > 1:
                start = day - ww
                end = day
                mean_neg_sq = (cumsum_neg_sq[end] - cumsum_neg_sq[start]) / ww
                dn_vol = np.sqrt(mean_neg_sq) * np.sqrt(252)
                dn_vol = np.where(dn_vol > 0, dn_vol, 0.0001)
                all_scores[di] /= dn_vol

    if params.use_earnings and em is not None:
        for di, day in enumerate(days_arr):
            earn = np.nan_to_num(em[day], nan=0.0)
            all_scores[di] *= (1 + np.clip(earn, -0.5, 2.0))

    if params.use_abs_momentum:
        # Vectorized: compute 12m returns for all days at once
        ends = days_arr + 1
        starts = ends - 252
        valid_abs = (starts >= 0) & (ends <= n_days_total)
        v_abs = np.where(valid_abs)[0]
        if len(v_abs) > 0:
            with np.errstate(divide="ignore", invalid="ignore"):
                mom_12m = np.nan_to_num(
                    prices[ends[v_abs] - 1] / prices[starts[v_abs]] - 1, nan=0.0)
            for i, vi in enumerate(v_abs):
                all_scores[vi] = np.where(mom_12m[i] > 0, all_scores[vi], -1.0)

    # Apply safe mask and negative momentum filter
    result = {}
    for di, day in enumerate(days_arr):
        scores = all_scores[di].copy()
        scores[safe_mask] = -1.0
        scores = np.where(wt_mom[di] > 0, scores, -1.0)
        result[day] = scores
    return result


def _mc_underwater_analysis(
    prices: np.ndarray,
    params,
    earn_mom: np.ndarray | None,
    fetched: list[str],
    safe_havens: set[str] | None = None,
    n_sims: int = 200,
    horizon_days: int = 756,
    rng_seed: int = 42,
) -> dict:
    """Monte Carlo underwater analysis with random entry points.

    Precomputes scores at all needed days via batch computation, then
    runs vectorized portfolio simulation.
    """
    if safe_havens is None:
        safe_havens = backtest_engine.SAFE_HAVENS
    n_days = prices.shape[0]
    n_tickers = prices.shape[1]
    rng = np.random.RandomState(rng_seed)

    min_start = max(params.lb_long, 756) + params.skip + 1
    max_start = n_days - horizon_days
    if max_start <= min_start:
        max_start = n_days - 252
    if max_start <= min_start:
        return None

    entry_days = rng.randint(min_start, max_start, size=n_sims)

    safe_mask = np.zeros(n_tickers, dtype=bool)
    for i, t in enumerate(fetched):
        if t in safe_havens:
            safe_mask[i] = True

    rebal_freq = params.rebal_freq
    max_pos = params.max_positions

    # Precompute daily returns matrix once
    with np.errstate(divide="ignore", invalid="ignore"):
        daily_rets = np.nan_to_num(prices[1:] / prices[:-1] - 1, nan=0.0)

    # Collect all unique days where we need scores
    rebal_offsets = list(range(0, horizon_days, rebal_freq))
    needed_days = set()
    for entry in entry_days:
        for t in rebal_offsets:
            day = entry + t
            if day < n_days:
                needed_days.add(day)

    # Batch compute all scores at once (much faster than per-day)
    needed_arr = np.array(sorted(needed_days))
    score_cache = _batch_compute_scores(prices, params, earn_mom, safe_mask, needed_arr)

    # Simulation: iterate rebal offsets, then sims
    portfolios = np.ones((n_sims, horizon_days))

    for rb_idx, t in enumerate(rebal_offsets):
        next_t = rebal_offsets[rb_idx + 1] if rb_idx + 1 < len(rebal_offsets) else horizon_days

        for sim_i, entry in enumerate(entry_days):
            day = entry + t
            if day >= n_days:
                portfolios[sim_i, t + 1:] = portfolios[sim_i, t]
                continue

            scores = score_cache.get(day)
            if scores is None:
                end = min(t + (next_t - t), horizon_days)
                portfolios[sim_i, t + 1:end] = portfolios[sim_i, t]
                continue

            valid = np.where(scores > 0)[0]
            if len(valid) == 0:
                end = min(t + (next_t - t), horizon_days)
                portfolios[sim_i, t + 1:end] = portfolios[sim_i, t]
                continue

            sorted_v = valid[np.argsort(scores[valid])]
            top_n = min(max_pos, len(sorted_v))
            top_idx = sorted_v[-top_n:]

            abs_start = entry + t
            abs_end = min(entry + next_t, n_days)
            actual = abs_end - abs_start
            if actual <= 0:
                continue
            hold_rets = daily_rets[abs_start:abs_end - 1][:, top_idx].mean(axis=1)
            end_idx = min(t + actual, horizon_days)
            cum = np.cumprod(1.0 + hold_rets)
            portfolios[sim_i, t + 1:end_idx] = portfolios[sim_i, t] * cum[:end_idx - t - 1]

    # Vectorized stats across all sims
    running_max = np.maximum.accumulate(portfolios, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(running_max > 0, (portfolios - running_max) / running_max, 0.0)

    max_dd_arr = dd.min(axis=1)
    total_ret_arr = portfolios[:, -1] / portfolios[:, 0] - 1
    years = horizon_days / 252
    cagr_arr = np.where(
        total_ret_arr > -1,
        np.power(1 + total_ret_arr, 1 / years) - 1,
        -1.0,
    )
    below_10_arr = (portfolios < 0.90).sum(axis=1)
    below_20_arr = (portfolios < 0.80).sum(axis=1)
    streak_arr = np.array([_max_underwater_streak(dd[i]) for i in range(n_sims)])

    def _pctiles(arr):
        return {
            "p5": float(np.percentile(arr, 5)),
            "p25": float(np.percentile(arr, 25)),
            "median": float(np.median(arr)),
            "p75": float(np.percentile(arr, 75)),
            "p95": float(np.percentile(arr, 95)),
            "mean": float(np.mean(arr)),
        }

    return {
        "total_return": _pctiles(total_ret_arr),
        "cagr": _pctiles(cagr_arr),
        "max_dd": _pctiles(max_dd_arr),
        "max_underwater_streak": _pctiles(streak_arr),
        "below_10_days": _pctiles(below_10_arr),
        "below_20_days": _pctiles(below_20_arr),
        "n_sims": n_sims,
        "horizon_days": horizon_days,
    }


def _mc_entry_points(prices, n_sims, min_start, max_start, seed=42):
    """Generate shared entry points — same seed for all configs."""
    rng = np.random.RandomState(seed)
    return rng.randint(min_start, max_start, size=n_sims)


def _mc_worker_run(args):
    """Worker function for parallel MC — runs one config."""
    params, prices, earn_mom, fetched, safe_havens, n_sims, horizon, seed = args
    mc = _mc_underwater_analysis(prices, params, earn_mom, fetched,
                                 safe_havens=safe_havens,
                                 n_sims=n_sims, horizon_days=horizon,
                                 rng_seed=seed)
    return mc


def _print_mc_table(label: str, candidates, prices, earn_mom, fetched, top_n=20, safe_havens=None):
    """Run MC analysis on top N configs and print full results."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    if safe_havens is None:
        safe_havens = backtest_engine.SAFE_HAVENS
    if not candidates:
        print(f"\n### {label} — Monte Carlo: no candidates")
        return
    n_days = prices.shape[0]
    horizon = 756
    # Shared entry points across all configs
    min_start = 756 + 21 + 1
    max_start = n_days - horizon
    if max_start <= min_start:
        max_start = n_days - 252
    if max_start <= min_start:
        print(f"\n### {label} — Monte Carlo: insufficient data")
        return

    actual_n = min(top_n, len(candidates))
    print(f"\n### {label} — Monte Carlo Analysis")
    print(f"  {actual_n} configs × 200 shared entries × 3yr (parallel)")
    print(f"  Seed=42, entries from day {min_start} to {max_start}")

    work_items = [
        (r.params, prices, earn_mom, fetched, safe_havens, 200, horizon, 42)
        for r in candidates[:top_n]
    ]

    mc_results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_mc_worker_run, w): i for i, w in enumerate(work_items)}
        for future in as_completed(futures):
            idx = futures[future]
            mc = future.result()
            if mc is not None:
                mc_results.append({"r": candidates[idx], "mc": mc})

    # Sort by median CAGR descending
    mc_results.sort(key=lambda x: x["mc"]["cagr"]["median"], reverse=True)

    table_rows = []
    for i, m in enumerate(mc_results):
        r = m["r"]
        mc = m["mc"]
        cagr = mc["cagr"]
        dd = mc["max_dd"]
        streak = mc["max_underwater_streak"]
        b10 = mc["below_10_days"]
        b20 = mc["below_20_days"]
        table_rows.append([
            f"{i+1}",
            r.params.label()[:40],
            # MC Returns
            f"{cagr['p5']*100:+.0f}%",
            f"{cagr['p25']*100:+.0f}%",
            f"{cagr['median']*100:+.0f}%",
            f"{cagr['p75']*100:+.0f}%",
            f"{cagr['p95']*100:+.0f}%",
            # MC Drawdown
            f"{dd['median']*100:.0f}%",
            f"{dd['p5']*100:.0f}%",
            # Underwater streak (days)
            f"{streak['median']:.0f}",
            f"{streak['p75']:.0f}",
            # Days below entry -10%, -20%
            f"{b10['median']:.0f}",
            f"{b20['median']:.0f}",
            # Walk-forward for reference
            f"{r.oos_annualized*100:+.0f}%",
        ])

    print(_md_table(
        ["#", "Config",
         "P5", "P25", "Med", "P75", "P95",
         "DD Med", "DD Wst",
         "Strk", "Strk75",
         "<-10%", "<-20%",
         "WF Ann"],
        table_rows,
    ))

    # Summary stats
    if mc_results:
        meds = [m["mc"]["cagr"]["median"] for m in mc_results]
        p5s = [m["mc"]["cagr"]["p5"] for m in mc_results]
        print(f"\n  Across {len(mc_results)} configs:")
        print(f"    MC median CAGR: best={max(meds)*100:+.0f}% "
              f"worst={min(meds)*100:+.0f}% avg={np.mean(meds)*100:+.0f}%")
        print(f"    MC P5 CAGR (worst 5%): best={max(p5s)*100:+.0f}% "
              f"worst={min(p5s)*100:+.0f}%")


def print_portfolio_allocation(
    results: list[WalkForwardResult],
    prices: np.ndarray,
    dates: np.ndarray,
    fetched: list[str],
    earn_mom: np.ndarray | None,
    cfg: MarketConfig | None = None,
    use_options: bool = False,
) -> None:
    """Split results into Core (60%, DD<=30%) and Max (30%, DD<=75%).

    10% always allocated to safe-haven assets.
    Picks best config per bucket by Sortino ratio, then computes
    current holdings using direct price-based scoring.
    """
    capital = cfg.portfolio_value if cfg else 50_000.0
    currency = "₹" if cfg and "India" in cfg.label else "$"
    has_earnings = earn_mom is not None

    CORE_DD_CAP = 0.30
    MAX_DD_CAP = 0.75
    OPTIONS_BUDGET = 0.05 if use_options else 0.0
    CORE_WEIGHT = 0.60 - OPTIONS_BUDGET * 0.6
    MAX_WEIGHT = 0.30 - OPTIONS_BUDGET * 0.3
    SAFE_WEIGHT = 0.10

    core_capital = capital * CORE_WEIGHT
    max_capital = capital * MAX_WEIGHT
    safe_capital = capital * SAFE_WEIGHT
    options_budget = capital * OPTIONS_BUDGET

    def _is_validated_signal(p) -> bool:
        """MC-validated signal family.

        With earnings (US): sort+earn+vnorm.
        Without earnings (India/ETFs): sort+vnorm (earnings not available).
        """
        base = p.use_sortino and p.log_variant.value == "vnorm"
        if has_earnings:
            return base and p.use_earnings
        return base and not p.use_earnings

    # Core: validated signal, DD<=30%, ranked by Sortino
    core_candidates = [
        r for r in results
        if abs(r.oos_max_dd) <= CORE_DD_CAP
        and r.oos_annualized > 0
        and _is_validated_signal(r.params)
    ]
    # Max: validated signal, DD<=75%, ranked by absolute return
    max_candidates = [
        r for r in results
        if abs(r.oos_max_dd) <= MAX_DD_CAP
        and r.oos_annualized > 0
        and _is_validated_signal(r.params)
    ]

    core_candidates.sort(key=lambda r: r.oos_sortino, reverse=True)
    max_candidates.sort(key=lambda r: r.oos_annualized, reverse=True)

    print("\n<portfolio-allocation>")
    print(f"### Portfolio Split: {currency}{capital:,.0f}")
    print(f"  Core: {currency}{core_capital:,.0f} ({CORE_WEIGHT:.0%}) — DD cap {CORE_DD_CAP:.0%}")
    print(f"  Max:  {currency}{max_capital:,.0f} ({MAX_WEIGHT:.0%}) — DD cap {MAX_DD_CAP:.0%}")
    n_safe = len(backtest_engine.SAFE_HAVENS)
    if n_safe <= 10:
        safe_label = ", ".join(sorted(backtest_engine.SAFE_HAVENS))
    else:
        safe_label = f"{n_safe} tickers (debt/gold/silver)"
    print(f"  Safe: {currency}{safe_capital:,.0f} ({SAFE_WEIGHT:.0%}) — {safe_label}")
    if use_options:
        print(f"  Options: {currency}{options_budget:,.0f} ({OPTIONS_BUDGET:.0%}) — PUTs + CALLs")

    last_day = prices.shape[0] - 1

    def _current_holdings(r, alloc_capital):
        """Get current holdings for a config."""
        p = r.params
        em = earn_mom if p.use_earnings else None
        earn_row = em[last_day] if em is not None else None
        scores = _compute_score_direct(
            prices, last_day, p, earn_row
        )

        # Exclude safe havens from scoring
        safe_idx = set()
        for i, t in enumerate(fetched):
            if t in backtest_engine.SAFE_HAVENS:
                safe_idx.add(i)
                scores[i] = -1.0

        valid = np.where(scores > 0)[0]
        if len(valid) == 0:
            return [], scores

        sorted_valid = valid[np.argsort(scores[valid])]
        top_n = min(p.max_positions, len(sorted_valid))
        top_idx = sorted_valid[-top_n:][::-1]

        # Equal-weight allocation
        per_position = alloc_capital / top_n
        holdings = []
        for idx in top_idx:
            ticker = fetched[idx]
            price = prices[last_day, idx]
            shares = int(per_position / price) if price > 0 else 0
            holdings.append({
                "ticker": ticker,
                "score": scores[idx],
                "price": price,
                "shares": shares,
                "value": shares * price,
            })
        return holdings, scores

    def _print_bucket(label, candidates, alloc_capital, top_n=5):
        if not candidates:
            print(f"\n### {label}: No configs found within DD cap")
            return None

        best = candidates[0]
        p = best.params
        print(f"\n### {label}")
        print(f"  Config: {p.label()}")
        print(f"  Ann={best.oos_annualized*100:+.1f}% "
              f"DD={best.oos_max_dd*100:.1f}% "
              f"Sortino={best.oos_sortino:.2f} "
              f"Calmar={best.oos_calmar:.2f} "
              f"Win={best.oos_win_rate*100:.0f}%")

        # Show top 5 alternatives
        print(f"\n  Top {top_n} configs by Sortino:")
        rows = []
        for r in candidates[:top_n]:
            rows.append([
                r.params.label()[:50],
                f"{r.oos_annualized*100:+.1f}%",
                f"{r.oos_max_dd*100:.1f}%",
                f"{r.oos_sortino:.2f}",
                f"{r.oos_calmar:.2f}",
                f"{r.oos_win_rate*100:.0f}%",
            ])
        print(_md_table(
            ["Config", "Ann", "MaxDD", "Sortino", "Calmar", "Win%"],
            rows,
        ))

        holdings, _ = _current_holdings(best, alloc_capital)
        if not holdings:
            print(f"\n  Current: CASH (no positive momentum)")
            return best

        print(f"\n  Current Holdings (as of {dates[last_day]}):")
        rows = []
        total_val = 0
        for h in holdings:
            rows.append([
                _resolve_name(h["ticker"]),
                f"{h['score']:.4f}",
                f"{currency}{h['price']:.2f}",
                str(h["shares"]),
                f"{currency}{h['value']:,.0f}",
            ])
            total_val += h["value"]
        print(_md_table(
            ["Ticker", "Score", "Price", "Shares", "Value"],
            rows,
        ))
        cash_left = alloc_capital - total_val
        if cash_left > 0:
            print(f"  Residual cash: {currency}{cash_left:,.0f}")

        return best

    core_best = _print_bucket("CORE (60%)", core_candidates, core_capital)
    max_best = _print_bucket("MAX (30%)", max_candidates, max_capital)

    # Monte Carlo underwater analysis
    safe_set = backtest_engine.SAFE_HAVENS
    _print_mc_table("CORE", core_candidates, prices, earn_mom, fetched, safe_havens=safe_set)
    _print_mc_table("MAX", max_candidates, prices, earn_mom, fetched, safe_havens=safe_set)

    # Safe haven allocation
    safe_tickers = [t for t in fetched if t in backtest_engine.SAFE_HAVENS]
    print(f"\n### SAFE HAVEN (10%)")
    if safe_tickers:
        # Pick by 12m momentum
        safe_scores = []
        for t in safe_tickers:
            idx = fetched.index(t)
            lb = 252
            end = last_day + 1
            start = end - lb
            if start >= 0:
                with np.errstate(divide="ignore", invalid="ignore"):
                    ret = float(np.nan_to_num(
                        prices[end - 1, idx] / prices[start, idx] - 1
                    ))
            else:
                ret = 0.0
            safe_scores.append((t, ret, prices[last_day, idx]))
        safe_scores.sort(key=lambda x: x[1], reverse=True)

        per_safe = safe_capital / min(3, len(safe_scores))
        rows = []
        total_safe = 0
        for t, ret, px in safe_scores[:3]:
            shares = int(per_safe / px) if px > 0 else 0
            val = shares * px
            rows.append([t, f"{ret*100:+.1f}%", f"{currency}{px:.2f}",
                         str(shares), f"{currency}{val:,.0f}"])
            total_safe += val
        print(_md_table(
            ["Ticker", "12M Ret", "Price", "Shares", "Value"],
            rows,
        ))

    # Combined summary
    print(f"\n### COMBINED PORTFOLIO SUMMARY")
    all_positions = {}

    if core_best:
        core_h, _ = _current_holdings(core_best, core_capital)
        for h in core_h:
            t = h["ticker"]
            if t not in all_positions:
                all_positions[t] = {"shares": 0, "value": 0, "bucket": []}
            all_positions[t]["shares"] += h["shares"]
            all_positions[t]["value"] += h["value"]
            all_positions[t]["bucket"].append("Core")
            all_positions[t]["price"] = h["price"]

    if max_best:
        max_h, _ = _current_holdings(max_best, max_capital)
        for h in max_h:
            t = h["ticker"]
            if t not in all_positions:
                all_positions[t] = {"shares": 0, "value": 0, "bucket": []}
            all_positions[t]["shares"] += h["shares"]
            all_positions[t]["value"] += h["value"]
            all_positions[t]["bucket"].append("Max")
            all_positions[t]["price"] = h["price"]

    if safe_tickers:
        for t, ret, px in safe_scores[:3]:
            shares = int(per_safe / px) if px > 0 else 0
            val = shares * px
            if t not in all_positions:
                all_positions[t] = {"shares": 0, "value": 0, "bucket": []}
            all_positions[t]["shares"] += shares
            all_positions[t]["value"] += val
            all_positions[t]["bucket"].append("Safe")
            all_positions[t]["price"] = px

    rows = []
    total = 0
    for t in sorted(all_positions, key=lambda x: all_positions[x]["value"], reverse=True):
        pos = all_positions[t]
        pct = pos["value"] / capital * 100
        rows.append([
            _resolve_name(t),
            "+".join(pos["bucket"]),
            f"{currency}{pos['price']:.2f}",
            str(pos["shares"]),
            f"{currency}{pos['value']:,.0f}",
            f"{pct:.1f}%",
        ])
        total += pos["value"]
    print(_md_table(
        ["Ticker", "Bucket", "Price", "Shares", "Value", "Wt%"],
        rows,
    ))
    print(f"  Total invested: {currency}{total:,.0f} / {currency}{capital:,.0f} "
          f"({total/capital*100:.1f}%)")
    print(f"  Cash: {currency}{capital - total:,.0f}")

    # ── Options overlay ──────────────────────────────────────────────
    if use_options:
        from options_utils import options_overlay_for_portfolio

        print(f"\n### OPTIONS OVERLAY")
        print(f"  Core: protective PUTs (5% OTM, 90 DTE)")
        print(f"  Max: conviction CALLs (10% OTM, 90 DTE)")
        print(f"  Budget: PUTs ≤5% of position, CALLs ≤10% of bucket")

        total_options_cost = 0

        # Core PUTs
        if core_best:
            core_h, _ = _current_holdings(core_best, core_capital)
            core_opts = options_overlay_for_portfolio(
                core_h, prices, fetched, "core",
                put_budget_pct=0.05,
            )
            if core_opts:
                print(f"\n  **Core Protective PUTs:**")
                rows = []
                for o in core_opts:
                    rows.append([
                        o["ticker"],
                        f"${o['strike']:.0f}",
                        f"${o['premium']:.2f}",
                        str(o["contracts"]),
                        f"${o['total_cost']:,.0f}",
                        f"{o['delta']:.2f}",
                        f"{o['sigma']*100:.0f}%",
                        f"{o['shares_protected']}sh",
                    ])
                    total_options_cost += o["total_cost"]
                print(_md_table(
                    ["Ticker", "Strike", "Prem/sh",
                     "Ctrs", "Cost", "Delta",
                     "Vol", "Protect"],
                    rows,
                ))

        # Max CALLs
        if max_best:
            max_h, _ = _current_holdings(max_best, max_capital)
            max_opts = options_overlay_for_portfolio(
                max_h, prices, fetched, "max",
                call_budget_pct=0.10,
            )
            if max_opts:
                print(f"\n  **Max Conviction CALLs:**")
                rows = []
                for o in max_opts:
                    rows.append([
                        o["ticker"],
                        f"${o['strike']:.0f}",
                        f"${o['premium']:.2f}",
                        str(o["contracts"]),
                        f"${o['total_cost']:,.0f}",
                        f"{o['delta']:.2f}",
                        f"{o['sigma']*100:.0f}%",
                        f"{o['leverage']:.0f}x",
                        f"${o['breakeven']:.0f}",
                    ])
                    total_options_cost += o["total_cost"]
                print(_md_table(
                    ["Ticker", "Strike", "Prem/sh",
                     "Ctrs", "Cost", "Delta",
                     "Vol", "Lev", "B/E"],
                    rows,
                ))

        print(f"\n  Total options cost: ${total_options_cost:,.0f} "
              f"({total_options_cost/capital*100:.1f}% of capital)")
        remaining = capital - total - total_options_cost
        print(f"  Cash after options: ${remaining:,.0f}")

    print("</portfolio-allocation>")
