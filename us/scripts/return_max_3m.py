"""Tactical 3-month return maximizer.

Sub-strategy of the main book (15-30% of capital). Optimized to maximize
P75 of the next 63-day return, not the long-run CAGR.

Sweep:
  score_variant ∈ {1w, 2w, 4w, 8w, eq, tilt, sortino}   (7)
  rebal_days    ∈ {2, 5, 10}                              (3)
  max_positions ∈ {5, 8, 10}                              (3)
  leverage      ∈ {1.0, 1.3, 1.5, 2.0}                    (4)
                                                  = 252 configs

Validation: rolling 63-day forward windows starting every 21 trading days
from 2008-01 onward. Per config across windows: P50 / P75 / P90 of 63d
return + P50 ulcer + P50 max_dd.

Breadth gate: if <30% of universe has positive 4W momentum at rebal,
hold cash (4.5% yield).

Costs modeled:
  - 5 bps per rebal × leverage (turnover proxy, IBKR-realistic)
  - 6.0% annual margin debit on negative cash (RegT-ish)
  - 4.5% annual yield on positive cash (T-bill-ish)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import click
import numpy as np
import polars as pl
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from invest.momentum_3m import precompute_scores, SCORE_VARIANTS, LB_8W  # noqa: E402
from invest.backtest import ffill_columns  # noqa: E402
from us_portfolio_allocation import TICKERS, fetch_total_return_index, BENCHMARK_TICKERS  # noqa: E402

console = Console()
HERE = ROOT / "us" / "autoresearch"
DOCS = ROOT / "docs"

WINDOW_DAYS = 63
STEP_DAYS = 21
WARMUP_DAYS = LB_8W + 5
BREADTH_THRESHOLD = 0.30
TURNOVER_BPS = 5
CASH_YIELD_ANNUAL = 0.045
MARGIN_DEBIT_ANNUAL = 0.06
START_DATE_DEFAULT = "2008-01-01"

REBAL_DAYS = (2, 5, 10)
MAX_POSITIONS = (5, 8, 10)
LEVERAGES = (1.0, 1.3, 1.5, 2.0)


@dataclass
class ConfigResult:
    score_variant: str
    rebal_days: int
    max_positions: int
    leverage: float
    n_windows: int
    p10_ret: float
    p25_ret: float
    p50_ret: float
    p75_ret: float
    p90_ret: float
    mean_ret: float
    p50_ulcer: float
    p50_max_dd: float
    p25_max_dd: float
    pct_positive: float
    pct_in_cash_avg: float


def simulate_window(
    window_start: int,
    prices: np.ndarray,
    score_arr: np.ndarray,
    breadth: np.ndarray,
    rebal_days: int,
    max_positions: int,
    leverage: float,
    window_days: int = WINDOW_DAYS,
) -> tuple[float, float, float, float] | None:
    """Run one config over one forward window of `window_days`.

    Returns (ret, ulcer, max_dd, pct_in_cash) or None if window invalid.
    """
    n_days, n_tick = prices.shape
    end = min(window_start + window_days, n_days)
    days = end - window_start
    if days < 21:
        return None

    daily_yield = (1 + CASH_YIELD_ANNUAL) ** (1 / 252) - 1
    daily_debit = (1 + MARGIN_DEBIT_ANNUAL) ** (1 / 252) - 1
    turnover_cost = TURNOVER_BPS / 10_000

    equity = np.empty(days + 1)
    equity[0] = 1.0
    cash = 1.0
    shares = np.zeros(n_tick)
    days_in_cash = 0

    for offset in range(days):
        t = window_start + offset
        held_value = float(np.nansum(shares * prices[t])) if shares.any() else 0.0
        port_value = held_value + cash
        equity[offset] = port_value

        cash *= 1 + (daily_yield if cash > 0 else daily_debit)
        if not shares.any():
            days_in_cash += 1

        if offset % rebal_days != 0:
            continue

        # Refresh port_value after cash accrual
        port_value = float(np.nansum(shares * prices[t])) + cash if shares.any() else cash

        if breadth[t] < BREADTH_THRESHOLD:
            cash = port_value
            shares = np.zeros(n_tick)
            continue

        sc = score_arr[t].copy()
        sc[~np.isfinite(sc)] = -np.inf
        # Also require live price
        sc[~np.isfinite(prices[t]) | (prices[t] <= 0)] = -np.inf
        # Long-only: positive scores
        sc = np.where(sc > 0, sc, -np.inf)

        n_valid = int(np.isfinite(sc).sum())
        if n_valid == 0:
            cash = port_value
            shares = np.zeros(n_tick)
            continue

        n_pick = min(max_positions, n_valid)
        if n_pick <= 0:
            cash = port_value
            shares = np.zeros(n_tick)
            continue

        if n_pick < n_tick:
            top_idx = np.argpartition(-sc, n_pick - 1)[:n_pick]
        else:
            top_idx = np.arange(n_tick)
        top_idx = top_idx[np.isfinite(sc[top_idx])]
        if len(top_idx) == 0:
            cash = port_value
            shares = np.zeros(n_tick)
            continue

        # Apply turnover cost on rebal (always full turnover to keep model simple)
        port_value -= port_value * leverage * turnover_cost

        deploy = port_value * leverage
        per_pos = deploy / len(top_idx)
        new_shares = np.zeros(n_tick)
        new_shares[top_idx] = per_pos / prices[t, top_idx]
        shares = new_shares
        cash = port_value - per_pos * len(top_idx)

    # Final mark
    t_final = window_start + days - 1
    held_value = float(np.nansum(shares * prices[t_final])) if shares.any() else 0.0
    equity[days] = held_value + cash

    ret = float(equity[-1] / equity[0] - 1)
    rmax = np.maximum.accumulate(equity)
    dd = (equity - rmax) / rmax
    ulcer = float(np.sqrt((dd ** 2).mean()))
    max_dd = float(dd.min())
    pct_in_cash = days_in_cash / days
    return ret, ulcer, max_dd, pct_in_cash


def run_one_config(args) -> dict:
    """Worker: one (score, rebal, max_pos, lev) config across all windows."""
    score_name, rebal, max_pos, lev, prices, scores_dict, breadth, window_starts, window_days = args
    score_arr = scores_dict[score_name]
    rets, ulcers, max_dds, pct_cash_list = [], [], [], []
    for ws in window_starts:
        out = simulate_window(ws, prices, score_arr, breadth, rebal, max_pos, lev, window_days)
        if out is None:
            continue
        rets.append(out[0])
        ulcers.append(out[1])
        max_dds.append(out[2])
        pct_cash_list.append(out[3])

    if not rets:
        return None
    arr = np.asarray(rets)
    return {
        "score_variant": score_name,
        "rebal_days": rebal,
        "max_positions": max_pos,
        "leverage": lev,
        "n_windows": len(arr),
        "p10_ret": float(np.percentile(arr, 10)),
        "p25_ret": float(np.percentile(arr, 25)),
        "p50_ret": float(np.percentile(arr, 50)),
        "p75_ret": float(np.percentile(arr, 75)),
        "p90_ret": float(np.percentile(arr, 90)),
        "mean_ret": float(arr.mean()),
        "p50_ulcer": float(np.percentile(ulcers, 50)),
        "p50_max_dd": float(np.percentile(max_dds, 50)),
        "p25_max_dd": float(np.percentile(max_dds, 25)),
        "pct_positive": float((arr > 0).mean()),
        "pct_in_cash_avg": float(np.mean(pct_cash_list)),
    }


def filter_to_start_date(prices_df: pl.DataFrame, start_date: str) -> pl.DataFrame:
    """Keep rows from `start_date` onward (string YYYY-MM-DD)."""
    return prices_df.filter(pl.col("date") >= start_date)


@click.command()
@click.option("--period", default="max", help="yfinance period.")
@click.option("--start-date", default=START_DATE_DEFAULT, help="First date to start rolling windows.")
@click.option("--window-days", default=WINDOW_DAYS, type=int, help="Forward holding window in trading days (63=3M, 126=6M).")
@click.option("--label", default="3m", help="Label for output files (e.g. '3m', '6m').")
@click.option("--quick", is_flag=True, help="Tiny sweep for dev iteration.")
@click.option("--workers", default=None, type=int, help="Parallel workers (default: cpu_count).")
def main(period: str, start_date: str, window_days: int, label: str, quick: bool, workers: int | None):
    console.print(f"[bold cyan]Return Maximizer Sweep — window={window_days}d ({label})[/]")
    console.print(f"  period={period}  start_date={start_date}  quick={quick}\n")

    console.print("Fetching data (this can take a few min on cold cache)...")
    prices_df, _, _ = fetch_total_return_index(TICKERS, period=period)
    if prices_df.is_empty():
        console.print("[red]No data fetched[/]")
        return
    prices_df = filter_to_start_date(prices_df, start_date).sort("date")
    console.print(f"  Universe: {len(prices_df.columns) - 1} tickers × {len(prices_df)} days "
                  f"({prices_df['date'][0]} → {prices_df['date'][-1]})")

    # Drop benchmark + ffill
    drop_cols = [c for c in BENCHMARK_TICKERS if c in prices_df.columns]
    if drop_cols:
        prices_df = prices_df.drop(drop_cols)
    price_arrays = ffill_columns(prices_df)
    tickers = sorted(price_arrays)
    prices = np.column_stack([price_arrays[t] for t in tickers])
    n_days = prices.shape[0]
    console.print(f"  Matrix shape: {prices.shape}\n")

    console.print("Precomputing scores...")
    scores_dict, breadth = precompute_scores(prices)
    console.print(f"  Done. Breadth: P10={np.percentile(breadth[WARMUP_DAYS:], 10):.0%} "
                  f"P50={np.percentile(breadth[WARMUP_DAYS:], 50):.0%} "
                  f"P90={np.percentile(breadth[WARMUP_DAYS:], 90):.0%}\n")

    window_starts = list(range(WARMUP_DAYS, n_days - window_days + 1, STEP_DAYS))
    console.print(f"  {len(window_starts)} forward {window_days}d windows (step {STEP_DAYS}d)\n")

    if quick:
        score_grid = ("score_4w", "score_tilt", "score_sortino")
        rebal_grid = (5, 10)
        pos_grid = (5, 10)
        lev_grid = (1.0, 1.5)
    else:
        score_grid = SCORE_VARIANTS
        rebal_grid = REBAL_DAYS
        pos_grid = MAX_POSITIONS
        lev_grid = LEVERAGES

    configs = list(product(score_grid, rebal_grid, pos_grid, lev_grid))
    console.print(f"[bold cyan]Running {len(configs)} configs × {len(window_starts)} windows...[/]\n")

    args_list = [
        (score, rebal, mp, lev, prices, scores_dict, breadth, window_starts, window_days)
        for (score, rebal, mp, lev) in configs
    ]

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one_config, a): a for a in args_list}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            done += 1
            if r is not None:
                results.append(r)
            if done % 20 == 0 or done == len(configs):
                console.print(f"  [{done}/{len(configs)}] complete")

    if not results:
        console.print("[red]No results[/]")
        return

    # Sort + report
    results.sort(key=lambda r: -r["p75_ret"])
    top20 = results[:20]

    table = Table(title=f"Top 20 Configs by P75 of {window_days}-Day Return")
    for col in ["#", "score", "rebal", "pos", "lev", "P50", "P75", "P90", "Mean",
                "Ulc P50", "DD P50", "Win%", "Cash%"]:
        table.add_column(col, justify="right" if col != "score" else "left")
    for i, r in enumerate(top20, 1):
        table.add_row(
            str(i),
            r["score_variant"].replace("score_", ""),
            f"{r['rebal_days']}d",
            str(r["max_positions"]),
            f"{r['leverage']:.1f}x",
            f"{r['p50_ret']*100:+.1f}%",
            f"{r['p75_ret']*100:+.1f}%",
            f"{r['p90_ret']*100:+.1f}%",
            f"{r['mean_ret']*100:+.1f}%",
            f"{r['p50_ulcer']*100:.1f}%",
            f"{r['p50_max_dd']*100:.0f}%",
            f"{r['pct_positive']*100:.0f}%",
            f"{r['pct_in_cash_avg']*100:.0f}%",
        )
    console.print(table)

    # Best by Ulcer-adjusted P75
    by_ulcer_p75 = sorted(results, key=lambda r: -r["p75_ret"] / max(r["p50_ulcer"], 0.01))
    console.print("\n[bold]Top 5 by P75 / P50_Ulcer (return-per-pain):[/]")
    for r in by_ulcer_p75[:5]:
        console.print(f"  {r['score_variant']:>14s} × {r['rebal_days']:>2d}d × pos={r['max_positions']} × lev={r['leverage']:.1f}x  "
                      f"P75={r['p75_ret']*100:+.1f}%  Ulc={r['p50_ulcer']*100:.1f}%  "
                      f"ratio={r['p75_ret']/max(r['p50_ulcer'], 0.01):.1f}")

    HERE.mkdir(parents=True, exist_ok=True)
    out_json = HERE / f"return_max_{label}_results.json"
    with out_json.open("w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "period": period,
            "start_date": start_date,
            "quick": quick,
            "n_configs": len(results),
            "n_windows": len(window_starts),
            "window_days": WINDOW_DAYS,
            "step_days": STEP_DAYS,
            "breadth_threshold": BREADTH_THRESHOLD,
            "turnover_bps": TURNOVER_BPS,
            "cash_yield_annual": CASH_YIELD_ANNUAL,
            "margin_debit_annual": MARGIN_DEBIT_ANNUAL,
            "results": results,
        }, f, indent=2)
    console.print(f"\n[green]Wrote {out_json}[/]")

    # Markdown report
    DOCS.mkdir(parents=True, exist_ok=True)
    out_md = DOCS / f"return_max_{label}_strategy.md"
    by_p75 = sorted(results, key=lambda r: -r["p75_ret"])
    by_p50 = sorted(results, key=lambda r: -r["p50_ret"])
    by_p90 = sorted(results, key=lambda r: -r["p90_ret"])
    by_ratio = sorted(results, key=lambda r: -r["p75_ret"] / max(r["p50_ulcer"], 0.005))

    def fmt_row(r: dict) -> str:
        return (
            f"| {r['score_variant'].replace('score_',''):>7s} "
            f"| {r['rebal_days']:>2d}d | {r['max_positions']} | {r['leverage']:.1f}x "
            f"| {r['p10_ret']*100:+.1f}% | {r['p25_ret']*100:+.1f}% | {r['p50_ret']*100:+.1f}% "
            f"| {r['p75_ret']*100:+.1f}% | {r['p90_ret']*100:+.1f}% "
            f"| {r['p50_ulcer']*100:.1f}% | {r['p50_max_dd']*100:.0f}% "
            f"| {r['pct_positive']*100:.0f}% | {r['pct_in_cash_avg']*100:.0f}% |"
        )

    md = [
        f"# Tactical Return Maximizer — {window_days}d ({label})",
        "",
        f"**Generated:** {datetime.now().date()}  ",
        f"**Period:** {period} (start {start_date})  ",
        f"**Validation:** {len(window_starts)} rolling {window_days}-day forward windows (step {STEP_DAYS}d)  ",
        f"**Universe:** {prices.shape[1]} tickers  ",
        f"**Configs swept:** {len(results)} = {len(SCORE_VARIANTS)} scores × {len(REBAL_DAYS)} rebal × {len(MAX_POSITIONS)} pos × {len(LEVERAGES)} lev  ",
        "",
        "## Costs Modeled",
        "- 5 bps turnover per rebal × leverage (IBKR-realistic)",
        f"- {MARGIN_DEBIT_ANNUAL*100:.1f}% annual margin debit on negative cash",
        f"- {CASH_YIELD_ANNUAL*100:.1f}% annual yield on positive cash",
        f"- Breadth gate: cash if <{BREADTH_THRESHOLD*100:.0f}% of universe has positive 4W mom",
        "",
        f"## Top 15 by P75 of {window_days}-day return",
        "",
        "| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in by_p75[:15]:
        md.append(fmt_row(r))

    md += ["", "## Top 10 by P50 (median outcome)", "",
           "| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in by_p50[:10]:
        md.append(fmt_row(r))

    md += ["", "## Top 10 by P90 (right-tail jackpot)", "",
           "| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in by_p90[:10]:
        md.append(fmt_row(r))

    md += ["", "## Top 10 by P75 / Ulcer (return-per-pain)", "",
           "| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in by_ratio[:10]:
        md.append(fmt_row(r))

    md += [
        "",
        "## Aggregates by Score Variant (best lev/pos/rebal per variant on P75)",
        "",
        "| score | best rebal | best pos | best lev | P50 | P75 | P90 | Ulcer P50 | Win% |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    by_score: dict[str, dict] = {}
    for r in results:
        cur = by_score.get(r["score_variant"])
        if cur is None or r["p75_ret"] > cur["p75_ret"]:
            by_score[r["score_variant"]] = r
    for sv in SCORE_VARIANTS:
        r = by_score.get(sv)
        if r is None:
            continue
        md.append(
            f"| {sv.replace('score_',''):>7s} | {r['rebal_days']}d | {r['max_positions']} | "
            f"{r['leverage']:.1f}x | {r['p50_ret']*100:+.1f}% | {r['p75_ret']*100:+.1f}% | "
            f"{r['p90_ret']*100:+.1f}% | {r['p50_ulcer']*100:.1f}% | {r['pct_positive']*100:.0f}% |"
        )

    md += [
        "",
        "## Aggregates by Leverage (best score/pos/rebal per leverage)",
        "",
        "| lev | best score | rebal | pos | P50 | P75 | P90 | Ulcer P50 | DD P50 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    by_lev: dict[float, dict] = {}
    for r in results:
        cur = by_lev.get(r["leverage"])
        if cur is None or r["p75_ret"] > cur["p75_ret"]:
            by_lev[r["leverage"]] = r
    for lev in LEVERAGES:
        r = by_lev.get(lev)
        if r is None:
            continue
        md.append(
            f"| {lev:.1f}x | {r['score_variant'].replace('score_','')} | {r['rebal_days']}d | "
            f"{r['max_positions']} | {r['p50_ret']*100:+.1f}% | {r['p75_ret']*100:+.1f}% | "
            f"{r['p90_ret']*100:+.1f}% | {r['p50_ulcer']*100:.1f}% | {r['p50_max_dd']*100:.0f}% |"
        )

    out_md.write_text("\n".join(md) + "\n")
    console.print(f"[green]Wrote {out_md}[/]")


if __name__ == "__main__":
    main()
