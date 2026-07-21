"""
Concall sentiment dataset — keyword-scored from snippets.

Reads ticker universe from ai_infra_universe.py (excluding ETFs/index/factor/debt/commodity/REIT).
For each stock ticker, fetches concall_search hits scoped to that symbol with a broad
sentiment-rich query, then scores each snippet via keyword polarity.

Aggregates per-quarter mean sentiment across all reporting tickers, forward-fills
between reports, writes parquet + meta JSON.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402

EXCLUDE_PREFIXES = (
    "Index:", "Cap:", "Sector:", "Factor:", "Debt:", "Commodity:",
    "Real:REIT", "Real:InvIT", "SafeHaven:",
)

POSITIVE = {
    "growth", "strong", "robust", "record", "expansion", "expand", "increase",
    "improved", "improving", "momentum", "demand", "healthy", "outperform",
    "beat", "exceed", "confident", "positive", "uptick", "ramp", "ramping",
    "tailwind", "accelerate", "accelerating", "best", "highest", "doubled",
    "tripled", "scaled", "scaling", "upgrade", "guidance raised", "raised",
    "opportunities", "opportunity", "promising", "bullish", "optimistic",
    "milestone", "leadership", "premium", "margin expansion",
}

NEGATIVE = {
    "decline", "declining", "decrease", "decreased", "weak", "weakness",
    "headwind", "headwinds", "pressure", "muted", "soft", "softness",
    "challenging", "challenge", "challenges", "slowdown", "slow", "delay",
    "delayed", "delays", "concern", "concerns", "concerned", "cautious",
    "caution", "tone down", "miss", "missed", "below", "disappoint",
    "disappointing", "loss", "losses", "negative", "downgrade", "guidance cut",
    "cut", "lower", "lowered", "deferred", "postponed", "uncertain",
    "uncertainty", "deteriorate", "deteriorating", "stress", "stressed",
    "impairment", "writedown", "shortfall",
}

MAX_CREDITS = 70  # safety cap below 75 actual remaining
SEARCH_COST = 5
QUERY = "guidance outlook growth demand margin"  # broad sentiment-rich
LIMIT = 8  # 8 most recent transcripts per ticker

OUT_PARQUET = Path("india/data/macro_concall_sentiment.parquet")
OUT_META = Path("india/data/macro_concall_meta.json")
CACHE_FILE = Path("india/data/macro_concall_search_cache.json")


def filter_universe() -> list[tuple[str, str, str]]:
    """Return [(ticker, name, theme), ...] for stocks only."""
    return [
        (k, v[0], v[3])
        for k, v in AI_INFRA_UNIVERSE.items()
        if not v[3].startswith(EXCLUDE_PREFIXES)
    ]


def score_snippet(text: str) -> float:
    """Return sentiment in [-1, 1] from keyword polarity on snippet."""
    t = text.lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos + neg == 0:
        return 0.0
    raw = (pos - neg) / (pos + neg)
    # squash so single-word matches don't slam to ±1
    return max(-1.0, min(1.0, raw * 0.7))


def quarter_end(date_str: str) -> str:
    """Map YYYY-MM-DD → quarter-end YYYY-MM-DD (Mar/Jun/Sep/Dec)."""
    y, m, _ = date_str.split("-")
    m = int(m)
    if m <= 3:
        return f"{y}-03-31"
    if m <= 6:
        return f"{y}-06-30"
    if m <= 9:
        return f"{y}-09-30"
    return f"{y}-12-31"


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def aggregate_and_write(per_ticker: dict[str, list[tuple[str, float]]]) -> dict:
    """Build per-quarter mean across tickers, forward-fill, write parquet.

    per_ticker: {ticker: [(date_str, score), ...]}
    """
    # Bucket each (ticker, date, score) into its calendar quarter
    quarter_scores: dict[str, list[float]] = defaultdict(list)
    quarter_tickers: dict[str, set[str]] = defaultdict(set)
    all_dates: set[str] = set()

    for ticker, hits in per_ticker.items():
        # Per ticker, take mean score per quarter so a single ticker can't
        # dominate by having multiple snippets in one quarter
        ticker_q: dict[str, list[float]] = defaultdict(list)
        for date, score in hits:
            q = quarter_end(date)
            ticker_q[q].append(score)
            all_dates.add(date)
        for q, scores in ticker_q.items():
            quarter_scores[q].append(sum(scores) / len(scores))
            quarter_tickers[q].add(ticker)

    # Build daily frame: forward-fill quarter sentiment from earliest to today
    if not quarter_scores:
        raise RuntimeError("No data collected")

    sorted_quarters = sorted(quarter_scores.keys())
    min_date = sorted_quarters[0]
    # Use today as end
    from datetime import date as _date
    end_date = _date.today().isoformat()

    # Build a row per quarter end, then expand to daily forward fill
    quarter_rows = [
        {
            "quarter": q,
            "sentiment_score": sum(quarter_scores[q]) / len(quarter_scores[q]),
            "n_companies_reporting": len(quarter_tickers[q]),
        }
        for q in sorted_quarters
    ]

    # Generate daily series spanning [min_date, end_date]
    from datetime import datetime, timedelta
    start = datetime.fromisoformat(min_date).date()
    end = datetime.fromisoformat(end_date).date()
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]

    # Map quarter-end → row
    q_lookup = {r["quarter"]: r for r in quarter_rows}
    sorted_q_dates = sorted(q_lookup.keys())

    daily_rows = []
    cur_idx = 0
    cur_row = q_lookup[sorted_q_dates[0]]
    for d in days:
        # Advance to the latest quarter whose end <= d
        while cur_idx + 1 < len(sorted_q_dates) and sorted_q_dates[cur_idx + 1] <= d:
            cur_idx += 1
            cur_row = q_lookup[sorted_q_dates[cur_idx]]
        daily_rows.append({
            "date": d,
            "sentiment_score": cur_row["sentiment_score"],
            "n_companies_reporting": cur_row["n_companies_reporting"],
        })

    df = pl.DataFrame(daily_rows).with_columns([
        pl.col("date").cast(pl.Utf8),
        pl.col("sentiment_score").cast(pl.Float64),
        pl.col("n_companies_reporting").cast(pl.UInt32),
    ])
    df.write_parquet(OUT_PARQUET)
    return {
        "n_quarters": len(quarter_rows),
        "min_quarter": sorted_q_dates[0],
        "max_quarter": sorted_q_dates[-1],
        "n_days": len(daily_rows),
    }


def main() -> None:
    universe = filter_universe()
    print(f"[info] filtered universe: {len(universe)} stock tickers")

    cache = load_cache()
    print(f"[info] cache hit: {len(cache)} tickers already searched")

    # Diversify across themes: round-robin so we cover many themes even on partial budget
    by_theme: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for k, n, t in universe:
        if k not in cache:
            by_theme[t].append((k, n, t))

    to_search: list[tuple[str, str, str]] = []
    while sum(len(v) for v in by_theme.values()) > 0:
        for theme in sorted(by_theme.keys()):
            if by_theme[theme]:
                to_search.append(by_theme[theme].pop(0))

    n_search = min(len(to_search), MAX_CREDITS // SEARCH_COST)
    print(f"[info] budget allows {n_search} new searches this run")
    print(f"[info] tickers to search: {[k for k, _, _ in to_search[:n_search]]}")
    print()

    # Hand off to caller — actual MCP calls happen in the agent loop
    print("CALL_TICKERS:" + ",".join(k for k, _, _ in to_search[:n_search]))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "aggregate":
        cache = load_cache()
        per_ticker: dict[str, list[tuple[str, float]]] = {}
        for ticker, hits in cache.items():
            scored = [(h["news_dt"], score_snippet(h.get("snippet", ""))) for h in hits]
            per_ticker[ticker] = scored
        stats = aggregate_and_write(per_ticker)
        universe = filter_universe()
        meta = {
            "universe_size": len(universe),
            "tickers_attempted": list(cache.keys()),
            "tickers_with_data": [k for k, h in cache.items() if h],
            "tickers_skipped": {k: "no_concalls" for k, h in cache.items() if not h},
            "total_transcripts": sum(len(h) for h in cache.values()),
            "date_range": {
                "min_quarter": stats["min_quarter"],
                "max_quarter": stats["max_quarter"],
                "n_quarters": stats["n_quarters"],
                "n_days": stats["n_days"],
            },
            "query": QUERY,
            "scoring": "keyword_polarity_squashed_0.7",
        }
        OUT_META.write_text(json.dumps(meta, indent=2, default=str))
        print(f"[ok] wrote {OUT_PARQUET} ({stats['n_days']} days, {stats['n_quarters']} quarters)")
        print(f"[ok] wrote {OUT_META}")
    else:
        main()
