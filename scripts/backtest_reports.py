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

    trace_cache = precompute_signals(
        prices, all_rebal_days_sorted, all_lookbacks, all_skips,
        needed_variants=needed_variants, need_smoothness=need_smoothness,
        need_consistency=need_consistency, need_crash=need_crash,
    )

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
            safe_mask[np.array([i for i, t in enumerate(fetched) if t in SAFE_HAVENS])] = True

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
                scores = score_from_cache(rb_abs, p, trace_cache, earn_row)
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
            scores = score_from_cache(rb_abs, best_p, trace_cache, earn_row)
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
