"""
US Portfolio Allocation using Sortino-weighted Momentum

Rewritten to use polars + rich for clean, fast computation.
"""

import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from functools import wraps
from pathlib import Path

import click
import numpy as np
import polars as pl
import yfinance as yf
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

CACHE_DIR = Path(__file__).parent.parent / "data" / "price_cache"


def daily_disk_cache(func):
    """Cache results to disk keyed by (args, today). Auto-stale after midnight."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        key = "__".join(str(a) for a in args)
        cache_file = CACHE_DIR / f"{func.__name__}__{key}__{today}.pkl"

        if cache_file.exists():
            return pickle.loads(cache_file.read_bytes())

        result = func(*args, **kwargs)
        if result is not None:
            cache_file.write_bytes(pickle.dumps(result))

        # Evict stale entries (any file not from today)
        for f in CACHE_DIR.glob(f"{func.__name__}__*.pkl"):
            if not f.name.endswith(f"__{today}.pkl"):
                f.unlink(missing_ok=True)

        return result

    return wrapper

console = Console()

# Configuration
TICKERS = [
    # === Precious Metals ===
    "WPM",  # Wheaton Precious Metals - 50% silver streamer
    "PAAS",  # Pan American Silver - silver miner
    "FNV",  # Franco-Nevada - gold streamer + energy royalties
    "AEM",  # Agnico Eagle - lowest AISC (~$1,275), 87% safe jurisdictions
    "HL",  # Hecla Mining - silver-primary, negative cash costs via byproducts
    "RGLD",  # Royal Gold - royalty/streaming, low-cost exposure to gold
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
    # === Industrial Metals ===
    "COPX",  # Global X Copper Miners - electrification supercycle
    # === Uranium / Nuclear ===
    "URA",  # Global X Uranium - nuclear renaissance, supply deficit
    # === Platinum Group Metals ===
    "PPLT",  # Aberdeen Platinum ETF - hydrogen fuel cells, autocatalysts
    # === LatAm Equity ===
    "ILF",  # iShares Latin America 40 - commodity beta, EM discount
    # === EM Fintech ===
    "NU",  # Nubank - 33% ROE, 40% growth, Brazil banking disruptor
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
    # === Ex-US Momentum ===
    "IMTM",  # iShares MSCI Intl Momentum Factor - ex-US momentum
    # === Regional Factor ETFs ===
    "EWJV",  # iShares MSCI Japan Value
    "DFJ",  # WisdomTree Japan SmallCap Dividend
    "DFE",  # WisdomTree Europe SmallCap Dividend (quality + momentum screened)
    "EWZS",  # iShares MSCI Brazil Small-Cap
    "FLN",  # First Trust Latin America AlphaDEX (multi-factor)
    # === Ex-US Emerging Markets ===
    "FRDM",  # Freedom 100 EM ETF - economic freedom-weighted
    # === Gold/Precious Metal ETFs (GOAU active since Dec 2025; SGDM/SGDJ passive Solactive factor indices) ===
    "GOAU",   # US Global GO GOLD - active (discretionary Smart Beta 2.0 since Dec 30 2025)
    "SGDM",   # Sprott Gold Miners ETF - passive, Solactive Gold Miners Custom Factors Index
    "SGDJ",   # Sprott Junior Gold Miners ETF - passive, Solactive Junior Gold Miners Custom Factors Index
    "GBUG",   # Sprott Active Gold & Silver Miners ETF - active, John Hathaway team, launched Feb 2025
    # === Sprott Uranium ETFs ===
    "URNM",   # Sprott Uranium Miners ETF - physical + miners
    "URNJ",   # Sprott Junior Uranium Miners ETF
    # === Sprott Copper ETF ===
    "COPP",   # Sprott Copper Miners ETF
    # === Bitcoin proxy (special DCA rules) ===
    "MSTR",
    # === Software compounder (discretionary) ===
    "CSU.TO",  # Constellation Software (TSX)
    # === AI Infrastructure / Data Centers ===
    "BE",      # Bloom Energy - fuel cells, data center power
    "CRWV",    # CoreWeave - AI cloud infrastructure
    "INTC",    # Intel - semiconductors
    "LITE",    # Lumentum - photonics, optical networking
    "CORZ",    # Core Scientific - bitcoin mining / AI hosting
    "IREN",    # Iris Energy - bitcoin mining / AI data centers
    "APLD",    # Applied Digital - AI data centers
    "SNDK",    # Sandisk - storage/memory
    "CIFR",    # Cipher Mining - bitcoin mining
    "EQT",     # EQT Corp - natural gas E&P
    "COHR",    # Coherent Corp - photonics, lasers
    "SEI",     # Solaris Energy Infrastructure - energy infrastructure
    "TSEM",    # Tower Semiconductor - specialty foundry
    "RIOT",    # Riot Platforms - bitcoin mining
    "KRC",     # Kilroy Realty - data center / office REIT
    "HUT",     # Hut 8 Mining - bitcoin mining / AI
    "WYFI",    # Wy-Fi - wireless infrastructure
    # === Agriculture / Fertilizer (Costa thesis: nat gas → fert → agri) ===
    "DBA",     # Invesco DB Agriculture Fund - broad agri commodity basket
    "CF",      # CF Industries - nitrogen/ammonia producer
    "IPI",     # Intrepid Potash - pure-play US potash
    # === Rick Rule picks (2026 BNN Bloomberg Top Picks) ===
    "CCJ",     # Cameco - Rule's top uranium conviction, "surest money in uranium"
    "GMIN.TO", # G Mining Ventures - Rule top pick Apr 10 2026 BNN Bloomberg
    "IPCO.TO", # International Petroleum - Rule top pick Apr 10 2026 BNN Bloomberg
    "DC-A.TO", # Dundee Corp - Rule top pick Apr 10 2026, resource holding company
    "BTG",     # B2Gold - Rule top pick Jan 5 2026, gold producer
    "ARG.TO",  # Amerigo Resources - Rule top pick Jan 5 2026, copper from tailings Chile
    "SLB",     # SLB - Rule top pick Jan 5 2026, oilfield services
    # === Rick Rule thesis ETFs ===
    "SETM",    # Sprott Critical Materials ETF - copper+uranium+lithium+nickel, +178% 1Y
    "GBUG",    # Sprott Active Gold & Silver Miners - John Hathaway manages, +113% 1Y
    # === Costa disclosed positions / named picks ===
    "ORLA",    # Orla Mining - Costa disclosed personal long position
    "AUGO",    # Aura Minerals - Costa named top mining stock pick
    "NFGC",    # New Found Gold - Costa named as company to watch
    "SNWGF",   # Snowline Gold (OTC) - Costa named as company to watch
    # === Costa/Rule thematic ETFs ===
    "GDXJ",    # VanEck Junior Gold Miners - Costa favors juniors on rebounds
    "SILJ",    # ETFMG Prime Junior Silver Miners - Rule: "real money is in stocks"
    "XOP",     # SPDR S&P Oil & Gas E&P - Rule: chronic underinvestment
    "MOO",     # VanEck Agribusiness - Costa agri thesis
]

BITCOIN_DCA_TARGET_PCT = 0.05
BITCOIN_MONTHLY_DCA_PCT = 0.001
DCA_WEEKS = 12
ROUND_TO = 100
SKIP_1M = 21
LOOKBACK_1M = 20
LOOKBACK_3M = 63
LOOKBACK_6M = 126
LOOKBACK_12M = 252
MAX_POSITIONS = 25

# Category groupings (for reporting only)
GOLD_STREAMERS = ["WPM", "FNV", "RGLD"]           # Royalty/streaming (no op risk)
SILVER_MINERS  = ["PAAS", "HL"]                   # Primary silver miners
GOLD_MINERS    = ["AEM", "GMIN.TO", "BTG"]          # Individual gold producers
GOLD_ETFs      = ["GOAU", "SGDM", "SGDJ", "GBUG", "GDXJ"] # Gold/silver miner ETF wrappers
SILVER_ETFs    = ["SILJ"]                          # Silver miner ETFs
PRECIOUS_METALS = GOLD_STREAMERS + SILVER_MINERS + GOLD_MINERS + GOLD_ETFs + SILVER_ETFs
INDUSTRIAL_METALS = ["COPX", "COPP", "ARG.TO", "SETM"]  # ARG = Amerigo Resources (copper from tailings)
URANIUM = ["URA", "URNM", "URNJ", "CCJ"]
PLATINUM = ["PPLT"]
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
    "IPCO.TO", # International Petroleum - Rick Rule top pick Apr 2026
    "SLB",     # SLB - Rule top pick Jan 2026, oilfield services
    "XOP",     # SPDR S&P Oil & Gas E&P
]
FACTOR_US = ["QVAL", "QMOM", "AVUV", "DFSV"]
FACTOR_INTL = ["IVAL", "IMOM", "IMTM", "DXIV", "AVDV", "DFE", "EWJV", "DFJ"]
FACTOR_EM = ["FRDM", "AVES", "FLN", "EWZS", "ILF", "NU"]
BITCOIN = ["MSTR"]
SOFTWARE = ["CSU.TO"]
AI_INFRA = [
    "BE", "CRWV", "INTC", "LITE", "CORZ", "IREN", "APLD", "SNDK",
    "CIFR", "EQT", "COHR", "SEI", "TSEM", "RIOT", "KRC", "HUT", "WYFI",
]
AGRICULTURE = ["DBA", "CF", "IPI", "MOO"]

CATEGORIES = [
    ("Gold Streamers", GOLD_STREAMERS),
    ("Silver Miners", SILVER_MINERS),
    ("Silver ETFs", SILVER_ETFs),
    ("Gold Miners", GOLD_MINERS),
    ("Gold/Silver ETFs", GOLD_ETFs),
    ("Industrial Metals", INDUSTRIAL_METALS),
    ("Uranium", URANIUM),
    ("Platinum", PLATINUM),
    ("Energy", ENERGY),
    ("Agriculture", AGRICULTURE),
    ("Factor: US", FACTOR_US),
    ("Factor: Intl", FACTOR_INTL),
    ("Factor: EM", FACTOR_EM),
    ("Bitcoin", BITCOIN),
    ("Software", SOFTWARE),
    ("AI Infra", AI_INFRA),
]

# If an ETF is selected, these individual tickers are blocked (already embedded in the ETF).
# Format: {etf: (constituents, min_combined_weight)}
# min_combined_weight=0.0 → always block; >0 → only block if their combined ETF weight exceeds threshold.
ETF_OVERLAP: dict[str, tuple[list[str], float]] = {
    "GOAU": (["AEM", "WPM", "FNV", "RGLD", "HL", "PAAS"], 0.0),
    "GBUG": (["AEM", "WPM", "FNV", "RGLD", "HL", "PAAS"], 0.0),
    "SGDM": (["AEM", "WPM", "FNV", "HL"], 0.0),
    "SGDJ": (["HL", "PAAS"], 0.0),
    "URNM": (["URA"], 0.0),
    "URNJ": (["URA"], 0.0),
    "COPP": (["COPX"], 0.0),
}

# Annual expense ratios for ETFs competing in thesis groups (used for fee-adjusted comparison)
EXPENSE_RATIOS: dict[str, float] = {
    # Uranium
    "URNM": 0.0075,  # Sprott
    "URNJ": 0.0080,  # Sprott
    "URA":  0.0069,  # Global X
    # Copper
    "COPP": 0.0065,  # Sprott
    "COPX": 0.0065,  # Global X
    # Gold miner ETFs
    "GOAU": 0.0060,  # US Global
    "SGDM": 0.0050,  # Sprott
    "SGDJ": 0.0057,  # Sprott
    "GBUG": 0.0089,  # Sprott Active (John Hathaway team)
    # Ex-US momentum
    "IMOM": 0.0039,  # Alpha Architect
    "IMTM": 0.0030,  # iShares
    # EM factor
    "FRDM": 0.0049,  # Life+Liberty
    "AVES": 0.0036,  # Avantis
    # LatAm
    "ILF":  0.0048,  # iShares
    "FLN":  0.0080,  # First Trust
    "EWZS": 0.0059,  # iShares
    # Intl small value
    "AVDV": 0.0036,  # Avantis
    "DXIV": 0.0023,  # Dimensional
    "DFSV": 0.0022,  # Dimensional
    "AVUV": 0.0025,  # Avantis
}

# Per-ticker maximum allocation overrides (fraction of capital). Caps individual miners
# that can dominate via momentum but represent idiosyncratic risk vs ETF wrappers.
TICKER_MAX_ALLOC: dict[str, float] = {
    "HL":   0.05,
    "PAAS": 0.05,
}

# (max_picks, [competing tickers]) — within each group, only top max_picks by score advance
THESIS_GROUPS: list[tuple[int, list[str]]] = [
    (1, ["URNM", "URNJ", "URA"]),            # Uranium: best one wins
    (1, ["COPP", "COPX"]),                    # Copper miners: best one wins
    (1, ["GOAU", "SGDM", "SGDJ", "GBUG"]),     # Gold miner ETF wrappers: best one wins
    (1, ["IMOM", "IMTM"]),                    # Ex-US momentum: best one wins
    (1, ["FRDM", "AVES"]),                    # EM factor: best one wins
    (1, ["ILF", "FLN", "EWZS"]),             # LatAm equity: best one wins
    (1, ["AVDV", "DXIV", "DFSV", "AVUV"]),  # Intl small value: best one wins
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


@daily_disk_cache
def _fetch_one(ticker: str, period: str) -> pl.DataFrame | None:
    """Fetch total return index for one ticker. Returns None on failure."""
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return None
    tri = _build_total_return(hist["Close"].values, hist["Dividends"].values)
    date_strs = [d.strftime("%Y-%m-%d") for d in hist.index.to_pydatetime()]
    return pl.DataFrame({"date": date_strs, ticker: tri})


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> pl.DataFrame:
    """Fetch total return prices (includes reinvested dividends) as polars DataFrame."""
    frames = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, t, period): t for t in tickers}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                frames.append(result)

    if not frames:
        return pl.DataFrame()

    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, on="date", how="full", coalesce=True)
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

    mom_1m = mom(LOOKBACK_1M)
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

    # Frog-in-the-Pan (FIP): fraction of positive daily returns in 12M-1M window.
    # Alpha Architect: prefers stocks that grind up steadily over those with a few large spikes.
    fip_returns = returns[start_idx:end_idx]
    fip = float(np.mean(fip_returns > 0)) if len(fip_returns) > 0 else 0.5

    # Composite smoothness: geometric mean of trend linearity (R²) and daily consistency (FIP)
    smoothness = (quality * fip) ** 0.5

    # Score (composite: 20% 3M, 40% 6M, 40% 12M, smoothness-adjusted)
    score = (wt_mom * smoothness) / dn_vol if dn_vol > 0 else 0.0

    # 12-1 momentum score (pure 12M skip-1M signal, common academic factor)
    score_12_1 = (mom_12m * smoothness) / dn_vol if dn_vol > 0 else 0.0

    # --- WTMF composite signal (WisdomTree Managed Futures style) ---
    # Binary sign at each horizon: +1 if positive, -1 if negative
    # Composite ranges from -3 (all bearish) to +3 (all bullish)
    # Weight: +3 → full, +1 → 2/3, 0 → zero
    m3_sign = 1.0 if mom_3m > 0 else (-1.0 if mom_3m < 0 else 0.0)
    m6_sign = 1.0 if mom_6m > 0 else (-1.0 if mom_6m < 0 else 0.0)
    m12_sign = 1.0 if mom_12m > 0 else (-1.0 if mom_12m < 0 else 0.0)
    wtmf_composite = m3_sign + m6_sign + m12_sign  # -3 to +3

    # WTMF score: composite signal scaled by momentum magnitude, vol-adjusted
    wtmf_weight = abs(wtmf_composite) / 3.0  # 0, 1/3, 2/3, or 1
    wtmf_mom = wtmf_weight * wt_mom
    score_wtmf = (wtmf_mom * smoothness) / dn_vol if dn_vol > 0 else 0.0

    # --- Baltas-Kosowski trend-fit signal ---
    # Instead of return sign, fit a linear trend to price path and use:
    # 1. Slope (annualized) as the momentum signal
    # 2. t-statistic of slope as the confidence filter
    # This reduces turnover ~2/3 vs simple return sign (Baltas & Kosowski 2013)
    if len(window) >= 20:
        log_w = np.log(window)
        x_w = np.arange(len(log_w))
        # Linear regression: log_price = slope * t + intercept
        slope_bk, intercept_bk = np.polyfit(x_w, log_w, 1)
        # Annualized slope (daily slope * 252)
        baltas_slope = slope_bk * 252
        # t-statistic of slope
        residuals = log_w - (slope_bk * x_w + intercept_bk)
        se_slope = np.sqrt(np.sum(residuals**2) / (len(x_w) - 2)) / np.sqrt(np.sum((x_w - x_w.mean())**2))
        baltas_tstat = slope_bk / se_slope if se_slope > 0 else 0.0
        # Only take position when trend is statistically significant (|t| > 1.5)
        baltas_signal = baltas_slope if abs(baltas_tstat) > 1.5 else 0.0
    else:
        baltas_slope = 0.0
        baltas_tstat = 0.0
        baltas_signal = 0.0

    # Baltas score: trend-fit slope (vol-adjusted), only when significant
    score_baltas = (baltas_signal * quality) / dn_vol if dn_vol > 0 else 0.0

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
        "mom_1m": mom_1m,
        "mom_3m": mom_3m,
        "mom_6m": mom_6m,
        "mom_12m": mom_12m,
        "wt_mom": wt_mom,
        "quality": quality,
        "fip": fip,
        "smoothness": smoothness,
        "dn_vol": dn_vol,
        "score": score,
        "score_12_1": score_12_1,
        "wtmf_composite": wtmf_composite,
        "score_wtmf": score_wtmf,
        "baltas_slope": baltas_slope,
        "baltas_tstat": baltas_tstat,
        "score_baltas": score_baltas,
        "max_dd": max_dd,
        "max_dd_dur": max_dd_dur,
        "avg_dd_dur": avg_dd_dur,
        "current_dd": current_dd,
        "worst_3m_dd": worst_3m_dd,
    }


def build_scores(prices: pl.DataFrame) -> pl.DataFrame:
    """Compute all per-ticker metrics. Returns one row per ticker."""
    tickers = [c for c in prices.columns if c != "date"]
    min_history = LOOKBACK_3M + SKIP_1M  # ~84 trading days (~4 months)
    rows = []
    skipped = []
    for t in tickers:
        p = prices[t].drop_nulls().to_numpy()
        if len(p) < min_history:
            skipped.append(t)
            continue
        r = np.diff(p) / p[:-1]
        rows.append(_score_one(t, p, r))
    if skipped:
        console.print(f"[dim]Skipped (insufficient history <12M): {', '.join(skipped)}[/]")
    return pl.DataFrame(rows)


def apply_thesis_groups(
    scores: pl.DataFrame,
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Pre-filter: within each same-thesis group, keep only top max_picks by fee-adjusted score."""
    excluded: dict[str, str] = {}
    for max_picks, group in THESIS_GROUPS:
        in_group = (
            scores
            .filter(pl.col("ticker").is_in(group) & (pl.col("wt_mom") > 0))
            .with_columns(
                pl.col("ticker")
                .map_elements(lambda t: EXPENSE_RATIOS.get(t, 0.0), return_dtype=pl.Float64)
                .alias("expense_ratio")
            )
            .with_columns(
                (pl.col("score") * (1 - pl.col("expense_ratio"))).alias("fee_adj_score")
            )
            .sort("fee_adj_score", descending=True)
        )
        if len(in_group) <= max_picks:
            continue
        winner = in_group[0]["ticker"].item()
        for row in in_group[max_picks:].iter_rows(named=True):
            fee_pct = row["expense_ratio"] * 100
            excluded[row["ticker"]] = (
                f"same thesis as {winner} "
                f"(score {row['score']:.2f}, fee {fee_pct:.2f}%)"
            )
    return scores.filter(~pl.col("ticker").is_in(list(excluded))), excluded


