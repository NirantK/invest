"""Live picker for the tactical 6M (or 3M) sleeve.

Takes today's data, computes the score variant from the recommended config,
applies the breadth gate, and prints the top-N tickers + dollar allocation.

Defaults match the 6M Balanced pick: score_4w × 8 positions × 1.5x leverage.
For the 6M Defensive: --leverage 1.0
For the 3M Balanced:  --score score_4w --positions 5 --leverage 1.5
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import numpy as np
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from invest.momentum_3m import precompute_scores, SCORE_VARIANTS  # noqa: E402
from invest.backtest import ffill_columns  # noqa: E402
from us_portfolio_allocation import TICKERS, fetch_total_return_index, BENCHMARK_TICKERS  # noqa: E402

console = Console()
BREADTH_THRESHOLD = 0.30


@click.command()
@click.option("--capital", default=20_000.0, type=float, help="Sleeve capital (USD).")
@click.option("--positions", default=8, type=int, help="Number of positions.")
@click.option("--leverage", default=1.5, type=float, help="Gross leverage (1.0 = unlevered).")
@click.option("--score", default="score_4w", type=click.Choice(list(SCORE_VARIANTS)), help="Score variant.")
@click.option("--period", default="1y", help="yfinance period (1y enough for 8W lookback + buffer).")
def main(capital: float, positions: int, leverage: float, score: str, period: str):
    console.print(f"[bold cyan]Tactical Sleeve Picker[/]")
    console.print(f"  config: {score} × pos={positions} × lev={leverage:.2f}x  capital=${capital:,.0f}\n")

    console.print("Fetching prices...")
    prices_df, _, _ = fetch_total_return_index(TICKERS, period=period)
    drop_cols = [c for c in BENCHMARK_TICKERS if c in prices_df.columns]
    if drop_cols:
        prices_df = prices_df.drop(drop_cols)
    prices_df = prices_df.sort("date")
    last_date = prices_df["date"][-1]
    console.print(f"  As of: {last_date}  (universe: {len(prices_df.columns)-1} tickers)\n")

    price_arrays = ffill_columns(prices_df)
    tickers = sorted(price_arrays)
    prices = np.column_stack([price_arrays[t] for t in tickers])
    scores_dict, breadth = precompute_scores(prices)

    today_breadth = float(breadth[-1])
    sc = scores_dict[score][-1]
    px = prices[-1]
    valid = np.isfinite(sc) & np.isfinite(px) & (px > 0) & (sc > 0)

    console.print(f"  Breadth (4W mom positive): {today_breadth*100:.0f}%  (gate fires at <{BREADTH_THRESHOLD*100:.0f}%)")
    console.print(f"  Universe with positive score: {valid.sum()}\n")

    if today_breadth < BREADTH_THRESHOLD:
        console.print(f"[bold red]BREADTH GATE: HOLD CASH[/]")
        console.print(f"Only {today_breadth*100:.0f}% of universe has positive 4W momentum. Park ${capital:,.0f} in BIL/SGOV/cash.")
        return

    if not valid.any():
        console.print(f"[bold red]No positive scores. HOLD CASH.[/]")
        return

    n_pick = min(positions, int(valid.sum()))
    sc_masked = np.where(valid, sc, -np.inf)
    top_idx = np.argpartition(-sc_masked, n_pick - 1)[:n_pick]
    top_idx = top_idx[np.argsort(-sc_masked[top_idx])]

    deploy = capital * leverage
    per_pos = deploy / n_pick

    table = Table(title=f"Top {n_pick} — Buy List (deploy ${deploy:,.0f}, per-pos ${per_pos:,.0f})")
    table.add_column("#", justify="right")
    table.add_column("Ticker")
    table.add_column("Score", justify="right")
    table.add_column("4W mom", justify="right")
    table.add_column("Last px", justify="right")
    table.add_column("Shares", justify="right")
    table.add_column("USD", justify="right")
    table.add_column("Weight", justify="right")

    rows = []
    for rank, j in enumerate(top_idx, 1):
        tk = tickers[j]
        last_px = float(px[j])
        shares = int(per_pos / last_px)
        usd = shares * last_px
        m4w = float(scores_dict["score_4w"][-1, j])
        sc_val = float(sc_masked[j])
        weight = usd / capital
        rows.append((tk, sc_val, m4w, last_px, shares, usd, weight))
        table.add_row(
            str(rank), tk,
            f"{sc_val:.4f}",
            f"{m4w*100:+.1f}%",
            f"${last_px:.2f}",
            f"{shares:,d}",
            f"${usd:,.0f}",
            f"{weight*100:.1f}%",
        )
    console.print(table)

    total_usd = sum(r[5] for r in rows)
    margin_used = max(0.0, total_usd - capital)
    console.print(f"\n[dim]Total deployed: ${total_usd:,.0f}  (margin debit: ${margin_used:,.0f})[/]")
    console.print(f"[dim]Cash leftover: ${capital - min(total_usd, capital):,.0f}[/]")
    if leverage > 1.0:
        console.print(f"[yellow]Margin used: ${margin_used:,.0f} @ ~6% APR = ~${margin_used*0.06/2:,.0f} cost over 6 months[/]")


if __name__ == "__main__":
    main()
