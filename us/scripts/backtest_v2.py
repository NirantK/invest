"""
Multi-score backtest harness for the V2 US screener.

Cross-product sweep: {score_col} × {sizing} × {rebal_days}.
Walk-forward, write JSON + markdown summary.

Engine in `invest.backtest`; this file is the US-specific runner.
"""

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

from us_portfolio_allocation import (  # type: ignore
    TICKERS, fetch_total_return_index, BENCHMARK_TICKERS,
    apply_thesis_groups, apply_sleeve_caps, allocate as us_allocate,
)
from invest.backtest import BacktestConfig, BacktestResult, run_backtest as _run
from invest.allocate import add_rank_scores

console = Console()


def us_allocator(scores, deploy, cfg: BacktestConfig):
    """Bind US sleeve config to the shared engine's allocator interface."""
    scores2 = add_rank_scores(scores)
    scores2, _ = apply_thesis_groups(scores2, score_col=cfg.score_col)
    if scores2.is_empty():
        return scores2
    alloc = us_allocate(scores2, deploy, cfg.min_pct, cfg.max_pct,
                        cfg.max_positions, score_col=cfg.score_col, sizing=cfg.sizing)
    if alloc.is_empty() or not cfg.use_sleeve_caps:
        return alloc
    alloc, _ = apply_sleeve_caps(alloc, scores2, deploy, cfg.min_pct, cfg.max_pct,
                                  cfg.max_positions, cfg.score_col, cfg.sizing)
    return alloc


def run_backtest(prices, closes, dvols, score_col: str, sizing: str, rebal_days: int,
                 **kwargs) -> BacktestResult:
    """US-flavoured wrapper: builds a BacktestConfig from kwargs, calls shared engine."""
    cfg = BacktestConfig(score_col=score_col, sizing=sizing, rebal_days=rebal_days, **kwargs)
    return _run(prices, closes, dvols, cfg, us_allocator, excluded_tickers=BENCHMARK_TICKERS)


def main():
    console.print("[bold cyan]Fetching data (period=3y)...[/]")
    prices, closes, dvols = fetch_total_return_index(TICKERS, period="3y")
    console.print(f"  Universe: {len(prices.columns) - 1} tickers, {len(prices)} days")

    score_cols = ["score_martin", "score_sortino", "score_rank"]
    sizings = ["raw", "sqrt", "equal"]
    rebal_freqs = [21, 63, 126]  # ~monthly, quarterly, semi

    combos = [(s, sz, r) for s in score_cols for sz in sizings for r in rebal_freqs]
    console.print(f"[bold cyan]Running {len(combos)} backtests...[/]")

    results: list[BacktestResult] = []
    for i, (score_col, sizing, rebal) in enumerate(combos, 1):
        console.print(f"  [{i:2d}/{len(combos)}] {score_col:>14s} × {sizing:>5s} × {rebal:3d}d", end="")
        r = run_backtest(prices, closes, dvols, score_col, sizing, rebal)
        results.append(r)
        console.print(f"  → CAGR={r.cagr*100:5.1f}%  Martin={r.martin:5.2f}  Ulcer={r.ulcer*100:4.1f}%  DD={r.max_dd*100:4.0f}%")

    # Save raw results
    out_data = ROOT / "data" / "backtest_results.json"
    out_data.parent.mkdir(parents=True, exist_ok=True)
    with out_data.open("w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "universe_size": len(TICKERS),
            "results": [asdict(r) for r in results],
        }, f, indent=2)

    # Print + save summary
    results.sort(key=lambda r: -r.martin)
    table = Table(title="Backtest Results — sorted by Martin Ratio (Higher = Better)")
    for col in ["score", "sizing", "rebal", "CAGR", "Martin", "Ulcer", "MaxDD", "Sharpe", "AvgPos"]:
        table.add_column(col, justify="right" if col != "score" else "left")
    for r in results:
        table.add_row(
            r.score_col.replace("score_", ""),
            r.sizing,
            f"{r.rebal_days}d",
            f"{r.cagr*100:.1f}%",
            f"{r.martin:.2f}",
            f"{r.ulcer*100:.1f}%",
            f"{r.max_dd*100:.0f}%",
            f"{r.sharpe:.2f}",
            f"{r.avg_positions:.1f}",
        )
    console.print(table)

    # Markdown summary
    out_md = ROOT / "docs" / "backtest_summary.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with out_md.open("w") as f:
        f.write(f"# V2 Screener Backtest — {datetime.now().date()}\n\n")
        f.write(f"Universe: {len(TICKERS)} tickers. Walk-forward 3Y. 1Y warmup. ${100_000:,} start capital.\n\n")
        f.write("Ranked by Martin Ratio (CAGR / Ulcer Index).\n\n")
        f.write("| Score | Sizing | Rebal | CAGR | Martin | Ulcer | MaxDD | Sharpe | AvgPos |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in results:
            f.write(
                f"| {r.score_col.replace('score_','')} | {r.sizing} | {r.rebal_days}d | "
                f"{r.cagr*100:.1f}% | {r.martin:.2f} | {r.ulcer*100:.1f}% | {r.max_dd*100:.0f}% | "
                f"{r.sharpe:.2f} | {r.avg_positions:.1f} |\n"
            )
        f.write("\n## Top 3\n\n")
        for r in results[:3]:
            f.write(f"- **{r.score_col} × {r.sizing} × {r.rebal_days}d**: "
                    f"CAGR {r.cagr*100:.1f}%, Martin {r.martin:.2f}, Ulcer {r.ulcer*100:.1f}%, "
                    f"MaxDD {r.max_dd*100:.0f}%\n")

    console.print(f"\n[green]Wrote {out_data} and {out_md}[/]")


if __name__ == "__main__":
    main()
