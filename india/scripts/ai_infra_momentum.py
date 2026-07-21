"""
AI-Infra India momentum screener.

Reuses fetch_etf_data infrastructure (yfinance fetch, Sortino-weighted scoring).
Universe defined in ai_infra_universe.py.

Usage:
  uv run python india/scripts/ai_infra_momentum.py
  uv run python india/scripts/ai_infra_momentum.py --top 25 --period 3y
  uv run python india/scripts/ai_infra_momentum.py --theme "Cable:*" --top 10
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from ai_infra_universe import AI_INFRA_UNIVERSE
from fetch_etf_data import (
    DataSource,
    compute_momentum,
    fetch_yfinance,
)


def fetch_universe(universe: dict, period: str = "3y") -> pl.DataFrame:
    """Parallel-fetch yfinance prices for the universe. Returns wide DataFrame."""
    keys = list(universe.keys())
    frames = []

    def _one(key: str):
        yf_ticker = universe[key][1]
        df = fetch_yfinance(yf_ticker, period)
        if df is None or "close" not in df.columns:
            return None
        return df.select("date", pl.col("close").alias(key))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_one, k): k for k in keys}
        for fut in as_completed(futures):
            res = fut.result()
            key = futures[fut]
            if res is None:
                print(f"  skip {key}", file=sys.stderr)
            else:
                frames.append(res)

    if not frames:
        return pl.DataFrame()

    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="date", how="full", coalesce=True)
    return out.sort("date")


def score_universe(universe: dict, prices: pl.DataFrame) -> pl.DataFrame:
    rows = []
    for key in universe:
        name = universe[key][0]
        theme = universe[key][3]
        stats = compute_momentum(prices, key, name=name, theme=theme)
        if stats is None:
            continue
        stats["theme"] = theme  # rename category → theme for display
        rows.append(stats)
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("score", descending=True)


def fmt_pct(v):
    return f"{v * 100:+.1f}%" if v is not None else "N/A"


def filter_theme(universe: dict, pattern: str) -> dict:
    """Glob-style theme prefix filter (e.g., 'Cable:*' or 'Power:Genset')."""
    pattern = pattern.rstrip("*")
    return {k: v for k, v in universe.items() if v[3].startswith(pattern)}


def print_table(scores: pl.DataFrame, top: int = 25):
    print(f"\n{'#':>3} {'Key':14s} {'Theme':22s} {'Name':30s} {'3M':>7} {'6M':>7} {'12M':>7} {'Score':>7} {'MaxDD':>7} {'CurrDD':>7}")
    print("-" * 130)
    for i, row in enumerate(scores.head(top).iter_rows(named=True), 1):
        print(
            f"{i:>3} {row['key']:14s} {row['theme']:22s} {row['name'][:30]:30s} "
            f"{fmt_pct(row['mom_3m']):>7} {fmt_pct(row['mom_6m']):>7} {fmt_pct(row['mom_12m']):>7} "
            f"{row['score']:>7.2f} "
            f"{fmt_pct(row['max_dd']):>7} {fmt_pct(row['current_dd']):>7}"
        )


def print_by_theme(scores: pl.DataFrame):
    themes = sorted(scores["theme"].unique().to_list())
    for theme in themes:
        sub = scores.filter(pl.col("theme") == theme)
        if sub.is_empty():
            continue
        print(f"\n--- {theme} ({len(sub)}) ---")
        print(f"{'Key':14s} {'Name':30s} {'3M':>7} {'6M':>7} {'12M':>7} {'Score':>7} {'MaxDD':>7}")
        print("-" * 100)
        for row in sub.iter_rows(named=True):
            print(
                f"{row['key']:14s} {row['name'][:30]:30s} "
                f"{fmt_pct(row['mom_3m']):>7} {fmt_pct(row['mom_6m']):>7} {fmt_pct(row['mom_12m']):>7} "
                f"{row['score']:>7.2f} {fmt_pct(row['max_dd']):>7}"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="3y", help="yfinance period (1y, 3y, 5y, max)")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--theme", default=None, help="Filter by theme prefix (e.g. 'Cable', 'Power', 'Energy:Gas')")
    ap.add_argument("--by-theme", action="store_true", help="Print one table per theme")
    args = ap.parse_args()

    universe = AI_INFRA_UNIVERSE
    if args.theme:
        universe = filter_theme(universe, args.theme)
        print(f"Theme filter '{args.theme}' → {len(universe)} tickers")

    print(f"AI-Infra India Momentum — {len(universe)} tickers, {args.period}")
    print("=" * 80)
    print("Fetching prices (cached daily)...")
    prices = fetch_universe(universe, args.period)
    fetched = [c for c in prices.columns if c != "date"]
    print(f"Got {len(fetched)} / {len(universe)} from yfinance")

    scores = score_universe(universe, prices)
    if scores.is_empty():
        print("No scores computed.")
        return

    if args.by_theme:
        print_by_theme(scores)
    print(f"\n{'=' * 130}")
    print(f"TOP {args.top} BY SORTINO-WEIGHTED MOMENTUM SCORE")
    print(f"{'=' * 130}")
    print_table(scores, args.top)


if __name__ == "__main__":
    main()
