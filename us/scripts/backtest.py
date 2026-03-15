"""
Momentum Parameter Sweep — Walk-Forward Validated, Vectorized

All hot paths use numpy vectorized ops. No Python loops over daily returns.
Uses shared data_utils for fetching, ProcessPoolExecutor with initializer
to avoid re-pickling the price matrix per task.

Usage:
    uv run python us/scripts/backtest.py
    uv run python us/scripts/backtest.py --top 20 --period 5y
    uv run python us/scripts/backtest.py --period max --max-dd-cap 0.50
"""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import product

import click
import numpy as np
from rich.console import Console
from rich.table import Table

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from data_utils import fetch_all_numpy, fetch_all_earnings, build_earnings_momentum

console = Console()

# ── Ticker universe ──────────────────────────────────────────────────────────
# Import from us_portfolio_allocation would create circular dep, so define here.
# Keep in sync with us_portfolio_allocation.py TICKERS.

TICKERS = [
    # Precious Metals
    "WPM", "PAAS", "FNV", "AEM", "HL", "RGLD",
    # Energy: Integrated
    "XOM", "CVX", "CNQ", "SU", "CVE", "XLE",
    # Energy: Midstream (1099 only)
    "ENB", "TRP", "KMI", "WMB", "OKE",
    # Energy: Refineries
    "VLO", "PSX", "MPC", "DINO",
    # Energy: E&P
    "COP", "DVN", "OXY",
    # Industrial Metals / Uranium / Platinum
    "COPX", "URA", "PPLT",
    # LatAm / EM Fintech
    "ILF", "NU",
    # Factor ETFs
    "QVAL", "QMOM", "IVAL", "IMOM", "DFSV", "DXIV",
    "AVUV", "AVDV", "AVES", "IMTM",
    # Regional Factor
    "EWJV", "DFJ", "DFE", "EWZS", "FLN", "FRDM",
    # Gold ETFs / Sprott
    "GOAU", "SGDM", "SGDJ", "GBUG", "URNM", "URNJ", "COPP",
    # Bitcoin / Software
    "MSTR", "CSU.TO",
    # AI Infrastructure
    "BE", "CRWV", "INTC", "LITE", "CORZ", "IREN", "APLD", "SNDK",
    "CIFR", "EQT", "COHR", "SEI", "TSEM", "RIOT", "KRC", "HUT", "WYFI",
    # NYSE FANG+ (10 constituents)
    "META", "AAPL", "AMZN", "NFLX", "GOOGL", "MSFT", "NVDA",
    "SNOW", "TSLA", "AVGO",
    # Tech / Software (non-FANG+)
    "ADBE", "CRWD",
    # Nifty IT (US ADRs + NSE)
    "INFY", "WIT",
    "TCS.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS",
    "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS", "INFY.NS", "WIPRO.NS",
]

MIN_TICKERS_PER_FOLD = 15  # Skip folds with fewer valid tickers


# ── Vectorized scoring (all numpy, no Python loops) ──────────────────────────


def momentum(prices: np.ndarray, lookback: int, skip: int) -> np.ndarray:
    """Momentum for all tickers. Shape: (n_tickers,)."""
    n = prices.shape[0]
    if n < lookback + skip:
        return np.zeros(prices.shape[1])
    end = n - skip
    start = end - lookback
    with np.errstate(divide="ignore", invalid="ignore"):
        mom = prices[end - 1] / prices[start] - 1
    return np.nan_to_num(mom, nan=0.0)


