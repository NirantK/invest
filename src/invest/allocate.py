"""
Shared allocation engine: water-fill, sleeve caps, thesis groups, ETF overlap.

Platform-agnostic — accepts SLEEVE_CAPS / THESIS_GROUPS / EXPENSE_RATIOS / ETF_OVERLAP
as args (no module-level globals).
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import polars as pl

# Sleeve cap entry: (label, members_list, cap_pct)
SleeveCap = tuple[str, list[str], float]
# Thesis group entry: (max_picks, members_list)
ThesisGroup = tuple[int, list[str]]
# ETF overlap entry: {etf_ticker: (constituents, min_combined_weight)}
EtfOverlap = dict[str, tuple[list[str], float]]
# ETF holdings provider: callable(ticker) -> {ticker: weight}
HoldingsProvider = Callable[[str], dict[str, float]]


SIZING_MODES = {"raw", "sqrt", "equal"}


def _transform_for_sizing(scores: dict[str, float], mode: str) -> dict[str, float]:
    if mode == "raw":
        return dict(scores)
    if mode == "sqrt":
        return {t: float(np.sqrt(max(s, 0.0))) for t, s in scores.items()}
    if mode == "equal":
        return {t: 1.0 for t in scores}
    raise ValueError(f"Unknown sizing mode: {mode}")


def water_fill(
    scores: dict[str, float],
    caps: dict[str, float],
    capital: float,
    sizing: str = "raw",
) -> dict[str, float]:
    """Pour capital into tickers proportional to (transformed) score. Pin at cap when hit;
    redistribute remainder to uncapped names. Continue until exhausted or all capped.
    """
    weights = _transform_for_sizing(scores, sizing)
    pinned: dict[str, float] = {}
    active = dict(weights)
    remaining = float(capital)

    while active and remaining > 0.01:
        total = sum(active.values())
        if total <= 0:
            break
        binding = min((caps[t] * total / s for t, s in active.items() if s > 0),
                      default=remaining)
        pour = min(remaining, binding)
        for t, s in list(active.items()):
            allocated = pinned.get(t, 0) + (s / total) * pour
            if allocated >= caps[t] - 0.01:
                pinned[t] = caps[t]
                del active[t]
            else:
                pinned[t] = allocated
        remaining -= pour
    return pinned


def add_rank_scores(scores: pl.DataFrame) -> pl.DataFrame:
    """Cross-sectional percentile rank composite. Adds `score_rank` and `r_*` columns."""
    pos = scores.filter(pl.col("wt_mom") > 0)
    if pos.is_empty():
        return scores.with_columns(pl.lit(0.0).alias("score_rank"))
    n = len(pos)

    def _pct(col: str, descending: bool = True) -> pl.Expr:
        return (pl.col(col).rank(method="average", descending=not descending) - 1) / max(n - 1, 1)

    ranked = pos.with_columns([
        _pct("wt_mom").alias("r_mom"),
        _pct("smoothness").alias("r_smooth"),
        _pct("ulcer_1y", descending=False).alias("r_ulcer"),
        _pct("dv_slope").alias("r_dvol"),
        _pct("dist52", descending=False).alias("r_d52"),
    ]).with_columns(
        ((pl.col("r_mom") + pl.col("r_smooth") + pl.col("r_ulcer")
          + pl.col("r_dvol") + pl.col("r_d52")) / 5.0).alias("score_rank")
    )

    keep_cols = ["ticker", "score_rank", "r_mom", "r_smooth", "r_ulcer", "r_dvol", "r_d52"]
    return scores.join(ranked.select(keep_cols), on="ticker", how="left").with_columns(
        pl.col("score_rank").fill_null(0.0)
    )


def allocate(
    scores: pl.DataFrame,
    capital: float,
    min_pct: float,
    max_pct: float,
    max_positions: int,
    score_col: str = "score_sortino",
    sizing: str = "raw",
    ticker_max_alloc: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Filter to positive momentum, score-rank top-N, water-fill within (min, max) caps.
    Below-min names are dropped and re-water-filled on the trimmed set, cascading.
    """
    ticker_max_alloc = ticker_max_alloc or {}
    df = scores.filter(pl.col("wt_mom") > 0).sort(score_col, descending=True).head(max_positions)
    if df.is_empty():
        return pl.DataFrame()
    total = df[score_col].sum()
    if total <= 0:
        return pl.DataFrame()

    min_amount = capital * min_pct
    scores_dict = {row["ticker"]: row[score_col] for row in df.iter_rows(named=True)}
    caps = {t: capital * ticker_max_alloc.get(t, max_pct) for t in scores_dict}
    alloc_dict = water_fill(scores_dict, caps, capital, sizing=sizing)

    for _ in range(50):
        below_min = [t for t, v in alloc_dict.items() if 0 < v < min_amount]
        if not below_min:
            break
        for t in below_min:
            del scores_dict[t]
            del caps[t]
        if not scores_dict:
            return pl.DataFrame()
        alloc_dict = water_fill(scores_dict, caps, capital, sizing=sizing)

    rows = [{"ticker": t, "alloc_usd": v} for t, v in alloc_dict.items() if v > 0]
    if not rows:
        return pl.DataFrame()
    return df.join(pl.DataFrame(rows), on="ticker", how="inner")


