"""
Shared walk-forward backtest engine for US and India momentum portfolios.

Platform-agnostic: takes a price/close/dvol DataFrame trio and an `allocator`
callable. Universe, sleeve definitions, and benchmark ticker are config.

Walk-forward: at each rebalance date, compute scores using only data ≤ that
date (no look-ahead), allocate, hold to next rebalance, mark-to-market daily.
Optional gates: regime (benchmark MA crossover), drawdown stop, vol targeting.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
import polars as pl
from pydantic import BaseModel, Field, ConfigDict, model_validator

from invest.momentum import score_one, LOOKBACK_3M, LOOKBACK_12M, SKIP_1M

PERIODS_PER_YEAR = 252
EPS_VOL = 1e-4
EPS_ULCER = 1e-6
GROSS_FLOOR = 0.20  # vol-targeting cannot deflate below 20% gross


class BacktestConfig(BaseModel):
    """All backtest knobs in one validated object."""
    model_config = ConfigDict(extra="forbid", frozen=False)

    score_col: str = "score_sortino"
    sizing: str = "equal"
    rebal_days: int = Field(default=21, gt=0)
    capital: float = Field(default=100_000.0, gt=0)
    max_positions: int = Field(default=15, gt=0)
    max_pct: float = Field(default=0.15, gt=0, le=1.0)
    min_pct: float = Field(default=0.03, ge=0, lt=1.0)
    warmup_days: int = Field(default=PERIODS_PER_YEAR, ge=0)
    min_adv: float = Field(default=0.0, ge=0)
    current_dd_floor: float = Field(default=-0.25, ge=-1.0, le=0.0)
    use_sleeve_caps: bool = True
    leverage: float = Field(default=1.0, gt=0)
    regime_gate: bool = False
    regime_ticker: str = "SPY"
    regime_fast: int = Field(default=50, gt=0)
    regime_slow: int = Field(default=200, gt=0)
    dd_stop: float = Field(default=0.0, ge=0, le=1.0)
    dd_recover_days: int = Field(default=21, ge=0)
    vol_target: float = Field(default=0.0, ge=0)
    vol_lookback: int = Field(default=60, gt=0)
    cash_yield_annual: float = Field(default=0.045, ge=0)

    @model_validator(mode="after")
    def _validate(self) -> "BacktestConfig":
        if not (self.min_pct < self.max_pct):
            raise ValueError("min_pct must be < max_pct")
        if not (self.regime_fast < self.regime_slow):
            raise ValueError("regime_fast must be < regime_slow")
        return self


class BacktestResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: BacktestConfig
    cagr: float = 0.0
    total_return: float = 0.0
    sharpe: float = 0.0
    martin: float = 0.0
    ulcer: float = 0.0
    max_dd: float = 0.0
    avg_positions: float = 0.0
    n_rebalances: int = 0
    final_equity: float = 0.0
    pct_in_cash: float = 0.0
    equity_curve: list[float] = Field(default_factory=list)


# AllocatorFn signature:
#   (scores: pl.DataFrame, deploy_capital: float, cfg: BacktestConfig) -> pl.DataFrame
# Returns DataFrame with at least columns ['ticker', 'alloc_usd'].
AllocatorFn = Callable[[pl.DataFrame, float, BacktestConfig], pl.DataFrame]


def metrics_from_equity(equity: np.ndarray) -> dict[str, float]:
    """CAGR, Sharpe, Martin, Ulcer, MaxDD, total_return from an equity curve."""
    if len(equity) < 2:
        return dict(cagr=0.0, sharpe=0.0, martin=0.0, ulcer=0.0,
                    max_dd=0.0, total_return=0.0)
    rets = np.diff(equity) / equity[:-1]
    n_years = len(equity) / PERIODS_PER_YEAR
    total = float(equity[-1] / equity[0] - 1)
    cagr = float((equity[-1] / equity[0]) ** (1 / max(n_years, 1e-9)) - 1)
    rstd = float(rets.std())
    sharpe = float((rets.mean() / rstd) * np.sqrt(PERIODS_PER_YEAR)) if rstd > 0 else 0.0
    rmax = np.maximum.accumulate(equity)
    dd = (equity - rmax) / rmax
    max_dd = float(dd.min())
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    martin = float(cagr / ulcer) if ulcer > EPS_ULCER else 0.0
    return dict(cagr=cagr, sharpe=sharpe, martin=martin, ulcer=ulcer,
                max_dd=max_dd, total_return=total)


def ffill_columns(prices: pl.DataFrame, exclude: Sequence[str] = ("date",)) -> dict[str, np.ndarray]:
    """Forward-fill each ticker column into a numpy array. Holdings shouldn't
    blink to zero on a missing trading day."""
    out: dict[str, np.ndarray] = {}
    for col in prices.columns:
        if col in exclude:
            continue
        arr = prices[col].to_numpy().astype(float)
        mask = np.isnan(arr)
        if mask.all():
            out[col] = arr
            continue
        idx = np.where(~mask, np.arange(len(arr)), 0)
        np.maximum.accumulate(idx, out=idx)
        out[col] = arr[idx]
    return out


def regime_signal(prices_1d: np.ndarray, fast: int, slow: int) -> np.ndarray:
    """1 = risk-on (fast MA > slow MA), 0 = risk-off. NaN-safe via convolve."""
    n = len(prices_1d)
    fastk = np.ones(fast) / fast
    slowk = np.ones(slow) / slow
    ma_fast = np.full(n, np.nan)
    ma_slow = np.full(n, np.nan)
    if n >= fast:
        ma_fast[fast - 1:] = np.convolve(prices_1d, fastk, mode="valid")
    if n >= slow:
        ma_slow[slow - 1:] = np.convolve(prices_1d, slowk, mode="valid")
    return ((ma_fast > ma_slow) & ~np.isnan(ma_fast) & ~np.isnan(ma_slow)).astype(int)


def build_scores_at(
    prices_until: pl.DataFrame,
    closes_until: pl.DataFrame,
    dvols_until: pl.DataFrame,
    excluded: set[str] | None = None,
    min_history: int = LOOKBACK_3M + SKIP_1M,
) -> pl.DataFrame:
    """Compute scores using only data ≤ today (no look-ahead).

    excluded: tickers to skip entirely (e.g. benchmark-only tickers like SPY).
    """
    excluded = excluded or set()
    rows = []
    for col in prices_until.columns:
        if col == "date" or col in excluded:
            continue
        p = prices_until[col].drop_nulls().to_numpy()
        if len(p) < min_history:
            continue
        r = np.diff(p) / p[:-1]
        c_arr = closes_until[col].drop_nulls().to_numpy() if col in closes_until.columns else None
        dv_arr = dvols_until[col].drop_nulls().to_numpy() if col in dvols_until.columns else None
        result = score_one(col, p, r, c_arr, dv_arr)
        if result is not None:
            rows.append(result)
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def _build_price_matrix(price_arrays: dict[str, np.ndarray]) -> tuple[np.ndarray, dict[str, int]]:
    """Stack per-ticker arrays into a (n_days, n_tickers) matrix + ticker→col index."""
    tickers = sorted(price_arrays)
    matrix = np.column_stack([price_arrays[t] for t in tickers])
    return matrix, {t: i for i, t in enumerate(tickers)}


def run_backtest(
    prices: pl.DataFrame,
    closes: pl.DataFrame,
    dvols: pl.DataFrame,
    cfg: BacktestConfig,
    allocator: AllocatorFn,
    excluded_tickers: set[str] | None = None,
) -> BacktestResult:
    """Walk-forward backtest with vectorized mark-to-market.

    Universe-agnostic — `allocator` knows about platform-specific sleeve caps,
    thesis groups, etc. Daily MTM uses a (n_days, n_tickers) price matrix and
    parallel (idx, shares) arrays — no per-day Python loop over holdings.
    """
    n_days = len(prices)
    if n_days < cfg.warmup_days + cfg.rebal_days:
        return BacktestResult(config=cfg)

    excluded_tickers = excluded_tickers or set()
    price_arrays = ffill_columns(prices)
    price_matrix, ticker_col = _build_price_matrix(price_arrays)

    regime_arr: np.ndarray | None = None
    if cfg.regime_gate and cfg.regime_ticker in price_arrays:
        regime_arr = regime_signal(price_arrays[cfg.regime_ticker], cfg.regime_fast, cfg.regime_slow)

    daily_cash_rate = (1 + cfg.cash_yield_annual) ** (1 / PERIODS_PER_YEAR) - 1
    rebal_dates = set(range(cfg.warmup_days, n_days, cfg.rebal_days))

    equity = np.empty(n_days - cfg.warmup_days + 1, dtype=float)
    equity[0] = cfg.capital
    cash = float(cfg.capital)

    # Holdings tracked as parallel numpy arrays for vectorized MTM
    h_idx = np.empty(0, dtype=np.int64)
    h_shares = np.empty(0, dtype=float)

    days_in_cash = 0
    in_cash_mode = False
    cooldown_until = 0
    running_max_eq = cfg.capital
    n_pos_total = 0

    for step, d_idx in enumerate(range(cfg.warmup_days, n_days), start=1):
        cash *= 1 + daily_cash_rate
        port_value = cash + float(price_matrix[d_idx, h_idx] @ h_shares) if h_idx.size else cash
        equity[step] = port_value
        if running_max_eq < port_value:
            running_max_eq = port_value
        if h_idx.size == 0:
            days_in_cash += 1

        if cfg.dd_stop > 0 and h_idx.size and (port_value / running_max_eq - 1) < -cfg.dd_stop:
            cash = port_value
            h_idx = np.empty(0, dtype=np.int64)
            h_shares = np.empty(0, dtype=float)
            in_cash_mode = True
            cooldown_until = d_idx + cfg.dd_recover_days

        if (regime_arr is not None and h_idx.size
                and d_idx < len(regime_arr) and regime_arr[d_idx] == 0):
            cash = port_value
            h_idx = np.empty(0, dtype=np.int64)
            h_shares = np.empty(0, dtype=float)
            in_cash_mode = True

        if d_idx not in rebal_dates:
            continue

        if in_cash_mode:
            if cooldown_until > 0 and d_idx < cooldown_until:
                continue
            if regime_arr is not None and d_idx < len(regime_arr) and regime_arr[d_idx] == 0:
                continue
            in_cash_mode = False
            cooldown_until = 0

        scores = build_scores_at(
            prices.head(d_idx + 1), closes.head(d_idx + 1), dvols.head(d_idx + 1),
            excluded=excluded_tickers,
        )
        if scores.is_empty():
            continue
        if cfg.min_adv > 0 and "adv60" in scores.columns:
            scores = scores.filter(pl.col("adv60") >= cfg.min_adv)
        if cfg.current_dd_floor > -1.0 and "current_dd" in scores.columns:
            scores = scores.filter(pl.col("current_dd") >= cfg.current_dd_floor)
        if scores.is_empty():
            continue

        gross_scale = cfg.leverage
        if cfg.vol_target > 0 and step >= cfg.vol_lookback:
            window = equity[step - cfg.vol_lookback:step + 1]
            wrets = np.diff(window) / window[:-1]
            realized_vol = float(wrets.std() * np.sqrt(PERIODS_PER_YEAR))
            if realized_vol > EPS_VOL:
                gross_scale = max(GROSS_FLOOR, min(cfg.leverage,
                                                    cfg.leverage * cfg.vol_target / realized_vol))

        deploy = port_value * gross_scale
        alloc = allocator(scores, deploy, cfg)
        if alloc.is_empty():
            continue

        # Vectorize new holdings build
        new_tickers = alloc["ticker"].to_list()
        new_amts = np.asarray(alloc["alloc_usd"].to_list(), dtype=float)
        new_idx = np.fromiter((ticker_col[t] for t in new_tickers), dtype=np.int64,
                              count=len(new_tickers))
        new_prices = price_matrix[d_idx, new_idx]
        h_idx = new_idx
        h_shares = new_amts / new_prices
        cash = port_value - float(new_amts.sum())
        n_pos_total += h_idx.size

    metrics = metrics_from_equity(equity)
    n_rebals = sum(1 for d in rebal_dates if d < n_days)
    return BacktestResult(
        config=cfg,
        equity_curve=equity.tolist(),
        pct_in_cash=days_in_cash / max(equity.size, 1),
        cagr=metrics["cagr"], total_return=metrics["total_return"],
        sharpe=metrics["sharpe"], martin=metrics["martin"], ulcer=metrics["ulcer"],
        max_dd=metrics["max_dd"],
        avg_positions=n_pos_total / max(n_rebals, 1),
        n_rebalances=n_rebals,
        final_equity=float(equity[-1]),
    )
