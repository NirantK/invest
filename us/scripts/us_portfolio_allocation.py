"""
US Portfolio Allocation using Sortino-weighted Momentum

Rewritten to use polars + rich for clean, fast computation.
"""

import click
import numpy as np
import polars as pl
import yfinance as yf
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Configuration
TICKERS = [
    # === Precious Metals ===
    "WPM",  # Wheaton Precious Metals - 50% silver streamer
    "PAAS",  # Pan American Silver - silver miner
    "FNV",  # Franco-Nevada - gold streamer + energy royalties
    "AEM",  # Agnico Eagle - lowest AISC (~$1,275), 87% safe jurisdictions
    "HL",  # Hecla Mining - silver-primary, negative cash costs via byproducts
    # === Energy: Integrated Oil Majors ===
    "XOM",  # Exxon Mobil
    "CVX",  # Chevron
    "CNQ",  # Canadian Natural Resources
    "SU",  # Suncor Energy
    "CVE",  # Cenovus Energy
    "XLE",  # Energy Select Sector SPDR
    # === Energy: Midstream (1099 C-corps only) ===
    "ENB",  # Enbridge
    "TRP",  # TC Energy
    "KMI",  # Kinder Morgan
    "WMB",  # Williams Companies
    "OKE",  # ONEOK
    # === Energy: Refineries ===
    "VLO",  # Valero Energy
    "PSX",  # Phillips 66
    "MPC",  # Marathon Petroleum
    "DINO",  # HF Sinclair
    # === Energy: E&P ===
    "COP",  # ConocoPhillips
    "DVN",  # Devon Energy
    "OXY",  # Occidental Petroleum
    # === Alpha Architect (Wes Gray) ===
    "QVAL",  # US Quantitative Value - concentrated deep value, EBIT/TEV
    "QMOM",  # US Quantitative Momentum - concentrated, monthly rebalance
    "IVAL",  # Intl Quantitative Value
    "IMOM",  # Intl Quantitative Momentum
    # === DFA (Dimensional) ===
    "DFSV",  # DFA US Small Cap Value - strongest value loading
    "DXIV",  # DFA International Vector Equity - aggressive multi-factor
    # === Avantis ===
    "AVUV",  # Avantis US Small Cap Value - flagship
    "AVDV",  # Avantis International Small Cap Value (kept over DISV)
    "AVES",  # Avantis Emerging Markets Value (kept over DFEV/AVEM)
    # === Regional Factor ETFs ===
    "EWJV",  # iShares MSCI Japan Value
    "DFJ",  # WisdomTree Japan SmallCap Dividend
    "DFE",  # WisdomTree Europe SmallCap Dividend (quality + momentum screened)
    "EWZS",  # iShares MSCI Brazil Small-Cap
    "FLN",  # First Trust Latin America AlphaDEX (multi-factor)
    # === Ex-US Emerging Markets ===
    "FRDM",  # Freedom 100 EM ETF - economic freedom-weighted
    # === Bitcoin proxy (special DCA rules) ===
    "MSTR",
    # === Software compounder (discretionary) ===
    "CSU.TO",  # Constellation Software (TSX)
]

BITCOIN_DCA_TARGET_PCT = 0.05
BITCOIN_MONTHLY_DCA_PCT = 0.001
DCA_WEEKS = 12
ROUND_TO = 100
SKIP_1M = 21
LOOKBACK_3M = 63
LOOKBACK_6M = 126
LOOKBACK_12M = 252
MAX_POSITIONS = 25

# Category groupings (for reporting only)
PRECIOUS_METALS = ["WPM", "PAAS", "FNV", "AEM", "HL"]
ENERGY = [
    "XOM",
    "CVX",
    "XLE",
    "CNQ",
    "SU",
    "CVE",
    "ENB",
    "TRP",
    "KMI",
    "WMB",
    "OKE",
    "VLO",
    "PSX",
    "MPC",
    "DINO",
    "COP",
    "DVN",
    "OXY",
]
FACTOR_US = ["QVAL", "QMOM", "AVUV", "DFSV"]
FACTOR_INTL = ["IVAL", "IMOM", "DXIV", "AVDV", "DFE", "EWJV", "DFJ"]
FACTOR_EM = ["FRDM", "AVES", "FLN", "EWZS"]
BITCOIN = ["MSTR"]
SOFTWARE = ["CSU.TO"]

CATEGORIES = [
    ("Precious Metals", PRECIOUS_METALS),
    ("Energy", ENERGY),
    ("Factor: US", FACTOR_US),
    ("Factor: Intl", FACTOR_INTL),
    ("Factor: EM", FACTOR_EM),
    ("Bitcoin", BITCOIN),
    ("Software", SOFTWARE),
]