def apply_thesis_groups(
    scores: pl.DataFrame,
    thesis_groups: list[ThesisGroup],
    expense_ratios: dict[str, float] | None = None,
    score_col: str = "score_sortino",
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Within each same-thesis group, keep only top-K by fee-adjusted score."""
    expense_ratios = expense_ratios or {}
    excluded: dict[str, str] = {}
    for max_picks, group in thesis_groups:
        in_group = (
            scores
            .filter(pl.col("ticker").is_in(group) & (pl.col("wt_mom") > 0))
            .with_columns(
                pl.col("ticker").map_elements(
                    lambda t: expense_ratios.get(t, 0.0), return_dtype=pl.Float64
                ).alias("expense_ratio")
            )
            .with_columns(
                (pl.col(score_col) * (1 - pl.col("expense_ratio"))).alias("fee_adj_score")
            )
            .sort("fee_adj_score", descending=True)
        )
        if len(in_group) <= max_picks:
            continue
        winner = in_group[0]["ticker"].item()
        for row in in_group[max_picks:].iter_rows(named=True):
            fee_pct = row["expense_ratio"] * 100
            excluded[row["ticker"]] = (
                f"same thesis as {winner} (score {row[score_col]:.2f}, fee {fee_pct:.2f}%)"
            )
    return scores.filter(~pl.col("ticker").is_in(list(excluded))), excluded


def apply_sleeve_caps(
    alloc: pl.DataFrame,
    scores: pl.DataFrame,
    capital: float,
    min_pct: float,
    max_pct: float,
    max_positions: int,
    sleeve_caps: list[SleeveCap],
    score_col: str = "score_sortino",
    sizing: str = "raw",
    ticker_max_alloc: dict[str, float] | None = None,
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Enforce per-sleeve caps. Iteratively demote lowest-score name in worst over-cap sleeve,
    re-run allocate on remaining universe, until all sleeves are under cap."""
    blocked: dict[str, str] = {}
    if alloc.is_empty():
        return alloc, blocked

    for _ in range(50):
        breaches = []
        for sleeve_name, members, cap_pct in sleeve_caps:
            sleeve_amt = alloc.filter(pl.col("ticker").is_in(members))["alloc_usd"].sum()
            if sleeve_amt > capital * cap_pct + 1:
                in_sleeve = alloc.filter(pl.col("ticker").is_in(members)).sort(score_col)
                if not in_sleeve.is_empty():
                    drop = in_sleeve[0]["ticker"].item()
                    breaches.append((sleeve_name, drop, sleeve_amt / capital))

        if not breaches:
            break
        breaches.sort(key=lambda x: -x[2])
        sleeve_name, drop_ticker, _ = breaches[0]
        blocked[drop_ticker] = f"sleeve cap: {sleeve_name}"
        filtered = scores.filter(~pl.col("ticker").is_in(list(blocked.keys())))
        alloc = allocate(filtered, capital, min_pct, max_pct, max_positions,
                         score_col=score_col, sizing=sizing, ticker_max_alloc=ticker_max_alloc)
        if alloc.is_empty():
            return alloc, blocked

    return alloc, blocked


def apply_etf_overlap(
    alloc: pl.DataFrame,
    scores: pl.DataFrame,
    capital: float,
    min_pct: float,
    max_pct: float,
    max_positions: int,
    etf_overlap: EtfOverlap,
    holdings_provider: HoldingsProvider | None = None,
    score_col: str = "score_sortino",
    sizing: str = "raw",
    ticker_max_alloc: dict[str, float] | None = None,
) -> tuple[pl.DataFrame, dict[str, str]]:
    """If a selected ETF holds constituents already in the universe, optionally block them."""
    selected = set(alloc["ticker"].to_list())
    universe = set(scores["ticker"].to_list())
    blocked: dict[str, str] = {}

    threshold_etfs = [etf for etf in selected & set(etf_overlap) if etf_overlap[etf][1] > 0.0]
    etf_holdings: dict[str, dict[str, float]] = {}
    if threshold_etfs and holdings_provider is not None:
        etf_holdings = {etf: holdings_provider(etf) for etf in threshold_etfs}

    for etf in selected & set(etf_overlap):
        constituents, weight_threshold = etf_overlap[etf]
        in_universe = [t for t in constituents if t in universe]
        if weight_threshold > 0.0:
            combined = sum(
                sum(holdings.get(t, 0.0) for t in in_universe)
                for holdings in etf_holdings.values()
            )
            if combined <= weight_threshold:
                continue
        for ticker in in_universe:
            blocked[ticker] = f"held inside {etf}"

    if not blocked:
        return alloc, blocked
    filtered = scores.filter(~pl.col("ticker").is_in(list(blocked)))
    return allocate(filtered, capital, min_pct, max_pct, max_positions,
                    score_col=score_col, sizing=sizing,
                    ticker_max_alloc=ticker_max_alloc), blocked
