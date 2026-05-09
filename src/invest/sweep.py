"""
Multi-strategy sweep harness, shared between US and India.

Cross-product over `score_col × sizing × rebal_days × override_dict`.
Parallelized via ProcessPoolExecutor — each backtest is independent.

Universe-agnostic: caller supplies (prices, closes, dvols), allocator, baseline config.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import numpy as np
import polars as pl
from pydantic import BaseModel

from invest.backtest import BacktestConfig, BacktestResult, run_backtest


@dataclass
class SweepCell:
    """One cell of the sweep — fully describes a backtest run."""
    name: str
    overrides: dict
    rebal_days: int


class SweepRow(BaseModel):
    """One sweep row for tabular display + JSON export."""
    name: str
    rebal_days: int
    cagr: float
    martin: float
    ulcer: float
    max_dd: float
    sharpe: float
    avg_positions: float
    n_rebalances: int
    pct_in_cash: float
    overrides: dict


# Worker functions must be top-level for pickling
def _run_one(args) -> tuple[str, int, dict, dict]:
    """Worker: run one backtest. Returns (name, rebal_days, overrides, metrics_dict)."""
    name, overrides, rebal_days, prices_dict, closes_dict, dvols_dict, base_config, allocator_factory, excluded = args
    prices = pl.from_dict(prices_dict)
    closes = pl.from_dict(closes_dict)
    dvols = pl.from_dict(dvols_dict)
    cfg = BacktestConfig(**{**base_config, **overrides, "rebal_days": rebal_days})
    allocator = allocator_factory()
    result = run_backtest(prices, closes, dvols, cfg, allocator, excluded_tickers=set(excluded))
    metrics = {
        "cagr": result.cagr, "martin": result.martin, "ulcer": result.ulcer,
        "max_dd": result.max_dd, "sharpe": result.sharpe,
        "avg_positions": result.avg_positions, "n_rebalances": result.n_rebalances,
        "pct_in_cash": result.pct_in_cash, "final_equity": result.final_equity,
    }
    return name, rebal_days, overrides, metrics


def run_sweep(
    prices: pl.DataFrame,
    closes: pl.DataFrame,
    dvols: pl.DataFrame,
    base_config: dict,
    strategies: dict[str, dict],
    rebal_days_grid: tuple[int, ...] = (21,),
    allocator_factory: Callable | None = None,
    excluded_tickers: frozenset[str] = frozenset(),
    n_workers: int | None = None,
) -> list[SweepRow]:
    """Run cross-product of strategies × rebal_days. Parallel via ProcessPool.

    `allocator_factory`: zero-arg callable returning an AllocatorFn. Must be
    importable (top-level function) so it can be pickled across processes.
    """
    cells = [
        SweepCell(name=name, overrides=overrides, rebal_days=r)
        for name, overrides in strategies.items()
        for r in rebal_days_grid
    ]
    prices_d = {col: prices[col].to_list() for col in prices.columns}
    closes_d = {col: closes[col].to_list() for col in closes.columns}
    dvols_d = {col: dvols[col].to_list() for col in dvols.columns}

    args_list = [
        (c.name, c.overrides, c.rebal_days, prices_d, closes_d, dvols_d,
         base_config, allocator_factory, list(excluded_tickers))
        for c in cells
    ]

    rows: list[SweepRow] = []
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for fut in as_completed(pool.submit(_run_one, a) for a in args_list):
            name, rebal_days, overrides, metrics = fut.result()
            rows.append(SweepRow(
                name=name, rebal_days=rebal_days, overrides=overrides,
                cagr=metrics["cagr"], martin=metrics["martin"], ulcer=metrics["ulcer"],
                max_dd=metrics["max_dd"], sharpe=metrics["sharpe"],
                avg_positions=metrics["avg_positions"], n_rebalances=metrics["n_rebalances"],
                pct_in_cash=metrics["pct_in_cash"],
            ))
    rows.sort(key=lambda r: (r.name, r.rebal_days))
    return rows


def run_sweep_serial(
    prices: pl.DataFrame,
    closes: pl.DataFrame,
    dvols: pl.DataFrame,
    base_config: dict,
    strategies: dict[str, dict],
    rebal_days_grid: tuple[int, ...] = (21,),
    allocator: Callable = None,
    excluded_tickers: frozenset[str] = frozenset(),
    progress: bool = True,
) -> list[SweepRow]:
    """Serial sweep — for when allocator can't be pickled (uses global config refs).

    Vectorized within each backtest; serial across strategies.
    """
    rows: list[SweepRow] = []
    cells = [
        SweepCell(name=name, overrides=overrides, rebal_days=r)
        for name, overrides in strategies.items()
        for r in rebal_days_grid
    ]
    for i, c in enumerate(cells, 1):
        if progress:
            print(f"  [{i:2d}/{len(cells)}] {c.name} (rebal={c.rebal_days}d)", end=" ", flush=True)
        cfg = BacktestConfig(**{**base_config, **c.overrides, "rebal_days": c.rebal_days})
        result = run_backtest(prices, closes, dvols, cfg, allocator,
                              excluded_tickers=set(excluded_tickers))
        rows.append(SweepRow(
            name=c.name, rebal_days=c.rebal_days, overrides=c.overrides,
            cagr=result.cagr, martin=result.martin, ulcer=result.ulcer,
            max_dd=result.max_dd, sharpe=result.sharpe,
            avg_positions=result.avg_positions, n_rebalances=result.n_rebalances,
            pct_in_cash=result.pct_in_cash,
        ))
        if progress:
            print(f"CAGR={result.cagr*100:>+5.1f}% Martin={result.martin:>5.2f} "
                  f"Ulcer={result.ulcer*100:>4.1f}% DD={result.max_dd*100:>4.0f}%")
    return rows


def best_by_metric(rows: list[SweepRow], metric: str = "martin") -> list[SweepRow]:
    """Sort sweep rows by metric (descending). Use 'cagr', 'martin', 'sharpe', or 'ulcer' (asc)."""
    if metric == "ulcer":
        return sorted(rows, key=lambda r: r.ulcer)
    return sorted(rows, key=lambda r: -getattr(r, metric))


def best_per_strategy(rows: list[SweepRow], metric: str = "martin") -> dict[str, SweepRow]:
    """For each strategy name, pick the best rebal_days variant by metric."""
    by_name: dict[str, SweepRow] = {}
    for r in rows:
        cur = by_name.get(r.name)
        if cur is None:
            by_name[r.name] = r
            continue
        better = (r.ulcer < cur.ulcer) if metric == "ulcer" else (getattr(r, metric) > getattr(cur, metric))
        if better:
            by_name[r.name] = r
    return by_name