def _build_total_return(close: np.ndarray, divs: np.ndarray) -> np.ndarray:
    """Build total return index from close prices and dividends (numpy)."""
    tri = close.copy()
    cumulative_div_yield = 0.0

    for i in range(1, len(close)):
        if close[i - 1] != 0:
            div_yield = divs[i] / close[i - 1]
        else:
            div_yield = 0
        cumulative_div_yield = (1 + cumulative_div_yield) * (1 + div_yield) - 1
        tri[i] = close[i] * (1 + cumulative_div_yield)

    return tri


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pl.DataFrame:
    """Fetch total return prices (includes reinvested dividends) as polars DataFrame."""
    frames = []
    for ticker in tickers:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            continue
        close = hist["Close"].values
        divs = hist["Dividends"].values
        tri = _build_total_return(close, divs)

        # Convert to string date for reliable joining
        date_strs = [d.strftime("%Y-%m-%d") for d in hist.index.to_pydatetime()]
        frames.append(
            pl.DataFrame({"date": date_strs, ticker: tri})
        )

    if not frames:
        return pl.DataFrame()

    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, on="date", how="inner")
    return result.sort("date")


def _score_one(ticker: str, prices: np.ndarray, returns: np.ndarray) -> dict:
    """Compute all metrics for one ticker in numpy. Returns dict for polars row."""
    n = len(prices)

    # Momentum with 1-month skip
    def mom(lookback):
        if n < lookback + SKIP_1M:
            return 0.0
        end_idx = n - SKIP_1M
        start_idx = end_idx - lookback
        return (prices[end_idx - 1] / prices[start_idx]) - 1

    mom_3m = mom(LOOKBACK_3M)
    mom_6m = mom(LOOKBACK_6M)
    mom_12m = mom(LOOKBACK_12M)
    wt_mom = 0.2 * mom_3m + 0.4 * mom_6m + 0.4 * mom_12m

    # Downside volatility
    neg_returns = returns[returns < 0]
    dn_vol = neg_returns.std() * np.sqrt(252) if len(neg_returns) > 0 else 0.0001

    # Quality (R² of log price path)
    end_idx = n - SKIP_1M if SKIP_1M > 0 else n
    start_idx = max(0, end_idx - LOOKBACK_12M)
    window = prices[start_idx:end_idx]

    if len(window) < 20:
        quality = 0.0
    else:
        log_prices = np.log(window)
        x = np.arange(len(log_prices))
        coeffs = np.polyfit(x, log_prices, 1)
        fitted = np.polyval(coeffs, x)
        ss_res = np.sum((log_prices - fitted) ** 2)
        ss_tot = np.sum((log_prices - log_prices.mean()) ** 2)
        quality = max(1 - (ss_res / ss_tot), 0.0) if ss_tot > 0 else 0.0

    # Score
    score = (wt_mom * quality) / dn_vol if dn_vol > 0 else 0.0

    # Drawdown metrics
    running_max = np.maximum.accumulate(prices)
    drawdown = (prices - running_max) / running_max

    max_dd = drawdown.min()
    current_dd = drawdown[-1]

    # Drawdown durations
    in_dd = drawdown < 0
    periods = []
    start = None
    for i in range(len(in_dd)):
        if in_dd[i] and start is None:
            start = i
        elif not in_dd[i] and start is not None:
            periods.append(i - start)
            start = None
    if start is not None:
        periods.append(len(in_dd) - start)

    max_dd_dur = max(periods) if periods else 0
    avg_dd_dur = np.mean(periods) if periods else 0

    # Rolling 3M max drawdown
    window_size = 63
    rolling_3m_dd = []
    for i in range(window_size, len(prices)):
        w = prices[i - window_size : i]
        w_max = np.maximum.accumulate(w)
        w_dd = ((w - w_max) / w_max).min()
        rolling_3m_dd.append(w_dd)
    worst_3m_dd = min(rolling_3m_dd) if rolling_3m_dd else max_dd

    return {
        "ticker": ticker,
        "mom_3m": mom_3m,
        "mom_6m": mom_6m,
        "mom_12m": mom_12m,
        "wt_mom": wt_mom,
        "quality": quality,
        "dn_vol": dn_vol,
        "score": score,
        "max_dd": max_dd,
        "max_dd_dur": max_dd_dur,
        "avg_dd_dur": avg_dd_dur,
        "current_dd": current_dd,
        "worst_3m_dd": worst_3m_dd,
    }


