"""
Momentum/factor switching backtest using mfapi.in NAV data.

Replaces Momentum_Switch_Cash.py, 02_Alpha_Switch_Cash.py, 03_Alpha_Weekly_Switch.py
which depended on local CSV files.

Usage:
    uv run python india/scripts/momentum_switch_mfapi.py
    uv run python india/scripts/momentum_switch_mfapi.py --frequency weekly
    uv run python india/scripts/momentum_switch_mfapi.py \
        --scheme-code 148703 --name "UTI N200 Mom30"
"""

import warnings
from datetime import datetime
from enum import Enum

import click
import httpx
import numpy as np
import polars as pl

warnings.filterwarnings("ignore")

# ── Scheme codes (Direct Growth plans from mfapi.in) ─────────────────────────

SCHEMES = {
    # Momentum factor
    "UTI N200 Mom30": 148703,
    "Nippon N500 Mom50": 152881,
    "Motilal N500 Mom50": 152875,
    # Alpha + Low Vol multi-factor
    "ICICI Alpha LowVol30": 149158,
    "Nippon Alpha LowVol30": 150487,
    # Low Volatility
    "ICICI N100 LowVol30": 148822,
    # Value
    "Nippon N50 Value20": 148721,
    # Active funds (long history, good for backtesting)
    "PPFAS Flexi Cap": 122639,
    "Quant Small Cap": 120828,
    "Nippon Small Cap": 118778,
    "HDFC Mid Cap": 118989,
    # Benchmark
    "UTI Nifty 50": 120716,
}


