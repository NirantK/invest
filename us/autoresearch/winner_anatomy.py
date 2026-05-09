"""
Winner anatomy: for the top 10 absolute winners over the 3Y window, dissect what
signals were visible BEFORE each broke out. Tests whether our screener would have
caught them in time.

Output:
- For each big winner: the per-month rank (out of universe) by score_sortino,
  score_rank, mom_12m, dvol_slope at each rebalance date.
- Cross-table: are top winners systematically high-ranked? Where did we miss?
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "us" / "scripts"))

from backtest_v2 import _build_scores_at, fetch_total_return_index  # type: ignore
from us_portfolio_allocation import TICKERS, add_rank_scores  # type: ignore

console = Console()
HERE = Path(__file__).parent


def main():
    console.print("[bold]Fetching 3Y data...[/]")
    prices, closes, dvols = fetch_total_return_index(TICKERS, period="3y")
    console.print(f"  {len(prices.columns)-1} tickers, {len(prices)} days")

    n = len(prices)
    if n < 252 + 252:
        console.print("[red]Need ≥504 days for full anatomy. Aborting.[/]")
        return

    # Compute total return over the WHOLE 3Y window per ticker (point estimate)
    tickers = [c for c in prices.columns if c != "date"]
    final_returns = {}
    for t in tickers:
        arr = prices[t].drop_nulls().to_numpy()
        if len(arr) < 100:
            continue
        # Use first valid → last value
        final_returns[t] = arr[-1] / arr[0] - 1

    # Top winners over the period
    sorted_returns = sorted(final_returns.items(), key=lambda kv: -kv[1])
    top_n = sorted_returns[:15]
    console.print(f"\n[bold]Top 15 absolute winners 3Y total return:[/]")
    for t, r in top_n:
        console.print(f"  {t:<8} {r*100:>+8.1f}%")

    # For each rebalance date (every 21d from day 252 onwards), score and rank.
    # Track for each top winner: rank at each rebalance date.
    rebal_dates = list(range(252, n, 21))
    console.print(f"\n[bold]Rebalance dates evaluated: {len(rebal_dates)}[/]")

    # We'll record per top-winner: timeline of (date_idx, score, rank_pct, mom_12m, dvol_slope, dist52)
    top_winners = [t for t, _ in top_n]
    timeline: dict[str, list[dict]] = {t: [] for t in top_winners}

    for d_idx in rebal_dates:
        scores = _build_scores_at(prices.head(d_idx + 1), closes.head(d_idx + 1), dvols.head(d_idx + 1))
        if scores.is_empty():
            continue
        # Filter to positive momentum only (matches what allocator sees)
        positive = scores.filter(pl.col("wt_mom") > 0)
        if positive.is_empty():
            continue
        positive = add_rank_scores(positive)
        # Rank by score_sortino (our top performer)
        ranked = positive.sort("score_sortino", descending=True).with_row_index("rank_sortino")
        ranked = ranked.with_columns((pl.col("rank_sortino") + 1).alias("rank_sortino"))
        # Also rank by score_rank
        ranked2 = positive.sort("score_rank", descending=True).with_row_index("rank_rank")
        rank_rank_map = {row["ticker"]: row["rank_rank"] + 1 for row in ranked2.iter_rows(named=True)}

        for row in ranked.iter_rows(named=True):
            t = row["ticker"]
            if t not in timeline:
                continue
            timeline[t].append({
                "d_idx": d_idx,
                "rank_sortino": row["rank_sortino"],
                "rank_rank": rank_rank_map.get(t, 0),
                "score_sortino": row.get("score_sortino", 0),
                "score_rank": row.get("score_rank", 0),
                "mom_12m": row.get("mom_12m", 0),
                "wt_mom": row.get("wt_mom", 0),
                "dvol_slope": row.get("dv_slope", 0),
                "dist52": row.get("dist52", 1),
                "smoothness": row.get("smoothness", 0),
                "current_dd": row.get("current_dd", 0),
                "ulcer_1y": row.get("ulcer_1y", 0),
            })

    # Build summary table
    table = Table(title="Winner Anatomy — Avg Pre-Breakout Signals (across rebalance windows)")
    table.add_column("Ticker", style="cyan")
    table.add_column("3Y Tot Ret", justify="right")
    table.add_column("AvgRank Sortino", justify="right")
    table.add_column("BestRank", justify="right")
    table.add_column("AvgMom 12m", justify="right")
    table.add_column("AvgDvol", justify="right")
    table.add_column("AvgD52", justify="right")
    table.add_column("AvgUlcer", justify="right")
    table.add_column("N obs", justify="right")

    rows_for_md = []
    for t, total_ret in top_n:
        obs = timeline.get(t, [])
        if not obs:
            continue
        avg_rank = np.mean([o["rank_sortino"] for o in obs])
        best_rank = min(o["rank_sortino"] for o in obs)
        avg_mom = np.mean([o["mom_12m"] for o in obs])
        avg_dvol = np.mean([o["dvol_slope"] for o in obs])
        avg_d52 = np.mean([o["dist52"] for o in obs])
        avg_ulcer = np.mean([o["ulcer_1y"] for o in obs])
        table.add_row(
            t, f"{total_ret*100:+.0f}%",
            f"{avg_rank:.0f}",
            f"{best_rank}",
            f"{avg_mom*100:+.0f}%",
            f"{avg_dvol:+.2f}",
            f"{avg_d52*100:.0f}%",
            f"{avg_ulcer*100:.0f}%",
            f"{len(obs)}",
        )
        rows_for_md.append({
            "ticker": t, "total_return": total_ret, "avg_rank_sortino": float(avg_rank),
            "best_rank": int(best_rank), "avg_mom_12m": float(avg_mom),
            "avg_dvol_slope": float(avg_dvol), "avg_dist52": float(avg_d52),
            "avg_ulcer_1y": float(avg_ulcer), "n_observations": len(obs),
        })

    console.print(table)

    # Cross-question: of all rebalances where a top winner was in the top-15, how often were we picking it?
    # Coverage rate = how often were the actual winners IN our top 15 selections
    coverage = {}
    for t in top_winners:
        obs = timeline.get(t, [])
        if not obs:
            continue
        in_top_15 = sum(1 for o in obs if o["rank_sortino"] <= 15)
        coverage[t] = (in_top_15, len(obs))

    console.print("\n[bold]Coverage — how often each big winner was already in our top-15:[/]")
    cov_table = Table()
    cov_table.add_column("Ticker", style="cyan")
    cov_table.add_column("In Top 15", justify="right")
    cov_table.add_column("Out of", justify="right")
    cov_table.add_column("Hit Rate", justify="right")
    for t, (hit, total) in coverage.items():
        cov_table.add_row(t, str(hit), str(total), f"{hit/total*100:.0f}%")
    console.print(cov_table)

    # Write markdown summary
    out = HERE / "winner_anatomy.md"
    md = [
        f"# Winner Anatomy — {datetime.now().date()}",
        "",
        f"For the top 15 absolute winners over the 3Y window, this analysis shows the average rank",
        f"and signal values across all monthly rebalance points (warmup excluded).",
        "",
        f"**Universe size:** {len(prices.columns)-1} tickers",
        f"**Rebalance dates evaluated:** {len(rebal_dates)} (monthly)",
        "",
        "## Top 15 winners",
        "",
        "| Ticker | 3Y Return | Avg Rank | Best Rank | Avg Mom12 | Avg Dvol | Avg D52 | Avg Ulcer | Obs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows_for_md:
        md.append(
            f"| {r['ticker']} | {r['total_return']*100:+.0f}% | {r['avg_rank_sortino']:.0f} | "
            f"{r['best_rank']} | {r['avg_mom_12m']*100:+.0f}% | {r['avg_dvol_slope']:+.2f} | "
            f"{r['avg_dist52']*100:.0f}% | {r['avg_ulcer_1y']*100:.0f}% | {r['n_observations']} |"
        )
    md += ["", "## Coverage (% of rebalances where the winner was in our top 15)", "",
           "| Ticker | Hit Rate |", "|---|---|"]
    for t, (hit, total) in coverage.items():
        md.append(f"| {t} | {hit}/{total} = {hit/total*100:.0f}% |")
    md += ["", "## Mechanism Read", "",
           "If a winner has Avg Rank ≤ 15, our screener picked it consistently → it contributed to returns.",
           "If a winner has Avg Rank > 15, we MISSED it → upside left on the table.",
           "Patterns in their pre-breakout signals (Mom12, Dvol, D52) reveal what predictive features we should weight more."]

    out.write_text("\n".join(md))
    console.print(f"\n[green]Wrote {out}[/]")


if __name__ == "__main__":
    main()
