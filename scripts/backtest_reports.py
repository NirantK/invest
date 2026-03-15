"""Reporting functions for backtest.py — LLM-parseable markdown + xml output."""

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from backtest import (
    MarketConfig,
    SAFE_HAVENS,
    WalkForwardResult,
    precompute_signals,
    score_from_cache,
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

    # MF name resolution
    import json as _json
    mf_names_file = Path(__file__).parent.parent / "data" / "india" / "mf_scheme_names.json"
    mf_name_cache = {}
    if mf_names_file.exists():
        mf_name_cache = _json.loads(mf_names_file.read_text())
    for ticker_id in fetched:
        if not ticker_id.isdigit():
            mf_name_cache[ticker_id] = ticker_id.replace(".NS", "")

    def _resolve_name(ticker_id: str) -> str:
        if ticker_id in mf_name_cache:
            return mf_name_cache[ticker_id]
        if ticker_id.isdigit():
            import httpx as _hx
            resp = _hx.get(f"https://api.mfapi.in/mf/{ticker_id}", timeout=5)
            if resp.status_code == 200:
                name = resp.json().get("meta", {}).get("scheme_name", ticker_id)
                for drop in [" - Direct Plan", " Direct Plan", "-Direct Plan",
                             " - Growth Option", " - Growth", "-Growth", " Growth",
                             " Option", " Fund"]:
                    name = name.replace(drop, "")
                mf_name_cache[ticker_id] = name[:45]
        return mf_name_cache.get(ticker_id, ticker_id)

    for rank, r in enumerate(survivable[:3]):
        p = r.params
        print(f"\n### Config #{rank+1}: {p.label()}")
        print(f"  ann={r.oos_annualized*100:+.1f}% dd={r.oos_max_dd*100:.1f}%")

        em = earn_mom if p.use_earnings else None
        n_tk = prices.shape[1]
        safe_mask = np.zeros(n_tk, dtype=bool)
        if fetched and p.use_abs_momentum:
            safe_mask[np.array([i for i, t in enumerate(fetched) if t in SAFE_HAVENS], dtype=np.intp)] = True

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
        safe_mask_trace[np.array([i for i, t in enumerate(fetched) if t in SAFE_HAVENS])] = True

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
    mf_names_file.parent.mkdir(parents=True, exist_ok=True)
    mf_names_file.write_text(_json.dumps(mf_name_cache, indent=2, sort_keys=True))
    print(f"  saved {len(mf_name_cache)} scheme names to {mf_names_file}")

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

    plot_path = Path(__file__).parent.parent / "data" / "us" / "efficient_frontier.png"
    p.save(plot_path, dpi=150, verbose=False)
    print(f"\nEfficient frontier saved: {plot_path}")


def _mc_underwater_analysis(
    prices: np.ndarray,
    params,
    earn_mom: np.ndarray | None,
    fetched: list[str],
    n_sims: int = 200,
    horizon_days: int = 756,  # 3 years
    rng_seed: int = 42,
) -> dict:
    """Monte Carlo underwater analysis with random entry points.

    For a given config, picks random entry dates, runs the strategy forward,
    and computes:
    - Duration underwater (days below previous peak)
    - Duration below -10% from entry
    - Duration below -20% from entry
    - Max drawdown distribution

    Returns dict with percentile stats.
    """
    n_days = prices.shape[0]
    n_tickers = prices.shape[1]
    rng = np.random.RandomState(rng_seed)

    # Need enough history for longest lookback + skip
    min_start = max(params.lb_long, 756) + params.skip + 1
    max_start = n_days - horizon_days
    if max_start <= min_start:
        max_start = n_days - 252  # at least 1 year
    if max_start <= min_start:
        return None

    entry_days = rng.randint(min_start, max_start, size=n_sims)

    # Safe haven mask
    safe_mask = np.zeros(n_tickers, dtype=bool)
    for i, t in enumerate(fetched):
        if t in SAFE_HAVENS:
            safe_mask[i] = True

    results = {
        "total_return": [],         # total return over horizon
        "cagr": [],                 # annualized return
        "max_dd": [],               # max drawdown
        "max_underwater_streak": [],  # longest streak below peak (days)
        "below_10_days": [],        # days below -10% from entry
        "below_20_days": [],        # days below -20% from entry
    }

    em = earn_mom if params.use_earnings else None

    for entry in entry_days:
        sim_len = min(horizon_days, n_days - entry)
        portfolio = np.ones(sim_len)
        rebal_freq = params.rebal_freq

        prev_weights = np.zeros(n_tickers)
        for t in range(0, sim_len - 1, rebal_freq):
            day = entry + t
            earn_row = em[day] if em is not None else None
            scores = _compute_score_direct(prices, day, params, earn_row)
            scores[safe_mask] = -1.0
            valid = np.where(scores > 0)[0]

            if len(valid) == 0:
                # Hold cash — portfolio flat
                hold_end = min(t + rebal_freq, sim_len)
                portfolio[t + 1:hold_end] = portfolio[t]
                prev_weights[:] = 0
                continue

            sorted_v = valid[np.argsort(scores[valid])]
            top_n = min(params.max_positions, len(sorted_v))
            top_idx = sorted_v[-top_n:]

            weights = np.zeros(n_tickers)
            weights[top_idx] = 1.0 / top_n

            hold_end = min(t + rebal_freq, sim_len)
            for d in range(t, hold_end - 1):
                abs_d = entry + d
                if abs_d + 1 >= n_days:
                    portfolio[d + 1] = portfolio[d]
                    continue
                with np.errstate(divide="ignore", invalid="ignore"):
                    daily_ret = np.nan_to_num(
                        prices[abs_d + 1] / prices[abs_d] - 1, nan=0.0
                    )
                port_ret = float(np.dot(weights, daily_ret))
                portfolio[d + 1] = portfolio[d] * (1 + port_ret)

            prev_weights = weights

        # Compute underwater stats
        running_max = np.maximum.accumulate(portfolio)
        dd = (portfolio - running_max) / running_max

        max_dd = float(dd.min())
        underwater = dd < -0.001  # below peak by >0.1%
        underwater_days = int(underwater.sum())
        underwater_pct = underwater_days / sim_len

        # Max underwater streak
        streaks = []
        current = 0
        for u in underwater:
            if u:
                current += 1
            else:
                if current > 0:
                    streaks.append(current)
                current = 0
        if current > 0:
            streaks.append(current)
        max_streak = max(streaks) if streaks else 0

        # Below entry thresholds
        below_10 = portfolio < 0.90
        below_20 = portfolio < 0.80
        below_10_days = int(below_10.sum())
        below_20_days = int(below_20.sum())

        # Returns
        total_return = portfolio[-1] / portfolio[0] - 1
        years = sim_len / 252
        cagr = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0

        results["max_dd"].append(max_dd)
        results["total_return"].append(total_return)
        results["cagr"].append(cagr)
        results["max_underwater_streak"].append(max_streak)
        results["below_10_days"].append(below_10_days)
        results["below_20_days"].append(below_20_days)

    # Compute percentiles
    def _pctiles(arr):
        return {
            "p5": float(np.percentile(arr, 5)),
            "p25": float(np.percentile(arr, 25)),
            "median": float(np.median(arr)),
            "p75": float(np.percentile(arr, 75)),
            "p95": float(np.percentile(arr, 95)),
            "mean": float(np.mean(arr)),
        }

    summary = {k: _pctiles(np.array(v)) for k, v in results.items()}
    summary["n_sims"] = n_sims
    summary["horizon_days"] = horizon_days
    return summary


def _mc_entry_points(prices, n_sims, min_start, max_start, seed=42):
    """Generate shared entry points — same seed for all configs."""
    rng = np.random.RandomState(seed)
    return rng.randint(min_start, max_start, size=n_sims)


def _print_mc_table(label: str, candidates, prices, earn_mom, fetched, top_n=50):
    """Run MC analysis on top N configs and print full results."""
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

    shared_entries = _mc_entry_points(prices, 200, min_start, max_start)

    print(f"\n### {label} — Monte Carlo Analysis")
    print(f"  {min(top_n, len(candidates))} configs × 200 shared entries × 3yr")
    print(f"  Seed=42, entries from day {min_start} to {max_start}")

    mc_results = []
    for r in candidates[:top_n]:
        mc = _mc_underwater_analysis(
            prices, r.params, earn_mom, fetched,
            n_sims=200, horizon_days=horizon,
            rng_seed=42,
        )
        if mc is None:
            continue
        mc_results.append({"r": r, "mc": mc})

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
    capital: float = 50000.0,
    use_options: bool = False,
) -> None:
    """Split results into Core (60%, DD<=30%) and Max (30%, DD<=75%).

    10% always allocated to safe-haven assets.
    Picks best config per bucket by Sortino ratio, then computes
    current holdings using direct price-based scoring.
    """
    CORE_DD_CAP = 0.30
    MAX_DD_CAP = 0.75
    OPTIONS_BUDGET = 0.05 if use_options else 0.0  # 5% reserved
    CORE_WEIGHT = 0.60 - OPTIONS_BUDGET * 0.6  # scale down proportionally
    MAX_WEIGHT = 0.30 - OPTIONS_BUDGET * 0.3
    SAFE_WEIGHT = 0.10

    core_capital = capital * CORE_WEIGHT
    max_capital = capital * MAX_WEIGHT
    safe_capital = capital * SAFE_WEIGHT
    options_budget = capital * OPTIONS_BUDGET

    def _is_validated_signal(p) -> bool:
        """MC-validated signal family: sort+earn+vnorm."""
        return p.use_sortino and p.use_earnings and p.log_variant.value == "vnorm"

    # Core: sort+earn+vnorm, DD<=30%, ranked by Sortino
    core_candidates = [
        r for r in results
        if abs(r.oos_max_dd) <= CORE_DD_CAP
        and r.oos_annualized > 0
        and _is_validated_signal(r.params)
    ]
    # Max: sort+earn+vnorm, DD<=75%, ranked by absolute return
    max_candidates = [
        r for r in results
        if abs(r.oos_max_dd) <= MAX_DD_CAP
        and r.oos_annualized > 0
        and _is_validated_signal(r.params)
    ]

    core_candidates.sort(key=lambda r: r.oos_sortino, reverse=True)
    max_candidates.sort(key=lambda r: r.oos_annualized, reverse=True)

    print("\n<portfolio-allocation>")
    print(f"### Portfolio Split: ${capital:,.0f}")
    print(f"  Core: ${core_capital:,.0f} ({CORE_WEIGHT:.0%}) — DD cap {CORE_DD_CAP:.0%}")
    print(f"  Max:  ${max_capital:,.0f} ({MAX_WEIGHT:.0%}) — DD cap {MAX_DD_CAP:.0%}")
    print(f"  Safe: ${safe_capital:,.0f} ({SAFE_WEIGHT:.0%}) — {', '.join(sorted(SAFE_HAVENS))}")
    if use_options:
        print(f"  Options: ${options_budget:,.0f} ({OPTIONS_BUDGET:.0%}) — PUTs + CALLs")

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
            if t in SAFE_HAVENS:
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
                h["ticker"],
                f"{h['score']:.4f}",
                f"${h['price']:.2f}",
                str(h["shares"]),
                f"${h['value']:,.0f}",
            ])
            total_val += h["value"]
        print(_md_table(
            ["Ticker", "Score", "Price", "Shares", "Value"],
            rows,
        ))
        cash_left = alloc_capital - total_val
        if cash_left > 0:
            print(f"  Residual cash: ${cash_left:,.0f}")

        return best

    core_best = _print_bucket("CORE (60%)", core_candidates, core_capital)
    max_best = _print_bucket("MAX (30%)", max_candidates, max_capital)

    # Monte Carlo underwater analysis
    _print_mc_table("CORE", core_candidates, prices, earn_mom, fetched)
    _print_mc_table("MAX", max_candidates, prices, earn_mom, fetched)

    # Safe haven allocation
    safe_tickers = [t for t in fetched if t in SAFE_HAVENS]
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
            rows.append([t, f"{ret*100:+.1f}%", f"${px:.2f}",
                         str(shares), f"${val:,.0f}"])
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
            t,
            "+".join(pos["bucket"]),
            f"${pos['price']:.2f}",
            str(pos["shares"]),
            f"${pos['value']:,.0f}",
            f"{pct:.1f}%",
        ])
        total += pos["value"]
    print(_md_table(
        ["Ticker", "Bucket", "Price", "Shares", "Value", "Wt%"],
        rows,
    ))
    print(f"  Total invested: ${total:,.0f} / ${capital:,.0f} "
          f"({total/capital*100:.1f}%)")
    print(f"  Cash: ${capital - total:,.0f}")

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
