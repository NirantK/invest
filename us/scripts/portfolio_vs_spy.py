#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["yfinance", "polars", "rich"]
# ///
"""
Compare IBKR portfolio performance vs SPY.

Uses avg cost from positions to estimate entry dates,
then compares each position's return vs SPY over the same window.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta

import polars as pl
import yfinance as yf
from rich.console import Console
from rich.table import Table

console = Console()


def get_positions() -> list[dict]:
    """Fetch positions from IBKR skill."""
    result = subprocess.run(
        ["uv", "run", sys.argv[0].replace("portfolio_vs_spy.py", "ibkr.py"), "positions", "--format", "json"],
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def estimate_entry_date(symbol: str, avg_cost: float, lookback_days: int = 365) -> str | None:
    """Find the most recent date when price was closest to avg_cost."""
    end = datetime.now()
    start = end - timedelta(days=lookback_days)

    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

    if hist.empty:
        return None

    # Find the date where close price is closest to avg cost
    # Search backwards (most recent first) — prefer recent matches
    hist = hist.sort_index(ascending=False)
    hist["diff"] = abs(hist["Close"] - avg_cost)

    # Find dates within 5% of avg cost, take the most recent
    threshold = avg_cost * 0.05
    close_matches = hist[hist["diff"] <= threshold]

    if not close_matches.empty:
        # Take the OLDEST close match (likely the actual buy date)
        best = close_matches.sort_index(ascending=True).iloc[0]
        return str(best.name.date())

    # Fallback: absolute closest
    best = hist.loc[hist["diff"].idxmin()]
    return str(best.name.date())


def get_spy_return(start_date: str, end_date: str) -> float:
    """Get SPY total return between two dates."""
    spy = yf.Ticker("SPY")
    hist = spy.history(start=start_date, end=end_date)
    if len(hist) < 2:
        return 0.0
    return (hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1


def main():
    console.print("[bold]Fetching IBKR positions...[/bold]")
    positions = get_positions()

    if not positions:
        console.print("[red]No positions found[/red]")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    console.print("[bold]Estimating entry dates from avg cost...[/bold]\n")

    rows = []
    total_cost = 0.0
    total_value = 0.0
    total_spy_equivalent_value = 0.0

    for pos in positions:
        symbol = pos["symbol"]
        avg_cost = pos["avgCost"]
        current_price = pos["currentPrice"]
        qty = pos["qty"]
        cost_basis = pos["costBasis"]
        market_value = pos["marketValue"]
        pnl_pct = pos["pnlPct"]

        entry_date = estimate_entry_date(symbol, avg_cost)
        if not entry_date:
            continue

        spy_return = get_spy_return(entry_date, today)
        spy_equivalent_value = cost_basis * (1 + spy_return)

        alpha = pnl_pct / 100 - spy_return

        rows.append({
            "symbol": symbol,
            "entry_date": entry_date,
            "avg_cost": avg_cost,
            "current_price": current_price,
            "qty": qty,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "position_return": pnl_pct / 100,
            "spy_return": spy_return,
            "alpha": alpha,
            "spy_equivalent_value": spy_equivalent_value,
        })

        total_cost += cost_basis
        total_value += market_value
        total_spy_equivalent_value += spy_equivalent_value

    # Display table
    table = Table(title="Portfolio vs SPY Comparison")
    table.add_column("Symbol", style="bold")
    table.add_column("Est. Entry", style="dim")
    table.add_column("Cost Basis", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("You", justify="right")
    table.add_column("SPY", justify="right")
    table.add_column("Alpha", justify="right")

    for r in sorted(rows, key=lambda x: x["alpha"]):
        pos_style = "green" if r["position_return"] >= 0 else "red"
        spy_style = "green" if r["spy_return"] >= 0 else "red"
        alpha_style = "green" if r["alpha"] >= 0 else "red"

        table.add_row(
            r["symbol"],
            r["entry_date"],
            f"${r['cost_basis']:,.0f}",
            f"${r['market_value']:,.0f}",
            f"[{pos_style}]{r['position_return']:+.1%}[/{pos_style}]",
            f"[{spy_style}]{r['spy_return']:+.1%}[/{spy_style}]",
            f"[{alpha_style}]{r['alpha']:+.1%}[/{alpha_style}]",
        )

    # Totals
    total_return = (total_value / total_cost - 1) if total_cost > 0 else 0
    total_spy_return = (total_spy_equivalent_value / total_cost - 1) if total_cost > 0 else 0
    total_alpha = total_return - total_spy_return

    pos_style = "green" if total_return >= 0 else "red"
    spy_style = "green" if total_spy_return >= 0 else "red"
    alpha_style = "green" if total_alpha >= 0 else "red"

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        f"[bold]${total_cost:,.0f}[/bold]",
        f"[bold]${total_value:,.0f}[/bold]",
        f"[bold {pos_style}]{total_return:+.1%}[/bold {pos_style}]",
        f"[bold {spy_style}]{total_spy_return:+.1%}[/bold {spy_style}]",
        f"[bold {alpha_style}]{total_alpha:+.1%}[/bold {alpha_style}]",
    )

    console.print(table)

    # Summary
    console.print(f"\n[bold]Portfolio:[/bold] ${total_value:,.0f} (was ${total_cost:,.0f})")
    console.print(f"[bold]If SPY instead:[/bold] ${total_spy_equivalent_value:,.0f}")
    diff = total_value - total_spy_equivalent_value
    diff_style = "green" if diff >= 0 else "red"
    console.print(f"[bold]Difference:[/bold] [{diff_style}]${diff:+,.0f}[/{diff_style}]")
    console.print(f"\n[dim]Entry dates estimated from when price was closest to avg cost (within 5%). Not exact.[/dim]")


if __name__ == "__main__":
    main()