def downside_vol(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """Annualized downside vol. Shape: (n_tickers,)."""
    w = min(window, prices.shape[0] - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(prices[-w - 1:], axis=0) / prices[-w - 1:-1]
    rets = np.nan_to_num(rets, nan=0.0)
    neg = np.minimum(rets, 0.0)
    dv = np.sqrt(252) * np.nanstd(neg, axis=0)
    return np.where(dv > 0, dv, 0.0001)


def trend_quality(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """R² of log-price trend — fully vectorized across all columns."""
    n = prices.shape[0]
    w = min(window, n)
    segment = prices[-w:]
    with np.errstate(divide="ignore", invalid="ignore"):
        log_p = np.log(segment)
    log_p = np.nan_to_num(log_p, nan=0.0, posinf=0.0, neginf=0.0)

    x = np.arange(w, dtype=np.float64)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    if x_var == 0:
        return np.zeros(prices.shape[1])

    # Vectorized linear regression across all columns at once
    y_mean = log_p.mean(axis=0)  # (n_tickers,)
    numerator = ((x - x_mean)[:, np.newaxis] * (log_p - y_mean)).sum(axis=0)
    slope = numerator / x_var

    fitted = slope * (x[:, np.newaxis] - x_mean) + y_mean
    ss_res = ((log_p - fitted) ** 2).sum(axis=0)
    ss_tot = ((log_p - y_mean) ** 2).sum(axis=0)

    with np.errstate(divide="ignore", invalid="ignore"):
        quality = 1.0 - ss_res / ss_tot
    quality = np.where(ss_tot > 0, quality, 0.0)
    return np.maximum(quality, 0.0)


def fip_score(prices: np.ndarray, window: int = 252) -> np.ndarray:
    """Frog-in-the-Pan: fraction of positive daily returns."""
    w = min(window, prices.shape[0] - 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rets = np.diff(prices[-(w + 1):], axis=0) / prices[-(w + 1):-1]
    rets = np.nan_to_num(rets, nan=0.0)
    return np.mean(rets > 0, axis=0)


# ── Scoring params ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoringParams:
    lb_short: int
    lb_mid: int
    lb_long: int
    w_short: float
    w_mid: float
    w_long: float
    skip: int
    use_sortino: bool
    use_smoothness: bool
    use_earnings: bool          # Blend earnings momentum into score
    max_positions: int

    def label(self) -> str:
        parts = [
            f"lb={self.lb_short}/{self.lb_mid}/{self.lb_long}",
            f"w={self.w_short:.1f}/{self.w_mid:.1f}/{self.w_long:.1f}",
            f"skip={self.skip}",
        ]
        if self.use_sortino:
            parts.append("sortino")
        if self.use_smoothness:
            parts.append("smooth")
        if self.use_earnings:
            parts.append("earn")
        parts.append(f"n={self.max_positions}")
        return " ".join(parts)


def score_universe(
    prices_window: np.ndarray,
    params: ScoringParams,
    earnings_row: np.ndarray | None = None,
) -> np.ndarray:
    """Score all tickers. Returns (n_tickers,). Negative = excluded.

    earnings_row: (n_tickers,) YoY EPS growth at the rebalance date. NaN = no data.
    """
    n = prices_window.shape[0]
    n_tickers = prices_window.shape[1]

    if n < params.lb_long + params.skip:
        return np.full(n_tickers, -1.0)

    mom_s = momentum(prices_window, params.lb_short, params.skip)
    mom_m = momentum(prices_window, params.lb_mid, params.skip)
    mom_l = momentum(prices_window, params.lb_long, params.skip)

    wt_mom = params.w_short * mom_s + params.w_mid * mom_m + params.w_long * mom_l
    scores = wt_mom.copy()

    if params.use_smoothness:
        qual = trend_quality(prices_window, min(252, n))
        fip = fip_score(prices_window, min(252, n - 1))
        scores *= np.sqrt(qual * fip)

    if params.use_sortino:
        scores /= downside_vol(prices_window, min(252, n))

    if params.use_earnings and earnings_row is not None:
        # Earnings momentum boost: multiply by (1 + clipped_yoy_growth)
        # Positive earnings growth amplifies score, negative shrinks it
        # NaN (ETFs, no data) → neutral multiplier of 1.0
        earn = np.nan_to_num(earnings_row, nan=0.0)
        earn_clipped = np.clip(earn, -0.5, 2.0)  # Cap extreme values
        scores *= (1 + earn_clipped)

    return np.where(wt_mom > 0, scores, -1.0)


# ── Vectorized OOS period ────────────────────────────────────────────────────


def run_oos_period(
    prices: np.ndarray,
    params: ScoringParams,
    oos_start: int,
    oos_end: int,
    rebalance_freq: int = 21,
    earn_mom: np.ndarray | None = None,
) -> tuple[float, float, float, np.ndarray]:
    """Run one OOS period. Returns (return, max_dd, avg_pos, daily_values).

    Inner daily return loop is fully vectorized with numpy.
    earn_mom: (n_days, n_tickers) earnings momentum matrix, or None.
    """
    n_tickers = prices.shape[1]
    period_len = oos_end - oos_start
    portfolio_value = np.ones(period_len + 1)
    position_counts = []

    rebal_offsets = list(range(0, period_len, rebalance_freq))

    for idx, rb_offset in enumerate(rebal_offsets):
        next_offset = rebal_offsets[idx + 1] if idx + 1 < len(rebal_offsets) else period_len

        # Score at rebalance point
        rb_abs = oos_start + rb_offset
        earn_row = earn_mom[rb_abs] if earn_mom is not None else None
        scores = score_universe(prices[:rb_abs + 1], params, earn_row)
        valid = np.where(scores > 0)[0]

        if len(valid) == 0:
            # No positions: flat
            portfolio_value[rb_offset + 1:next_offset + 1] = portfolio_value[rb_offset]
            position_counts.append(0)
            continue

        top_n = min(params.max_positions, len(valid))
        top_idx = valid[np.argsort(scores[valid])[-top_n:]]
        weights = np.zeros(n_tickers)
        weights[top_idx] = 1.0 / top_n
        position_counts.append(top_n)

        # Vectorized daily returns for this holding period
        day_start = oos_start + rb_offset
        day_end = min(oos_start + next_offset, prices.shape[0] - 1)
        n_hold_days = day_end - day_start

        if n_hold_days <= 0:
            continue

        with np.errstate(divide="ignore", invalid="ignore"):
            daily_rets = prices[day_start + 1:day_end + 1] / prices[day_start:day_end] - 1
        daily_rets = np.nan_to_num(daily_rets, nan=0.0)

        # Portfolio returns = daily_rets @ weights (matrix-vector)
        port_rets = daily_rets @ weights  # (n_hold_days,)

        # Compounded portfolio value
        cum = np.cumprod(1 + port_rets)
        actual_days = min(n_hold_days, next_offset - rb_offset)
        portfolio_value[rb_offset + 1:rb_offset + 1 + actual_days] = (
            portfolio_value[rb_offset] * cum[:actual_days]
        )

    oos_return = portfolio_value[-1] / portfolio_value[0] - 1
    running_max = np.maximum.accumulate(portfolio_value)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdowns = (portfolio_value - running_max) / running_max
    max_dd = np.nan_to_num(drawdowns, nan=0.0).min()
    avg_pos = np.mean(position_counts) if position_counts else 0

    return oos_return, max_dd, avg_pos, portfolio_value


# ── Walk-forward result ──────────────────────────────────────────────────────


@dataclass
class WalkForwardResult:
    oos_total_return: float
    oos_annualized: float
    oos_max_dd: float
    oos_sortino: float
    oos_calmar: float
    oos_romad: float
    oos_win_rate: float
    n_folds: int
    avg_positions: float
    consistency: float
    params: ScoringParams
    fold_returns: list[float] = field(default_factory=list)

    def label(self) -> str:
        return self.params.label()


# ── Walk-forward engine ──────────────────────────────────────────────────────

# Global arrays set by ProcessPoolExecutor initializer (avoid pickling per task)
_G_PRICES: np.ndarray | None = None
_G_DATES: np.ndarray | None = None
_G_EARN_MOM: np.ndarray | None = None


def _init_worker(prices: np.ndarray, dates: np.ndarray, earn_mom: np.ndarray | None):
    global _G_PRICES, _G_DATES, _G_EARN_MOM
    _G_PRICES = prices
    _G_DATES = dates
    _G_EARN_MOM = earn_mom


def _worker_run(args: tuple) -> WalkForwardResult:
    """Worker function using global prices (set by initializer)."""
    params, min_train, oos_window, valid_folds = args
    return walk_forward_backtest(
        _G_PRICES, params, min_train, oos_window, valid_folds, _G_EARN_MOM
    )


def build_folds(
    prices: np.ndarray,
    min_train_days: int,
    oos_window_days: int,
    min_tickers: int = MIN_TICKERS_PER_FOLD,
) -> list[tuple[int, int]]:
    """Build fold boundaries, pruning folds with too few tickers."""
    n_days = prices.shape[0]
    folds = []
    train_end = min_train_days
    while train_end + 21 < n_days:
        oos_start = train_end
        oos_end = min(train_end + oos_window_days, n_days - 1)
        if oos_end - oos_start < 21:
            break
        # Count tickers with valid data at this point
        window = prices[:oos_start]
        n_valid = np.sum(~np.all(np.isnan(window), axis=0))
        if n_valid >= min_tickers:
            folds.append((oos_start, oos_end))
        train_end = oos_end
    return folds


def walk_forward_backtest(
    prices: np.ndarray,
    params: ScoringParams,
    min_train_days: int = 252,
    oos_window_days: int = 126,
    folds: list[tuple[int, int]] | None = None,
    earn_mom: np.ndarray | None = None,
) -> WalkForwardResult:
    """Anchored walk-forward backtest."""
    if folds is None:
        folds = build_folds(prices, min_train_days, oos_window_days)

    if not folds:
        return WalkForwardResult(0, 0, -1, 0, 0, 0, 0, 0, 0, 1.0, params)

    fold_returns = []
    all_daily_values = []
    total_positions = []

    em = earn_mom if params.use_earnings else None
    for oos_start, oos_end in folds:
        ret, dd, avg_pos, daily_vals = run_oos_period(
            prices, params, oos_start, oos_end, earn_mom=em
        )
        fold_returns.append(ret)
        total_positions.append(avg_pos)
        all_daily_values.append(daily_vals)

    # Compound OOS returns
    oos_total = float(np.prod([1 + r for r in fold_returns]) - 1)

    # Chain daily values — vectorized segment scaling
    scaled_segments = []
    cumulative = 1.0
    for dv in all_daily_values:
        scale = cumulative / dv[0] if dv[0] != 0 else cumulative
        scaled_segments.append(dv * scale)
        cumulative = scaled_segments[-1][-1]
    scaled = np.concatenate(scaled_segments)

    running_max = np.maximum.accumulate(scaled)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd_series = (scaled - running_max) / running_max
    overall_dd = np.nan_to_num(dd_series, nan=0.0).min()

    # Annualized return
    total_oos_days = sum(e - s for s, e in folds)
    n_years = total_oos_days / 252
    ann_return = (1 + oos_total) ** (1 / n_years) - 1 if n_years > 0 else 0

    # Fold stats
    fold_arr = np.array(fold_returns)
    consistency = float(fold_arr.std())
    win_rate = float(np.mean(fold_arr > 0))

    # Sortino from chained daily returns
    daily_rets = np.diff(scaled) / scaled[:-1]
    daily_rets = daily_rets[np.isfinite(daily_rets)]
    neg_rets = daily_rets[daily_rets < 0]
    dn_vol = float(neg_rets.std() * np.sqrt(252)) if len(neg_rets) > 0 else 0.0001
    sortino = ann_return / dn_vol if dn_vol > 0 else 0

    # Calmar & RoMAD (cap RoMAD to avoid display overflow on multi-decade runs)
    calmar = ann_return / abs(overall_dd) if overall_dd != 0 else 0
    romad = min(oos_total / abs(overall_dd), 1e6) if overall_dd != 0 else 0

    return WalkForwardResult(
        oos_total_return=oos_total,
        oos_annualized=ann_return,
        oos_max_dd=overall_dd,
        oos_sortino=sortino,
        oos_calmar=calmar,
        oos_romad=romad,
        oos_win_rate=win_rate,
        n_folds=len(folds),
        avg_positions=float(np.mean(total_positions)),
        consistency=consistency,
        params=params,
        fold_returns=fold_returns,
    )


# ── Parameter grid ───────────────────────────────────────────────────────────


def build_param_grid() -> list[ScoringParams]:
    configs = []
    lookbacks = [
        (21, 63, 126), (21, 63, 252), (42, 126, 252),
        (63, 126, 252), (63, 189, 252),
    ]
    weight_schemes = [
        (0.2, 0.4, 0.4), (0.4, 0.4, 0.2), (0.5, 0.3, 0.2),
        (0.1, 0.3, 0.6), (0.33, 0.34, 0.33),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
    ]
    for lb, ws, skip, sortino, smooth, earnings, n_pos in product(
        lookbacks, weight_schemes, [0, 21], [True, False], [True, False],
        [True, False], [5, 8, 10, 15, 20],
    ):
        if lb[0] <= skip:
            continue
        configs.append(ScoringParams(
            lb_short=lb[0], lb_mid=lb[1], lb_long=lb[2],
            w_short=ws[0], w_mid=ws[1], w_long=ws[2],
            skip=skip, use_sortino=sortino, use_smoothness=smooth,
            use_earnings=earnings, max_positions=n_pos,
        ))
    return configs


# ── Table builder (DRY) ─────────────────────────────────────────────────────


def _fmt(r: WalkForwardResult) -> dict[str, str]:
    """Pre-format all metrics for a result row."""
    return {
        "ret": f"{r.oos_total_return * 100:+.1f}%",
        "ann": f"{r.oos_annualized * 100:+.1f}%",
        "dd": f"{r.oos_max_dd * 100:.1f}%",
        "sortino": f"{r.oos_sortino:.2f}",
        "calmar": f"{r.oos_calmar:.2f}",
        "romad": f"{r.oos_romad:.1f}",
        "win": f"{r.oos_win_rate * 100:.0f}%",
        "pos": f"{r.avg_positions:.0f}",
        "params": r.label(),
    }


def build_table(
    title: str,
    results: list[WalkForwardResult],
    limit: int,
    highlight_col: str,
    columns: list[str],
) -> Table:
    """Build a rich Table from results. Columns chosen from _fmt keys."""
    style_map = {
        "ret": ("OOS Ret", "bold green"),
        "ann": ("Ann.", ""),
        "dd": ("MaxDD", "red"),
        "sortino": ("Sortino", "cyan"),
        "calmar": ("Calmar", "yellow"),
        "romad": ("RoMAD", ""),
        "win": ("Win%", ""),
        "pos": ("Pos", ""),
        "params": ("Params", ""),
    }
    table = Table(title=title)
    table.add_column("#", style="dim", width=3)
    for col in columns:
        label, style = style_map[col]
        s = f"bold {style}" if col == highlight_col else style
        table.add_column(label, justify="right" if col != "params" else "left", style=s)

    for i, r in enumerate(results[:limit]):
        f = _fmt(r)
        table.add_row(str(i + 1), *(f[c] for c in columns))

    return table


ALL_COLS = ["ret", "ann", "dd", "sortino", "calmar", "romad", "win", "pos", "params"]


# ── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--top", default=20, help="Show top N results.")
@click.option("--period", default="max", help="Price history period.")
@click.option("--workers", default=8, help="Parallel workers.")
@click.option("--min-train", default=252, help="Min training days.")
@click.option("--oos-window", default=126, help="OOS test window days.")
@click.option("--max-dd-cap", default=0.50, help="MaxDD cap for survivable scenario.")
def main(top: int, period: str, workers: int, min_train: int, oos_window: int, max_dd_cap: float):
    """Walk-forward momentum parameter sweep — vectorized."""
    console.print(f"[bold]Fetching {len(TICKERS)} tickers ({period})...[/]")
    prices, dates, fetched = fetch_all_numpy(TICKERS, period)
    n_days = prices.shape[0]
    console.print(f"[green]Got {len(fetched)} tickers, {n_days} days ({dates[0]} → {dates[-1]})[/]")

    # Fetch earnings data for earnings momentum
    console.print("[bold]Fetching earnings data...[/]")
    earnings = fetch_all_earnings(fetched)
    n_with_earnings = len(earnings)
    console.print(f"[green]Got earnings for {n_with_earnings}/{len(fetched)} tickers[/]")
    earn_mom = build_earnings_momentum(earnings, dates, fetched)

    # Pre-compute folds (shared across all param combos)
    folds = build_folds(prices, min_train, oos_window)
    console.print(f"[bold]{len(folds)} valid folds[/] (min {MIN_TICKERS_PER_FOLD} tickers/fold)")
    if folds:
        console.print(f"  [dim]First: {dates[folds[0][0]]}  Last: {dates[folds[-1][1]]}[/]")

    grid = build_param_grid()
    console.print(f"[bold]Sweeping {len(grid):,} combos × {len(folds)} folds...[/]")

    # Run with shared memory (initializer avoids pickling prices per task)
    results: list[WalkForwardResult] = []
    args_list = [(p, min_train, oos_window, folds) for p in grid]

    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(prices, dates, earn_mom)
    ) as pool:
        futures = {pool.submit(_worker_run, a): i for i, a in enumerate(args_list)}
        done = 0
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 200 == 0:
                console.print(f"  [dim]{done}/{len(grid)}...[/]")

    # ── Tables ───────────────────────────────────────────────────────────────

    results.sort(key=lambda r: r.oos_total_return, reverse=True)
    console.print(build_table(
        f"Top {top} by OOS Return ({len(folds)} folds)", results, top, "ret", ALL_COLS))

    by_sortino = sorted(results, key=lambda r: r.oos_sortino, reverse=True)
    console.print(build_table("Top 15 by Sortino", by_sortino, 15, "sortino", ALL_COLS))

    by_calmar = sorted(results, key=lambda r: r.oos_calmar, reverse=True)
    console.print(build_table("Top 15 by Calmar", by_calmar, 15, "calmar", ALL_COLS))

    # Survivable: DD capped
    dd_cap_pct = max_dd_cap * 100
    survivable = sorted(
        [r for r in results if abs(r.oos_max_dd) <= max_dd_cap],
        key=lambda r: r.oos_total_return, reverse=True,
    )
    console.print(build_table(
        f"SURVIVABLE (DD≤{dd_cap_pct:.0f}%) — Best Return", survivable, 15, "ret", ALL_COLS))

    surv_calmar = sorted(survivable, key=lambda r: r.oos_calmar, reverse=True)
    console.print(build_table(
        f"SURVIVABLE (DD≤{dd_cap_pct:.0f}%) — Best Calmar", surv_calmar, 10, "calmar", ALL_COLS))

    # ── Summary ──────────────────────────────────────────────────────────────

    oos_rets = np.array([r.oos_total_return for r in results])
    console.print(f"\n[bold]Summary[/]  combos={len(results):,}  folds={len(folds)}")
    console.print(f"  OOS return — best: {oos_rets.max()*100:+.1f}%  "
                  f"median: {np.median(oos_rets)*100:+.1f}%  "
                  f"worst: {oos_rets.min()*100:+.1f}%")
    console.print(f"  Survivable: {len(survivable)}/{len(results)}")

    # Per-fold detail for top 3 survivable
    console.print(f"\n[bold]Top 3 survivable fold returns:[/]")
    for i, r in enumerate(survivable[:3]):
        folds_str = " → ".join(f"{fr*100:+.1f}%" for fr in r.fold_returns)
        console.print(f"  #{i+1} [{r.label()}] DD={r.oos_max_dd*100:.1f}%")
        console.print(f"      {folds_str}")

    # Parameter dominance
    top50 = survivable[:min(50, len(survivable))]
    if top50:
        console.print(f"\n[bold]Param dominance (top 50 survivable):[/]")
        s0 = sum(1 for r in top50 if r.params.skip == 0)
        console.print(f"  skip: 0={s0}  21={len(top50)-s0}")
        sy = sum(1 for r in top50 if r.params.use_sortino)
        console.print(f"  sortino-adj: yes={sy}  no={len(top50)-sy}")
        sm = sum(1 for r in top50 if r.params.use_smoothness)
        console.print(f"  smooth: yes={sm}  no={len(top50)-sm}")
        ey = sum(1 for r in top50 if r.params.use_earnings)
        console.print(f"  earnings-mom: yes={ey}  no={len(top50)-ey}")
        pc = Counter(r.params.max_positions for r in top50)
        console.print(f"  positions: {' '.join(f'{k}={v}' for k,v in sorted(pc.items()))}")
        wc = Counter((r.params.w_short, r.params.w_mid, r.params.w_long) for r in top50)
        for wt, cnt in wc.most_common(3):
            console.print(f"    w={wt[0]:.1f}/{wt[1]:.1f}/{wt[2]:.1f}: {cnt}")


if __name__ == "__main__":
    main()