@daily_disk_cache
def _fetch_etf_weights(etf: str) -> dict[str, float]:
    """Return {ticker: weight} for an ETF's top holdings. Empty dict if unavailable."""
    holdings = yf.Ticker(etf).funds_data.top_holdings
    if holdings is None or len(holdings) == 0:
        return {}
    return dict(zip(holdings.index.tolist(), holdings["Holding Percent"].tolist()))


def apply_etf_overlap(
    alloc: pl.DataFrame,
    scores: pl.DataFrame,
    capital: int,
    min_pct: float,
    max_pct: float,
    max_positions: int = MAX_POSITIONS,
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Post-filter: block constituent tickers whose combined weight across all selected ETFs exceeds threshold."""
    selected = set(alloc["ticker"].to_list())
    universe = set(scores["ticker"].to_list())
    blocked: dict[str, str] = {}

    # Pre-fetch holdings for every selected ETF that has a weight threshold
    etf_holdings: dict[str, dict[str, float]] = {
        etf: _fetch_etf_weights(etf)
        for etf in selected & set(ETF_OVERLAP)
        if ETF_OVERLAP[etf][1] > 0.0
    }

    for etf in selected & set(ETF_OVERLAP):
        constituents, weight_threshold = ETF_OVERLAP[etf]
        in_universe = [t for t in constituents if t in universe]

        if weight_threshold > 0.0:
            # Sum constituent weights across ALL selected ETFs, not just this one
            combined = sum(
                sum(holdings.get(t, 0.0) for t in in_universe)
                for holdings in etf_holdings.values()
            )
            if combined <= weight_threshold:
                continue  # not concentrated enough across the portfolio

        for ticker in in_universe:
            blocked[ticker] = f"held inside {etf}"

    if not blocked:
        return alloc, blocked
    filtered = scores.filter(~pl.col("ticker").is_in(list(blocked)))
    return allocate(filtered, capital, min_pct, max_pct, max_positions), blocked


def allocate(
    scores: pl.DataFrame, capital: int, min_pct: float, max_pct: float,
    max_positions: int = MAX_POSITIONS,
) -> pl.DataFrame:
    """Filter, weight, constrain. Returns allocation DataFrame."""
    # Filter positive momentum
    df = scores.filter(pl.col("wt_mom") > 0)

    if len(df) == 0:
        return pl.DataFrame()

    # Weight by score
    total_score = df["score"].sum()
    df = df.with_columns((pl.col("score") / total_score).alias("weight"))

    # Cap at max_positions
    df = df.sort("score", descending=True).head(max_positions)

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

        # Cap above maximum (global or per-ticker override)
        for t in alloc_dict:
            ticker_max = capital * TICKER_MAX_ALLOC.get(t, max_pct)
            if alloc_dict[t] > ticker_max:
                alloc_dict[t] = ticker_max
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
    """Compact scores: one line per ticker, PASS only."""
    pass_only = scores.filter(pl.col("wt_mom") > 0).sort("score", descending=True)
    lines = []
    for row in pass_only.iter_rows(named=True):
        lines.append(
            f"  {row['ticker']:<7} score={row['score']:.2f}  "
            f"mom={row['wt_mom']*100:+.0f}%  smooth={row['smoothness']:.2f}  dd={row['max_dd']*100:.0f}%"
        )
    print("Scores (PASS):")
    print("\n".join(lines))


def print_allocation_table(alloc: pl.DataFrame, prices: pl.DataFrame, capital: int):
    """Compact allocation: ticker | $ | wt | score."""
    latest_prices = {
        row["ticker"]: prices.select(row["ticker"]).drop_nulls().tail(1).item()
        for row in alloc.iter_rows(named=True)
    }
    print(f"\n{'Ticker':<7} {'$':>7}  {'Wt':>5}  {'Score':>5}  {'Mom':>6}  {'DD':>5}")
    print("-" * 46)
    for row in alloc.sort("alloc_usd", descending=True).iter_rows(named=True):
        t = row["ticker"]
        amt = round_to_nearest(row["alloc_usd"])
        wt = amt / capital * 100
        print(
            f"{t:<7} ${amt:>6,}  {wt:>4.1f}%  {row['score']:>5.2f}  "
            f"{row['wt_mom']*100:>+5.0f}%  {row['max_dd']*100:>4.0f}%"
        )


def print_portfolio_summary(alloc: pl.DataFrame, scores: pl.DataFrame, capital: int):
    """Two-line portfolio summary."""
    weights = alloc.with_columns((pl.col("alloc_usd") / pl.col("alloc_usd").sum()).alias("w"))
    joined = weights.join(scores, on="ticker", how="inner")

    w_mom = (joined["w"] * (0.2*joined["mom_3m"] + 0.4*joined["mom_6m"] + 0.4*joined["mom_12m"])).sum()
    w_smooth = (joined["w"] * joined["smoothness"]).sum()
    w_score = (joined["w"] * joined["score"]).sum()
    w_dn_vol = (joined["w"] * joined["dn_vol"]).sum()
    w_max_dd = (joined["w"] * joined["max_dd"]).sum()
    pain = w_mom / abs(w_max_dd) if w_max_dd != 0 else 0

    cat_parts = []
    for label, group in CATEGORIES:
        amt = alloc.filter(pl.col("ticker").is_in(group))["alloc_usd"].sum()
        if amt > 0:
            cat_parts.append(f"{label} {amt/capital*100:.0f}%")

    print(f"\nscore={w_score:.2f}  smooth={w_smooth:.2f}  mom={w_mom*100:+.0f}%  "
          f"dd={w_max_dd*100:.0f}%  dnvol={w_dn_vol*100:.0f}%  pain={pain:.1f}")
    print("  " + "  ".join(cat_parts))


def print_exclusions(thesis: dict[str, str], overlap: dict[str, str]) -> None:
    """One-line exclusion summary."""
    parts = []
    for t, r in thesis.items():
        winner = r.split("same thesis as ")[1].split(" ")[0]
        parts.append(f"{t}→{winner}")
    thesis_str = "thesis: " + "  ".join(parts) if parts else ""
    overlap_str = "inside-etf: " + "  ".join(f"{t}({r.split('inside ')[1]})" for t, r in overlap.items()) if overlap else ""
    line = "  ".join(x for x in [thesis_str, overlap_str] if x)
    if line:
        print(f"excluded  {line}")


@click.command()
@click.option(
    "--min-allocation",
    "-m",
    type=float,
    default=0.0,
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
@click.option(
    "--max-positions",
    "-n",
    type=int,
    default=MAX_POSITIONS,
    help="Maximum number of positions.",
)
def main(min_allocation: float, max_allocation: float, capital: int, max_positions: int):
    """US Portfolio Allocation - Sortino-weighted Momentum."""
    prices = fetch_total_return_index(TICKERS)
    if prices.is_empty():
        print("No data fetched.")
        return

    print(f"data {prices['date'].min()}→{prices['date'].max()}  capital=${capital:,}  n={max_positions}")

    scores = build_scores(prices)

    scores_clean, thesis_excl = apply_thesis_groups(scores)
    alloc = allocate(scores_clean, capital, min_allocation, max_allocation, max_positions)
    alloc, overlap_excl = apply_etf_overlap(alloc, scores_clean, capital, min_allocation, max_allocation, max_positions)

    if alloc.is_empty():
        print("No positions passed filters.")
        return

    print_exclusions(thesis_excl, overlap_excl)
    print_allocation_table(alloc, prices, capital)
    print_portfolio_summary(alloc, scores, capital)


if __name__ == "__main__":
    main()