class Frequency(str, Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"


# ── Data fetching ─────────────────────────────────────────────────────────────


def fetch_nav(scheme_code: int) -> pl.DataFrame | None:
    """Fetch full NAV history from mfapi.in. Returns df with [date, nav] columns."""
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    entries = data.get("data", [])
    if not entries:
        return None

    records = []
    for item in entries:
        dt = datetime.strptime(item["date"], "%d-%m-%Y")
        nav = float(item["nav"])
        records.append({"date": dt, "nav": nav})

    return pl.DataFrame(records).sort("date")


def resample(df: pl.DataFrame, freq: Frequency) -> pl.DataFrame:
    """Resample daily NAV to monthly (last trading day) or weekly (Friday close)."""
    if freq == Frequency.MONTHLY:
        return (
            df.with_columns(pl.col("date").dt.truncate("1mo").alias("period"))
            .group_by("period")
            .agg(pl.col("nav").last().alias("nav"))
            .sort("period")
            .rename({"period": "date"})
        )
    # Weekly: truncate to Monday, take last value per week
    return (
        df.with_columns(pl.col("date").dt.truncate("1w").alias("period"))
        .group_by("period")
        .agg(pl.col("nav").last().alias("nav"))
        .sort("period")
        .rename({"period": "date"})
    )


# ── Switching logic ───────────────────────────────────────────────────────────


def compute_pct_change(df: pl.DataFrame, periods: int = 1) -> pl.DataFrame:
    """Add percent change column."""
    return df.with_columns(
        ((pl.col("nav") / pl.col("nav").shift(periods) - 1) * 100)
        .round(2)
        .alias("pct_change")
    )


def compute_quantiles(
    series: pl.Series, quantiles: list[float]
) -> dict[float, float]:
    """Compute quantile values from a polars Series."""
    return {q: series.quantile(q) for q in quantiles}


def run_switch(
    df: pl.DataFrame,
    col_name: str,
    initial_value: str,
    to_cash: float,
    to_momentum: float,
) -> pl.DataFrame:
    """Apply momentum/cash switching rule based on pct_change thresholds."""
    pct = df["pct_change"].to_list()
    switch_list = []

    for idx in range(len(pct)):
        if idx == 0:
            switch_list.append(initial_value)
            continue

        prev = switch_list[idx - 1]
        change = pct[idx]

        if change is None:
            switch_list.append(initial_value)
        elif change < to_cash:
            switch_list.append("CASH")
        elif change > to_momentum:
            switch_list.append("MOMENTUM")
        else:
            switch_list.append(prev)

    return df.with_columns(pl.Series(name=col_name, values=switch_list))


def apply_strategy(
    df: pl.DataFrame, strategy_col: str, initial_amount: float = 1000.0
) -> pl.DataFrame:
    """Simulate equity curve: in MOMENTUM follow NAV, in CASH hold flat."""
    navs = df["nav"].to_list()
    signals = df[strategy_col].to_list()
    amounts = [initial_amount]

    for idx in range(1, len(navs)):
        if signals[idx - 1] == "MOMENTUM":
            amounts.append(amounts[-1] * (navs[idx] / navs[idx - 1]))
        else:
            amounts.append(amounts[-1])

    amount_col = f"amount_{strategy_col}"
    return df.with_columns(pl.Series(name=amount_col, values=amounts).round(2))


# ── Backtest stats ────────────────────────────────────────────────────────────


def backtest_stats(
    df: pl.DataFrame,
    amount_cols: list[str],
    periods_per_year: int,
    rf_rate: float = 0.07,
) -> pl.DataFrame:
    """Compute CAGR, risk, Sharpe, Sortino, Max DD, Calmar for each amount column."""
    rows = []
    n = df.height

    for col in amount_cols:
        vals = df[col].to_numpy().astype(np.float64)
        years = n / periods_per_year
        cagr = (vals[-1] / vals[0]) ** (1 / years) - 1

        rets = np.diff(vals) / vals[:-1]
        annual_risk = np.std(rets, ddof=1) * np.sqrt(periods_per_year)

        sharpe = (cagr - rf_rate) / annual_risk if annual_risk > 0 else 0

        # Max drawdown
        cummax = np.maximum.accumulate(vals)
        dd = (cummax - vals) / cummax
        max_dd = dd.max()

        # Sortino
        downside = rets[rets < 0]
        if len(downside) > 1:
            downside_std = (
                np.std(downside, ddof=1) * np.sqrt(periods_per_year)
            )
        else:
            downside_std = np.nan
        sortino = (
            (cagr - rf_rate) / downside_std
            if downside_std and downside_std > 0
            else 0
        )

        calmar = cagr / max_dd if max_dd > 0 else 0

        rows.append(
            {
                "strategy": col,
                "cagr": f"{cagr * 100:.1f}%",
                "annual_risk": f"{annual_risk * 100:.1f}%",
                "sharpe": f"{sharpe:.2f}",
                "sortino": f"{sortino:.2f}",
                "max_dd": f"{max_dd * 100:.1f}%",
                "calmar": f"{calmar:.2f}",
                "final_value": f"{vals[-1]:.0f}",
            }
        )

    return pl.DataFrame(rows)


def count_switches(df: pl.DataFrame, strategy_col: str) -> tuple[int, int]:
    """Return (total switches, sell count i.e. MOMENTUM->CASH)."""
    signals = df[strategy_col].to_list()
    changes = sum(1 for i in range(1, len(signals)) if signals[i] != signals[i - 1])
    sells = sum(
        1 for i in range(1, len(signals))
        if signals[i] != signals[i - 1] and signals[i] == "CASH"
    )
    return changes, sells


# ── Main ──────────────────────────────────────────────────────────────────────


def run_backtest_for_scheme(
    name: str,
    scheme_code: int,
    freq: Frequency,
    lookback_quantile_periods: int,
) -> None:
    """Run the full switching backtest for one scheme."""
    print(f"\n{'=' * 90}")
    print(f"  {name} (scheme: {scheme_code}, freq: {freq.value})")
    print(f"{'=' * 90}")

    print("Fetching NAV data...", end=" ")
    raw = fetch_nav(scheme_code)
    if raw is None or raw.height < 100:
        print("insufficient data")
        return
    print(f"{raw.height} daily NAVs ({raw['date'].min()} to {raw['date'].max()})")

    df = resample(raw, freq)
    periods_per_year = 12 if freq == Frequency.MONTHLY else 52
    change_periods = 1 if freq == Frequency.MONTHLY else 4  # monthly vs 4-week

    df = compute_pct_change(df, periods=change_periods)
    df = df.filter(pl.col("pct_change").is_not_null())

    if df.height < lookback_quantile_periods + 10:
        print(f"Only {df.height} periods after pct_change — too short")
        return

    # Split: first N periods for quantile estimation, rest for out-of-sample backtest
    train = df.head(lookback_quantile_periods)
    test = df.slice(lookback_quantile_periods)

    train_pct = train["pct_change"]
    quantiles = [0.10, 0.25, 0.50, 0.75, 0.90]
    qmap = compute_quantiles(train_pct, quantiles)

    print(f"Train: {train.height} periods | Test: {test.height} periods")
    print("Quantiles: " + "  ".join(f"P{int(q*100)}={v:.1f}%" for q, v in qmap.items()))

    # Three strategy variants
    strategies = {
        "dynamic": {"to_cash": qmap[0.10], "to_momentum": qmap[0.25], "initial": "MOMENTUM"},
        "optimistic": {"to_cash": qmap[0.25], "to_momentum": qmap[0.25], "initial": "MOMENTUM"},
        "pessimistic": {"to_cash": qmap[0.50], "to_momentum": qmap[0.75], "initial": "MOMENTUM"},
    }

    result = test.clone()
    amount_cols = ["nav"]  # benchmark = buy-and-hold

    for sname, params in strategies.items():
        result = run_switch(result, sname, params["initial"], params["to_cash"], params["to_momentum"])
        result = apply_strategy(result, sname)
        amount_cols.append(f"amount_{sname}")

    # Normalize benchmark to 1000
    nav_start = result["nav"][0]
    result = result.with_columns(
        (pl.col("nav") / nav_start * 1000).round(2).alias("nav")
    )

    # Stats
    stats = backtest_stats(result, amount_cols, periods_per_year)
    print(f"\n{'─' * 90}")
    print(stats)

    # Switch counts
    print(f"\n{'─' * 90}")
    print(f"{'Strategy':<20} {'Switches':>10} {'Sells':>10}")
    print(f"{'─' * 40}")
    for sname in strategies:
        changes, sells = count_switches(result, sname)
        print(f"{sname:<20} {changes:>10} {sells:>10}")

    # Recent signals
    recent = result.tail(6).select(
        ["date"] + list(strategies.keys()) + [f"amount_{s}" for s in strategies]
    )
    print(f"\n{'─' * 90}")
    print(f"Recent {6} periods:")
    print(recent)


@click.command()
@click.option(
    "--frequency",
    type=click.Choice(["monthly", "weekly"]),
    default="monthly",
    help="Resampling frequency",
)
@click.option("--scheme-code", type=int, default=None, help="Single scheme code to backtest")
@click.option("--name", type=str, default=None, help="Name for single scheme")
@click.option(
    "--lookback",
    type=int,
    default=None,
    help="Periods for quantile estimation (default: 60 monthly, 120 weekly)",
)
def main(frequency: str, scheme_code: int | None, name: str | None, lookback: int | None):
    freq = Frequency(frequency)
    default_lookback = 60 if freq == Frequency.MONTHLY else 120

    if lookback is None:
        lookback = default_lookback

    print("=" * 90)
    print("MOMENTUM SWITCHING BACKTEST (mfapi.in)")
    print(f"Frequency: {freq.value} | Lookback: {lookback} periods")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 90)

    if scheme_code:
        label = name or f"Scheme {scheme_code}"
        run_backtest_for_scheme(label, scheme_code, freq, lookback)
    else:
        for fund_name, code in SCHEMES.items():
            run_backtest_for_scheme(fund_name, code, freq, lookback)


if __name__ == "__main__":
    main()
