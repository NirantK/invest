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
    # === Leo Aschenbrenner 13F Q4 2025 (additional) ===
    "PSIX",    # Power Solutions - data center backup power
    "BTDR",    # Bitdeer - bitcoin mining / AI hosting
    "CLSK",    # CleanSpark - bitcoin mining
    "BITF",    # Bitfarms - bitcoin mining
    "LBRT",    # Liberty Energy - oilfield services / data center power
    "BWC",     # Babcock & Wilcox - small modular reactors / nuclear
    "PUMP",    # ProPetro - oilfield services
    # === Citrini 2026 watchlist ===
    "ACN",     # Accenture - AI job loss beneficiary
    "IBM",     # IBM - AI job loss beneficiary
    "ZM",      # Zoom - AI job loss beneficiary
    "INTU",    # Intuit - AI job loss beneficiary
    "DG",      # Dollar General - AI job loss beneficiary
    "TGT",     # Target - AI job loss beneficiary
    "UPS",     # UPS - AI job loss beneficiary
    "CMG",     # Chipotle - back-of-house automation
    "CAVA",    # Cava - slop bowl automation
    "SG",      # Sweetgreen - slop bowl automation
    "WVE",     # Wave Life Sciences - GalNAc-siRNA weight loss
    "ARWR",    # Arrowhead - GalNAc-siRNA weight loss
    "ALNY",    # Alnylam - GalNAc-siRNA pioneer
    "RL",      # Ralph Lauren - luxury / Girlfriend Index
    "AS",      # Amer Sports - luxury / Girlfriend Index
    # === Zephyr (@zephyr_z9) ===
    "AMD",     # AMD - semis, "mispriced" call
    "STX",     # Seagate - storage with SNDK
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
def _fetch_one_v2(ticker: str, period: str) -> dict | None:
    """Fetch TRI + close + dollar volume for one ticker. Returns dict of arrays or None."""
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return None
    closes = hist["Close"].values
    vols = hist["Volume"].values
    divs = hist["Dividends"].values
    tri = _build_total_return(closes, divs)
    dvol = closes * vols
    date_strs = [d.strftime("%Y-%m-%d") for d in hist.index.to_pydatetime()]
    return {"date": date_strs, "tri": tri, "close": closes, "dvol": dvol}


