"""
Regime sensitivity: roll 3Y backtest windows over 10+ years to test if S12 × 10d
holds up across different market regimes (2014-2017 grind, 2018 vol, 2020 COVID,
2022 bear, 2023-2026 AI bull, etc.).

Per window:
  - Filter universe to tickers with full window data (avoids survivorship bias)
  - Run S12_no_inpain × 10d
  - Record CAGR, Martin, Ulcer, MaxDD
  - Classify regime by SPY's window return

Aggregate:
  - Distribution of metrics across all windows
  - Performance by regime class (bull / neutral / bear)
  - Where the strategy failed
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import click
import numpy as np
import polars as pl
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "us" / "scripts"))

from backtest_v2 import run_backtest, fetch_total_return_index  # type: ignore
from us_portfolio_allocation import TICKERS, BENCHMARK_TICKERS  # type: ignore

console = Console()
HERE = Path(__file__).parent

PERIODS_PER_YEAR = 252
TRAIN_DAYS = 3 * PERIODS_PER_YEAR     # 3Y window length (post-warmup)
WARMUP_DAYS = PERIODS_PER_YEAR         # 1Y warmup at window start
TOTAL_WINDOW = WARMUP_DAYS + TRAIN_DAYS  # 4Y total span per window
STEP_DAYS = PERIODS_PER_YEAR // 2      # step every 6 months


@dataclass
class WindowResult:
    window_idx: int
    start_date: str
    end_date: str
    n_tickers_avail: int
    spy_window_return: float
    regime_class: str
    cagr: float
    martin: float
    ulcer: float
    max_dd: float
    sharpe: float
    avg_positions: float
    n_rebalances: int


def classify_regime(spy_return_3y: float) -> str:
    """Bull: SPY +30% over 3Y. Bear: SPY <0%. Neutral: in between."""
    cagr = (1 + spy_return_3y) ** (1 / 3) - 1
    if cagr >= 0.10:
        return "bull"
    if cagr <= 0.0:
        return "bear"
    return "neutral"


def slice_window(df: pl.DataFrame, start: int, end: int) -> pl.DataFrame:
    """Slice to row range [start:end]. Drops columns that are all-null in the window."""
    sliced = df[start:end]
    keep = ["date"] + [
        col for col in sliced.columns
        if col != "date" and sliced[col].drop_nulls().len() >= 0.9 * (end - start)
    ]
    return sliced.select(keep)


def run_window(prices: pl.DataFrame, closes: pl.DataFrame, dvols: pl.DataFrame,
               start: int, end: int, window_idx: int) -> WindowResult | None:
    p = slice_window(prices, start, end)
    c = slice_window(closes, start, end)
    v = slice_window(dvols, start, end)
    if len(p) < TOTAL_WINDOW * 0.95:
        return None

    n_tickers = len(p.columns) - 1
    if n_tickers < 30:
        return None

    spy_col = "SPY" if "SPY" in p.columns else None
    spy_return = 0.0
    if spy_col:
        spy_arr = p[spy_col].drop_nulls().to_numpy()
        if len(spy_arr) > WARMUP_DAYS:
            spy_post_warmup = spy_arr[WARMUP_DAYS:]
            if len(spy_post_warmup) > 0:
                spy_return = spy_post_warmup[-1] / spy_post_warmup[0] - 1

    result = run_backtest(
        p, c, v,
        score_col="score_sortino", sizing="equal", rebal_days=10,
        capital=100_000.0, max_positions=15, max_pct=0.15, min_pct=0.03,
        warmup_days=WARMUP_DAYS,
        min_adv=0, current_dd_floor=-1.0, use_sleeve_caps=True, leverage=1.0,
    )

    return WindowResult(
        window_idx=window_idx,
        start_date=p["date"][0],
        end_date=p["date"][-1],
        n_tickers_avail=n_tickers,
        spy_window_return=float(spy_return),
        regime_class=classify_regime(spy_return),
        cagr=result.cagr, martin=result.martin, ulcer=result.ulcer,
        max_dd=result.max_dd, sharpe=result.sharpe,
        avg_positions=result.avg_positions, n_rebalances=result.n_rebalances,
    )


def percentiles(values: list[float]) -> dict[str, float]:
    a = np.asarray(values)
    return {
        "p10": float(np.percentile(a, 10)),
        "p25": float(np.percentile(a, 25)),
        "p50": float(np.percentile(a, 50)),
        "p75": float(np.percentile(a, 75)),
        "p90": float(np.percentile(a, 90)),
        "mean": float(np.mean(a)),
        "min": float(np.min(a)),
        "max": float(np.max(a)),
    }


@click.command()
@click.option("--period", default="max",
              help="yfinance period string (max, 10y, 15y).")
@click.option("--step-months", default=6, type=int,
              help="Step between window starts (months).")
def main(period, step_months):
    console.print(f"[bold cyan]Regime Sensitivity Sweep — period={period}[/]")

    console.print("Fetching long-history data (this takes a few min)...")
    prices, closes, dvols = fetch_total_return_index(TICKERS, period=period)
    n_days = len(prices)
    console.print(f"  Fetched {len(prices.columns) - 1} tickers × {n_days} days "
                  f"({prices['date'][0]} → {prices['date'][-1]})")

    if n_days < TOTAL_WINDOW:
        console.print(f"[red]Insufficient data: {n_days} < {TOTAL_WINDOW}[/]")
        return

    step = step_months * (PERIODS_PER_YEAR // 12)
    starts = list(range(0, n_days - TOTAL_WINDOW + 1, step))
    console.print(f"  Running {len(starts)} rolling 3Y windows (step {step_months}mo)...\n")

    results: list[WindowResult] = []
    for i, start in enumerate(starts, 1):
        end = start + TOTAL_WINDOW
        wr = run_window(prices, closes, dvols, start, end, i)
        if wr is None:
            console.print(f"  [{i:2d}/{len(starts)}] {prices['date'][start]} skipped (insufficient data)")
            continue
        results.append(wr)
        console.print(f"  [{i:2d}/{len(starts)}] "
                      f"{wr.start_date}→{wr.end_date}  "
                      f"univ={wr.n_tickers_avail:>3d}  SPY3Y={wr.spy_window_return*100:>+5.0f}%({wr.regime_class:>7s})  "
                      f"CAGR={wr.cagr*100:>+5.0f}%  Martin={wr.martin:>5.2f}  "
                      f"Ulc={wr.ulcer*100:>4.1f}%  DD={wr.max_dd*100:>4.0f}%")

    if not results:
        console.print("[red]No valid windows[/]")
        return

    cagrs = [r.cagr for r in results]
    martins = [r.martin for r in results]
    ulcers = [r.ulcer for r in results]
    max_dds = [r.max_dd for r in results]

    table = Table(title="Distribution Across Windows")
    for col in ["Metric", "min", "P10", "P25", "P50", "P75", "P90", "max", "mean"]:
        table.add_column(col, justify="right" if col != "Metric" else "left")
    for label, vals, fmt in [
        ("CAGR", cagrs, lambda v: f"{v*100:.0f}%"),
        ("Martin", martins, lambda v: f"{v:.2f}"),
        ("Ulcer", ulcers, lambda v: f"{v*100:.1f}%"),
        ("MaxDD", max_dds, lambda v: f"{v*100:.0f}%"),
    ]:
        p = percentiles(vals)
        table.add_row(label, fmt(p['min']), fmt(p['p10']), fmt(p['p25']),
                       fmt(p['p50']), fmt(p['p75']), fmt(p['p90']),
                       fmt(p['max']), fmt(p['mean']))
    console.print(table)

    by_regime: dict[str, list[WindowResult]] = {"bull": [], "neutral": [], "bear": []}
    for r in results:
        by_regime[r.regime_class].append(r)

    console.print("\n[bold]By regime class (SPY 3Y CAGR):[/]")
    rt = Table()
    for col in ["Regime", "N", "CAGR P10", "CAGR P50", "CAGR P90", "Martin P50", "Ulcer P50", "MaxDD P50"]:
        rt.add_column(col, justify="right" if col != "Regime" else "left")
    for regime, group in by_regime.items():
        if not group:
            continue
        gc = [r.cagr for r in group]
        gm = [r.martin for r in group]
        gu = [r.ulcer for r in group]
        gd = [r.max_dd for r in group]
        rt.add_row(regime, str(len(group)),
                    f"{np.percentile(gc, 10)*100:+.0f}%",
                    f"{np.percentile(gc, 50)*100:+.0f}%",
                    f"{np.percentile(gc, 90)*100:+.0f}%",
                    f"{np.percentile(gm, 50):.2f}",
                    f"{np.percentile(gu, 50)*100:.1f}%",
                    f"{np.percentile(gd, 50)*100:.0f}%")
    console.print(rt)

    out_json = HERE / "regime_sensitivity_results.json"
    with out_json.open("w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "period": period, "step_months": step_months,
            "n_windows": len(results),
            "results": [asdict(r) for r in results],
            "distribution": {
                "cagr": percentiles(cagrs),
                "martin": percentiles(martins),
                "ulcer": percentiles(ulcers),
                "max_dd": percentiles(max_dds),
            },
        }, f, indent=2)

    out_md = HERE / "regime_sensitivity.md"
    md_lines = [
        f"# Regime Sensitivity — S12_no_inpain × 10d",
        f"",
        f"**Generated:** {datetime.now().date()}  ",
        f"**Period:** {period} (yfinance)  ",
        f"**Universe:** 162 tickers (filtered per window to avoid survivorship bias)  ",
        f"**Step:** {step_months} months  ",
        f"**Windows:** {len(results)}  ",
        f"",
        f"## Per-Window Results",
        f"",
        f"| # | Start | End | Univ | SPY 3Y | Regime | CAGR | Martin | Ulcer | MaxDD |",
        f"|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        md_lines.append(
            f"| {r.window_idx} | {r.start_date} | {r.end_date} | {r.n_tickers_avail} | "
            f"{r.spy_window_return*100:+.0f}% | {r.regime_class} | {r.cagr*100:+.0f}% | "
            f"{r.martin:.2f} | {r.ulcer*100:.1f}% | {r.max_dd*100:.0f}% |"
        )
    md_lines += ["", "## Distribution", "", "| Metric | min | P10 | P25 | P50 | P75 | P90 | max | mean |",
                  "|---|---|---|---|---|---|---|---|---|"]
    for label, vals, fmt in [
        ("CAGR", cagrs, lambda v: f"{v*100:.0f}%"),
        ("Martin", martins, lambda v: f"{v:.2f}"),
        ("Ulcer", ulcers, lambda v: f"{v*100:.1f}%"),
        ("MaxDD", max_dds, lambda v: f"{v*100:.0f}%"),
    ]:
        p = percentiles(vals)
        md_lines.append(
            f"| {label} | {fmt(p['min'])} | {fmt(p['p10'])} | {fmt(p['p25'])} | "
            f"{fmt(p['p50'])} | {fmt(p['p75'])} | {fmt(p['p90'])} | {fmt(p['max'])} | {fmt(p['mean'])} |"
        )

    md_lines += ["", "## By Regime", "", "| Regime | N windows | CAGR P10 | P50 | P90 | Martin P50 | Ulcer P50 | MaxDD P50 |",
                  "|---|---|---|---|---|---|---|---|"]
    for regime, group in by_regime.items():
        if not group:
            continue
        gc = [r.cagr for r in group]
        gm = [r.martin for r in group]
        gu = [r.ulcer for r in group]
        gd = [r.max_dd for r in group]
        md_lines.append(
            f"| {regime} | {len(group)} | {np.percentile(gc, 10)*100:+.0f}% | "
            f"{np.percentile(gc, 50)*100:+.0f}% | {np.percentile(gc, 90)*100:+.0f}% | "
            f"{np.percentile(gm, 50):.2f} | {np.percentile(gu, 50)*100:.1f}% | "
            f"{np.percentile(gd, 50)*100:.0f}% |"
        )

    out_md.write_text("\n".join(md_lines))
    console.print(f"\n[green]Wrote {out_json} and {out_md}[/]")


if __name__ == "__main__":
    main()