def build_scores(prices: pl.DataFrame) -> pl.DataFrame:
    """Compute all per-ticker metrics. Returns one row per ticker."""
    tickers = [c for c in prices.columns if c != "date"]
    rows = []
    for t in tickers:
        p = prices[t].to_numpy()
        r = np.diff(p) / p[:-1]
        rows.append(_score_one(t, p, r))
    return pl.DataFrame(rows)


def allocate(
    scores: pl.DataFrame, capital: int, min_pct: float, max_pct: float
) -> pl.DataFrame:
    """Filter, weight, constrain. Returns allocation DataFrame."""
    # Filter positive momentum
    df = scores.filter(pl.col("wt_mom") > 0)

    if len(df) == 0:
        return pl.DataFrame()

    # Weight by score
    total_score = df["score"].sum()
    df = df.with_columns((pl.col("score") / total_score).alias("weight"))

    # Cap at MAX_POSITIONS
    df = df.sort("score", descending=True).head(MAX_POSITIONS)

    # Iterative min/max constraints
    min_amount = capital * min_pct
    max_amount = capital * max_pct

    # Convert to pandas for iterative constraint logic (polars doesn't support item assignment)
    alloc_dict = {row["ticker"]: row["weight"] * capital for row in df.iter_rows(named=True)}

    for _ in range(100):
        changed = False

        # Zero out below minimum
        for t in list(alloc_dict.keys()):
            if 0 < alloc_dict[t] < min_amount:
                alloc_dict[t] = 0
                changed = True

        # Cap above maximum
        for t in alloc_dict:
            if alloc_dict[t] > max_amount:
                alloc_dict[t] = max_amount
                changed = True

        # Renormalize
        current_total = sum(alloc_dict.values())
        if abs(current_total - capital) > 1:
            scale = capital / current_total
            alloc_dict = {t: v * scale for t, v in alloc_dict.items()}
            changed = True

        if not changed:
            break

    # Rebuild DataFrame
    alloc_df = pl.DataFrame(
        [{"ticker": t, "alloc_usd": alloc_dict[t]} for t in alloc_dict if alloc_dict[t] > 0]
    )

    # Join back with scores
    return df.join(alloc_df, on="ticker", how="inner")


def round_to_nearest(value: float, multiple: int = 1000) -> int:
    """Round to nearest multiple (default $1000, fallback to $100 for small amounts)."""
    if value < 500:
        return round(value / 100) * 100
    return round(value / multiple) * multiple


def print_scores_table(scores: pl.DataFrame):
    """Print scores table (momentum + drawdown in one)."""
    table = Table(title="Ticker Scores (3Y History)", show_header=True, header_style="bold magenta")
    table.add_column("Ticker", style="cyan", justify="left")
    table.add_column("3M", justify="right")
    table.add_column("6M", justify="right")
    table.add_column("12M", justify="right")
    table.add_column("Wt Mom", justify="right")
    table.add_column("Quality", justify="right")
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Max DD", justify="right")
    table.add_column("Status", justify="center")

    for row in scores.sort("score", descending=True).iter_rows(named=True):
        status = "[green]PASS[/]" if row["wt_mom"] > 0 else "[red]FAIL[/]"
        table.add_row(
            row["ticker"],
            f"{row['mom_3m']*100:+.1f}%",
            f"{row['mom_6m']*100:+.1f}%",
            f"{row['mom_12m']*100:+.1f}%",
            f"{row['wt_mom']*100:+.1f}%",
            f"{row['quality']:.3f}",
            f"{row['score']:.2f}",
            f"{row['max_dd']*100:.1f}%",
            status,
        )

    console.print(table)