def fetch_total_return_index(tickers: list[str], period: str = "3y") -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Fetch (TRI, close, dollar-volume) DataFrames keyed by date, columns by ticker."""
    fetched: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one_v2, t, period): t for t in tickers}
        for future in as_completed(futures):
            t = futures[future]
            result = future.result()
            if result is not None:
                fetched[t] = result

    if not fetched:
        empty = pl.DataFrame()
        return empty, empty, empty

    def _to_df(field: str) -> pl.DataFrame:
        frames = [pl.DataFrame({"date": v["date"], t: v[field]}) for t, v in fetched.items()]
        out = frames[0]
        for f in frames[1:]:
            out = out.join(f, on="date", how="full", coalesce=True)
        return out.sort("date")

    return _to_df("tri"), _to_df("close"), _to_df("dvol")


def _score_one(ticker: str, prices: np.ndarray, returns: np.ndarray,
               closes: np.ndarray | None = None, dvols: np.ndarray | None = None) -> dict:
    """Compute all metrics for one ticker in numpy. Returns dict for polars row.

    closes: raw close prices (for 52WH distance)
    dvols: dollar volumes (close × volume) for ADV + dvol slope
    """
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

    # Ulcer Index (1Y): sqrt(mean(DD²)) over last 252 trading days
    # Recompute DD against rolling 1Y peak so 2022 wipeouts don't pollute current regime
    if n >= LOOKBACK_12M:
        last_year = prices[-LOOKBACK_12M:]
        running_max_1y = np.maximum.accumulate(last_year)
        dd_1y = (last_year - running_max_1y) / running_max_1y
        ulcer_1y = float(np.sqrt(np.mean(dd_1y ** 2)))
        max_dd_1y = float(dd_1y.min())
    else:
        # Fall back to all-history if <1Y data
        ulcer_1y = float(np.sqrt(np.mean(drawdown ** 2)))
        max_dd_1y = float(max_dd)

    # Martin Ratio: weighted-mom / ulcer_1y. Higher = more return per unit of pain.
    martin = (wt_mom / ulcer_1y) if ulcer_1y > 0.001 else 0.0

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

    # === Volume + price-level signals ===
    # 1. 52-week-high distance: how close to recent peak (closer = stronger trend)
    #    dist52 = 0 means at high; 0.25 = 25% below. Penalty if > 0.25.
    if closes is not None and len(closes) >= LOOKBACK_12M:
        max_252 = float(np.nanmax(closes[-LOOKBACK_12M:]))
        last_close = float(closes[-1])
        dist52 = 1.0 - (last_close / max_252) if max_252 > 0 else 1.0
    else:
        dist52 = float("nan")

    # 2. Dollar-volume slope (3M): is money flow growing or shrinking?
    #    Positive slope on log(dvol) = accumulation; negative = distribution
    if dvols is not None and len(dvols) >= LOOKBACK_3M:
        dv_window = dvols[-LOOKBACK_3M:]
        dv_window = dv_window[np.isfinite(dv_window) & (dv_window > 0)]
        if len(dv_window) >= 30:
            log_dv = np.log(dv_window)
            x_dv = np.arange(len(log_dv))
            dv_slope = float(np.polyfit(x_dv, log_dv, 1)[0]) * 252  # annualized
        else:
            dv_slope = 0.0
    else:
        dv_slope = 0.0

    # 3. Average Daily Dollar Volume (60d) — liquidity gate
    if dvols is not None and len(dvols) >= 60:
        adv60 = float(np.nanmean(dvols[-60:]))
    else:
        adv60 = 0.0

    # Volume confirmation factor: rewards growing money flow, mildly penalizes shrinking
    # dv_slope ranges roughly -2 to +2 (annualized log-growth). Map to [0.7, 1.3].
    vol_factor = float(np.clip(1.0 + 0.15 * dv_slope, 0.7, 1.3))

    # 52WH boost: reward proximity to peak (Minervini/O'Neil style)
    # dist52 < 0.10: ×1.10; 0.10–0.25: ×1.00; > 0.25: linear penalty down to 0.85
    if not np.isnan(dist52):
        if dist52 < 0.10:
            high_factor = 1.10
        elif dist52 < 0.25:
            high_factor = 1.00
        else:
            high_factor = max(0.85, 1.00 - 0.50 * (dist52 - 0.25))
    else:
        high_factor = 1.00

    # Legacy Sortino-style score (kept for diagnostics + backtest comparison)
    score_sortino = score * vol_factor * high_factor

    # New: Martin-anchored score (returns per unit of pain, with quality multipliers)
    score_martin = martin * smoothness * vol_factor * high_factor

    # Default reported score: Martin (user pivoted from Sharpe to Ulcer/Martin)
    score_v2 = score_martin

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
        "score": score_v2,
        "score_sortino": score_sortino,  # legacy Sortino-style for backtest A/B
        "score_martin": score_martin,    # Martin-anchored (currently default)
        "score_pricemom": score,         # raw Sortino without volume/level boosts
        "ulcer_1y": ulcer_1y,
        "max_dd_1y": max_dd_1y,
        "martin": martin,
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
        "dist52": dist52,
        "dv_slope": dv_slope,
        "adv60": adv60,
        "vol_factor": vol_factor,
        "high_factor": high_factor,
    }


def add_rank_scores(scores: pl.DataFrame) -> pl.DataFrame:
    """Add cross-sectional rank-based composite score.

    Each signal converted to percentile rank (0..1), then averaged.
    Lower-is-better signals (ulcer_1y, dist52) inverted before ranking.
    Result column: score_rank in [0, 1].
    """
    pos = scores.filter(pl.col("wt_mom") > 0)
    if pos.is_empty():
        return scores.with_columns(pl.lit(0.0).alias("score_rank"))

    n = len(pos)

    def _pct_rank(col: str, descending: bool = True) -> pl.Expr:
        # Higher value = higher rank (1.0 = best). For lower-is-better, pass descending=False.
        return (pl.col(col).rank(method="average", descending=not descending) - 1) / max(n - 1, 1)

    ranked = pos.with_columns([
        _pct_rank("wt_mom").alias("r_mom"),
        _pct_rank("smoothness").alias("r_smooth"),
        _pct_rank("ulcer_1y", descending=False).alias("r_ulcer"),  # lower ulcer → higher rank
        _pct_rank("dv_slope").alias("r_dvol"),
        _pct_rank("dist52", descending=False).alias("r_d52"),       # closer to high → higher rank
    ])
    # Composite: mean of 5 percentile ranks (range 0..1)
    ranked = ranked.with_columns(
        ((pl.col("r_mom") + pl.col("r_smooth") + pl.col("r_ulcer")
          + pl.col("r_dvol") + pl.col("r_d52")) / 5.0).alias("score_rank")
    )

    # Join back; non-passing tickers get score_rank=0
    keep_cols = ["ticker", "score_rank", "r_mom", "r_smooth", "r_ulcer", "r_dvol", "r_d52"]
    return scores.join(ranked.select(keep_cols), on="ticker", how="left").with_columns(
        pl.col("score_rank").fill_null(0.0)
    )


def build_scores(prices: pl.DataFrame, closes: pl.DataFrame | None = None,
                 dvols: pl.DataFrame | None = None) -> pl.DataFrame:
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
        c_arr = closes[t].drop_nulls().to_numpy() if closes is not None and t in closes.columns else None
        dv_arr = dvols[t].drop_nulls().to_numpy() if dvols is not None and t in dvols.columns else None
        rows.append(_score_one(t, p, r, c_arr, dv_arr))
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


def _water_fill(scores: dict[str, float], caps: dict[str, float], capital: float) -> dict[str, float]:
    """Pour capital into tickers proportional to score. Pin at cap when hit; redistribute remainder
    to uncapped names by score. Continue until capital exhausted or all names capped.
    """
    pinned = {}
    active = dict(scores)
    remaining = float(capital)

    while active and remaining > 0.01:
        total_score = sum(active.values())
        if total_score <= 0:
            break

        # Find tightest binding cap: which ticker would hit cap first?
        # For each active ticker, fraction_to_pour = score/total_score
        # Capacity to absorb before hitting cap = caps[t] / fraction_to_pour
        binding = min((caps[t] * total_score / s for t, s in active.items() if s > 0),
                      default=remaining)
        pour = min(remaining, binding)
        for t, s in list(active.items()):
            add = (s / total_score) * pour
            allocated = pinned.get(t, 0) + add
            if allocated >= caps[t] - 0.01:
                pinned[t] = caps[t]
                del active[t]
            else:
                pinned[t] = allocated
        remaining -= pour

    return pinned


def allocate(
    scores: pl.DataFrame, capital: int, min_pct: float, max_pct: float,
    max_positions: int = MAX_POSITIONS,
) -> pl.DataFrame:
    """Filter, weight, constrain. Returns allocation DataFrame.

    Algorithm: water-filling by score, capped at max_pct (or per-ticker override).
    Names below min_pct are dropped at the end and their share redistributed
    pro-rata to remaining uncapped names (cascading until stable).
    """
    # Filter positive momentum, cap at max_positions by score
    df = scores.filter(pl.col("wt_mom") > 0).sort("score", descending=True).head(max_positions)

    if len(df) == 0:
        return pl.DataFrame()

    df = df.with_columns(
        (pl.col("score") / df["score"].sum()).alias("weight")
    )

    min_amount = capital * min_pct
    scores_dict = {row["ticker"]: row["score"] for row in df.iter_rows(named=True)}
    caps = {t: capital * TICKER_MAX_ALLOC.get(t, max_pct) for t in scores_dict}

    alloc_dict = _water_fill(scores_dict, caps, capital)

    # Drop below-min names; redistribute via water-fill on the trimmed set.
    # Cascade: dropping may free capital that pushes others over min, which may push others below max.
    for _ in range(50):
        below_min = [t for t, v in alloc_dict.items() if 0 < v < min_amount]
        if not below_min:
            break
        for t in below_min:
            del scores_dict[t]
            del caps[t]
        if not scores_dict:
            alloc_dict = {}
            break
        alloc_dict = _water_fill(scores_dict, caps, capital)

    # Rebuild DataFrame
    rows = [{"ticker": t, "alloc_usd": alloc_dict[t]} for t in alloc_dict if alloc_dict[t] > 0]
    if not rows:
        return pl.DataFrame()
    alloc_df = pl.DataFrame(rows)

    # Join back with scores
    return df.join(alloc_df, on="ticker", how="inner")


def round_to_nearest(value: float, multiple: int = 1000) -> int:
    """Round to nearest multiple (default $1000, fallback to $100 for small amounts)."""
    if value < 500:
        return round(value / 100) * 100
    return round(value / multiple) * multiple


def print_scores_table(scores: pl.DataFrame):
    """Compact scores: one line per ticker, PASS only. Shows Martin + Ulcer."""
    pass_only = scores.filter(pl.col("wt_mom") > 0).sort("score", descending=True)
    lines = []
    for row in pass_only.iter_rows(named=True):
        d52 = row.get("dist52", float("nan"))
        d52_s = f"{d52*100:>3.0f}%" if d52 == d52 else "  - "
        dvs = row.get("dv_slope", 0.0)
        adv = row.get("adv60", 0.0)
        ulcer = row.get("ulcer_1y", 0.0)
        martin = row.get("martin", 0.0)
        cur_dd = row.get("current_dd", 0.0)
        lines.append(
            f"  {row['ticker']:<7} S={row['score']:>5.2f}  "
            f"M={martin:>5.2f}  Ulc={ulcer*100:>4.0f}%  "
            f"mom={row['wt_mom']*100:+.0f}%  cur={cur_dd*100:>4.0f}%  "
            f"d52={d52_s}  dv={dvs:+.2f}  adv=${adv/1e6:.0f}M"
        )
    print("Scores (PASS) — S=score, M=Martin, Ulc=Ulcer1Y, cur=current_dd:")
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
@click.option(
    "--min-adv",
    type=float,
    default=5_000_000.0,
    help="Minimum 60-day average daily dollar volume (liquidity gate). Default $5M.",
)
def main(min_allocation: float, max_allocation: float, capital: int, max_positions: int, min_adv: float):
    """US Portfolio Allocation - Sortino-weighted Momentum + Volume."""
    prices, closes, dvols = fetch_total_return_index(TICKERS)
    if prices.is_empty():
        print("No data fetched.")
        return

    print(f"data {prices['date'].min()}→{prices['date'].max()}  capital=${capital:,}  n={max_positions}  min_adv=${min_adv/1e6:.1f}M")

    scores = build_scores(prices, closes, dvols)

    # Liquidity gate: drop names below ADV threshold
    illiquid = scores.filter(pl.col("adv60") < min_adv)["ticker"].to_list()
    if illiquid:
        scores = scores.filter(pl.col("adv60") >= min_adv)
        print(f"[dim]ADV filter (<${min_adv/1e6:.1f}M): dropped {', '.join(illiquid)}[/]")

    # In-pain filter: don't enter names already in -25%+ drawdown
    in_pain = scores.filter(pl.col("current_dd") < -0.25)["ticker"].to_list()
    if in_pain:
        scores = scores.filter(pl.col("current_dd") >= -0.25)
        print(f"[dim]In-pain filter (current_dd <-25%): dropped {', '.join(in_pain)}[/]")

    scores_clean, thesis_excl = apply_thesis_groups(scores)
    print_scores_table(scores_clean)
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