def print_allocation_table(alloc: pl.DataFrame, prices: pl.DataFrame, capital: int):
    """Print allocation + weekly DCA table."""
    latest_prices = {row["ticker"]: prices.select(row["ticker"]).tail(1).item() for row in alloc.iter_rows(named=True)}

    table = Table(title=f"Final Allocation (${capital:,})", show_header=True, header_style="bold green")
    table.add_column("Ticker", style="cyan", justify="left")
    table.add_column("Allocation", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Shares", justify="right")
    table.add_column("Weekly DCA", justify="right", style="bold")

    for row in alloc.sort("alloc_usd", descending=True).iter_rows(named=True):
        ticker = row["ticker"]
        alloc_usd = round_to_nearest(row["alloc_usd"])
        price = latest_prices[ticker]
        shares = alloc_usd / price
        weight = alloc_usd / capital * 100
        weekly = round_to_nearest(alloc_usd / DCA_WEEKS, ROUND_TO)

        table.add_row(
            ticker,
            f"${alloc_usd:,}",
            f"{weight:.1f}%",
            f"${price:.2f}",
            f"{shares:.2f}",
            f"${weekly:,}",
        )

    console.print(table)


def print_portfolio_summary(alloc: pl.DataFrame, scores: pl.DataFrame, capital: int):
    """Print portfolio summary panel (risk, momentum, drawdown, categories, MSTR)."""
    # Compute weighted metrics
    weights = alloc.with_columns(
        (pl.col("alloc_usd") / pl.col("alloc_usd").sum()).alias("w")
    )

    joined = weights.join(scores, on="ticker", how="inner")

    w_mom_3m = (joined["w"] * joined["mom_3m"]).sum()
    w_mom_6m = (joined["w"] * joined["mom_6m"]).sum()
    w_mom_12m = (joined["w"] * joined["mom_12m"]).sum()
    w_quality = (joined["w"] * joined["quality"]).sum()
    w_score = (joined["w"] * joined["score"]).sum()
    w_dn_vol = (joined["w"] * joined["dn_vol"]).sum()
    w_max_dd = (joined["w"] * joined["max_dd"]).sum()
    w_current_dd = (joined["w"] * joined["current_dd"]).sum()
    w_worst_3m_dd = (joined["w"] * joined["worst_3m_dd"]).sum()

    num_pos = len(alloc)
    max_weight = weights["w"].max()
    top_3 = weights.sort("w", descending=True).head(3)["w"].sum()

    avg_mom = 0.2 * w_mom_3m + 0.4 * w_mom_6m + 0.4 * w_mom_12m
    pain_ratio = avg_mom / abs(w_max_dd) if w_max_dd != 0 else 0

    # Category exposure
    cat_lines = []
    for label, group in CATEGORIES:
        cat_alloc = alloc.filter(pl.col("ticker").is_in(group))["alloc_usd"].sum()
        if cat_alloc > 0:
            cat_lines.append(f"{label:<20s} ${cat_alloc:>8,.0f} ({cat_alloc/capital*100:>5.1f}%)")

    # MSTR footnote
    mstr_row = scores.filter(pl.col("ticker") == "MSTR")
    if len(mstr_row) > 0:
        mstr_mom = mstr_row["wt_mom"].item()
        monthly_dca = capital * BITCOIN_MONTHLY_DCA_PCT
        mstr_note = f"MSTR: DCA ${monthly_dca:,.0f}/mo (momentum: {mstr_mom*100:+.1f}%)"
    else:
        mstr_note = "MSTR: Not in universe"

    summary = f"""[bold]Portfolio Risk[/]
  Positions: {num_pos} | Top 3: {top_3*100:.1f}% | Max weight: {max_weight*100:.1f}%
  Downside vol: {w_dn_vol*100:.1f}%

[bold]Momentum[/]
  3M: {w_mom_3m*100:+.1f}% | 6M: {w_mom_6m*100:+.1f}% | 12M: {w_mom_12m*100:+.1f}%
  Quality: {w_quality:.3f} | Score: {w_score:.2f}

[bold]Drawdown[/]
  Max DD: {w_max_dd*100:.1f}% | Current: {w_current_dd*100:.1f}% | Worst 3M: {w_worst_3m_dd*100:.1f}%
  Pain ratio: {pain_ratio:.2f}

[bold]Categories[/]
{chr(10).join(cat_lines)}

[bold]Special Positions[/]
  {mstr_note}
"""

    console.print(Panel(summary, title="Portfolio Summary", border_style="blue"))


@click.command()
@click.option(
    "--min-allocation",
    "-m",
    type=float,
    default=0.05,
    help="Minimum allocation percentage.",
)
@click.option(
    "--max-allocation",
    "-M",
    type=float,
    default=1.0,
    help="Maximum allocation percentage.",
)
@click.option(
    "--capital",
    "-c",
    type=int,
    default=40000,
    help="Total capital to allocate.",
)
def main(min_allocation: float, max_allocation: float, capital: int):
    """US Portfolio Allocation - Sortino-weighted Momentum."""
    console.print(f"\n[bold cyan]Fetching data for {len(TICKERS)} tickers...[/]")

    prices = fetch_total_return_index(TICKERS)

    if prices.is_empty():
        console.print("[red]No data fetched. Exiting.[/]")
        return

    console.print(
        f"[green]Data range: {prices['date'].min()} to {prices['date'].max()}[/]\n"
    )

    scores = build_scores(prices)
    print_scores_table(scores)

    alloc = allocate(scores, capital, min_allocation, max_allocation)

    if alloc.is_empty():
        console.print("[yellow]No positions passed momentum filter.[/]")
        return

    console.print()
    print_allocation_table(alloc, prices, capital)
    console.print()
    print_portfolio_summary(alloc, scores, capital)


if __name__ == "__main__":
    main()
