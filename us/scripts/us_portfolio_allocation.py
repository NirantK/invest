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

from invest.momentum import score_one, LOOKBACK_3M, SKIP_1M
from invest.allocate import (
    allocate as _shared_allocate,
    add_rank_scores as _shared_add_rank_scores,
    apply_thesis_groups as _shared_apply_thesis_groups,
    apply_sleeve_caps as _shared_apply_sleeve_caps,
    apply_etf_overlap as _shared_apply_etf_overlap,
)

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
    # === Biotech winners (high DD, high Martin in 1Y window) ===
    "IONS",    # Ionis - siRNA leader, GalNAc partner
    "NTLA",    # Intellia - CRISPR, big DD survivor
    "MRNA",    # Moderna - mRNA platform, AI-discovery thesis
    # === AI hardware / data center hyperscale ===
    "SMCI",    # Super Micro - AI server hardware
    "DELL",    # Dell - AI server demand
    "VRT",     # Vertiv - data center cooling/power
    # === AI Power (nuclear + gas for data centers) ===
    "TLN",     # Talen Energy - nuclear, AWS deal
    "VST",     # Vistra - nuclear/gas, AI power thesis
    "CEG",     # Constellation Energy - nuclear, MSFT deal
    "OKLO",    # Oklo - SMR nuclear, Sam Altman backed
    # === Defense / Space momentum ===
    "RKLB",    # Rocket Lab - defense + space
    # === AI Apps / GovTech ===
    "PLTR",    # Palantir - AI + government
    # === Mega-cap AI semiconductors (Phase 2 universe expansion) ===
    "NVDA",    # NVIDIA - the index of AI momentum
    "AVGO",    # Broadcom - networking, custom silicon for hyperscalers
    "MU",      # Micron - memory (HBM) — pair-trade with SNDK
    "ANET",    # Arista - AI/data-center networking
    "MRVL",    # Marvell - custom silicon, optical DSPs
    "CRDO",    # Credo - AI connectivity (small-cap rocket)
    "ALAB",    # Astera Labs - AI connectivity (post-IPO 2024)
    "AMAT",    # Applied Materials - semi cap eq
    "LRCX",    # Lam Research - semi cap eq
    "KLAC",    # KLA - semi metrology
    "TEM",     # Tempus AI - healthcare AI (post-IPO)
    "POWL",    # Powell Industries - electrical infra for AI power
    "GEV",     # GE Vernova - grid + nuclear, AI power buildout
    # === Mega-cap miners (US-listed primary producers) ===
    "NEM",     # Newmont - largest gold producer
    "GOLD",    # Barrick - global gold major
    "KGC",     # Kinross Gold
    "AU",      # AngloGold Ashanti
    "AG",      # First Majestic Silver
    "CDE",     # Coeur Mining - silver/gold US producer
    # "MAG",   # MAG Silver — yfinance 404, dropped

    # === Industrial metals additions ===
    "FCX",     # Freeport-McMoRan - copper/gold (user holds)
    "SCCO",    # Southern Copper (user holds)
    "TECK",    # Teck Resources - diversified Canadian miner
    "ALB",     # Albemarle - lithium
    "SQM",     # SQM Sociedad - lithium + iodine
    # === Sector ETFs added (incl. ones the user holds) ===
    "SMH",     # VanEck Semis ETF (user holds)
    "VNQ",     # Vanguard Real Estate (user holds)
    "EWY",     # iShares MSCI Korea (user holds)
    "GDX",     # VanEck Gold Miners (large-cap)
    "SIL",     # Global X Silver Miners
    "LIT",     # Global X Lithium & Battery Tech
    "REMX",    # VanEck Rare Earth/Strategic Metals
    "PICK",    # iShares MSCI Global Metals & Mining (broad)
    "FCG",     # First Trust Natural Gas - gas E&P
    "AIQ",     # Global X AI & Tech ETF
    # === Regime gate / benchmark (not for allocation; used only for SPY 50/200 DMA) ===
    "SPY",
]

# Tickers in TICKERS purely for regime/benchmark use (NOT eligible for allocation)
BENCHMARK_TICKERS = {"SPY"}

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
SILVER_MINERS  = ["PAAS", "HL", "AG", "CDE"]                   # Primary silver miners
GOLD_MINERS    = ["AEM", "GMIN.TO", "BTG", "NEM", "GOLD", "KGC", "AU"]          # Individual gold producers
GOLD_ETFs      = ["GOAU", "SGDM", "SGDJ", "GBUG", "GDXJ", "GDX"] # Gold/silver miner ETF wrappers
SILVER_ETFs    = ["SILJ", "SIL"]                          # Silver miner ETFs
PRECIOUS_METALS = GOLD_STREAMERS + SILVER_MINERS + GOLD_MINERS + GOLD_ETFs + SILVER_ETFs
INDUSTRIAL_METALS = ["COPX", "COPP", "ARG.TO", "SETM", "FCX", "SCCO", "TECK", "ALB", "SQM", "LIT", "REMX", "PICK"]
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
    "SMCI", "DELL", "VRT", "STX", "AMD", "PLTR",
    "NVDA", "AVGO", "MU", "ANET", "MRVL", "CRDO", "ALAB",
    "AMAT", "LRCX", "KLAC", "TEM", "SMH", "AIQ",
]
AI_POWER = ["TLN", "VST", "CEG", "OKLO", "GEV", "POWL"]  # Nuclear/gas data center power + grid
BIOTECH = ["ARWR", "IONS", "NTLA", "MRNA", "WVE", "ALNY"]
CRYPTO_AI = ["CIFR", "IREN", "HUT", "APLD", "BTDR", "CLSK", "BITF", "RIOT", "CORZ"]  # overlaps AI_INFRA intentionally
DEFENSE = ["RKLB"]
AGRICULTURE = ["DBA", "CF", "IPI", "MOO"]

# Sleeve caps for diversification discipline. Applied AFTER allocate(), demoting lowest-score
# names in over-cap sleeves until under threshold.
SLEEVE_CAPS: list[tuple[str, list[str], float]] = [
    ("AI Infra",      AI_INFRA, 0.40),
    ("AI Power",      AI_POWER, 0.20),
    ("Biotech",       BIOTECH, 0.15),
    ("Crypto-AI",     CRYPTO_AI, 0.15),
    ("Energy",        ENERGY, 0.15),
    ("Real Assets",   GOLD_STREAMERS + SILVER_MINERS + GOLD_MINERS + GOLD_ETFs + SILVER_ETFs + INDUSTRIAL_METALS + URANIUM + PLATINUM, 0.20),
    ("Defensive",     FACTOR_US + FACTOR_INTL + FACTOR_EM, 0.15),
]

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
    ("AI Power", AI_POWER),
    ("Biotech", BIOTECH),
    ("Defense/Space", DEFENSE),
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


def add_rank_scores(scores: pl.DataFrame) -> pl.DataFrame:
    """Cross-sectional rank composite. Delegates to shared lib."""
    return _shared_add_rank_scores(scores)


def build_scores(prices: pl.DataFrame, closes: pl.DataFrame | None = None,
                 dvols: pl.DataFrame | None = None) -> pl.DataFrame:
    """Compute all per-ticker metrics via shared score_one. Returns one row per ticker."""
    tickers = [c for c in prices.columns if c != "date"]
    min_history = LOOKBACK_3M + SKIP_1M
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
        result = score_one(t, p, r, c_arr, dv_arr)
        if result is not None:
            rows.append(result)
    if skipped:
        console.print(f"[dim]Skipped (insufficient history <12M): {', '.join(skipped)}[/]")
    return pl.DataFrame(rows) if rows else pl.DataFrame()


@daily_disk_cache
def _fetch_etf_weights(etf: str) -> dict[str, float]:
    """Return {ticker: weight} for an ETF's top holdings. Empty dict if unavailable."""
    holdings = yf.Ticker(etf).funds_data.top_holdings
    if holdings is None or len(holdings) == 0:
        return {}
    return dict(zip(holdings.index.tolist(), holdings["Holding Percent"].tolist()))


def apply_thesis_groups(scores: pl.DataFrame, score_col: str = "score") -> tuple[pl.DataFrame, dict[str, str]]:
    """Platform wrapper: passes US THESIS_GROUPS + EXPENSE_RATIOS to shared engine."""
    return _shared_apply_thesis_groups(scores, THESIS_GROUPS, EXPENSE_RATIOS, score_col=score_col)


def apply_sleeve_caps(
    alloc: pl.DataFrame, scores: pl.DataFrame, capital: int,
    min_pct: float, max_pct: float, max_positions: int,
    score_col: str, sizing: str,
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Platform wrapper: passes US SLEEVE_CAPS to shared engine."""
    return _shared_apply_sleeve_caps(
        alloc, scores, capital, min_pct, max_pct, max_positions,
        SLEEVE_CAPS, score_col=score_col, sizing=sizing,
        ticker_max_alloc=TICKER_MAX_ALLOC,
    )


def apply_etf_overlap(
    alloc: pl.DataFrame, scores: pl.DataFrame, capital: int,
    min_pct: float, max_pct: float, max_positions: int = MAX_POSITIONS,
    score_col: str = "score", sizing: str = "raw",
) -> tuple[pl.DataFrame, dict[str, str]]:
    """Platform wrapper: passes US ETF_OVERLAP + holdings provider to shared engine."""
    return _shared_apply_etf_overlap(
        alloc, scores, capital, min_pct, max_pct, max_positions,
        ETF_OVERLAP, holdings_provider=_fetch_etf_weights,
        score_col=score_col, sizing=sizing,
        ticker_max_alloc=TICKER_MAX_ALLOC,
    )


def allocate(
    scores: pl.DataFrame, capital: int, min_pct: float, max_pct: float,
    max_positions: int = MAX_POSITIONS,
    score_col: str = "score", sizing: str = "raw",
) -> pl.DataFrame:
    """Platform wrapper: passes US TICKER_MAX_ALLOC to shared engine."""
    return _shared_allocate(
        scores, capital, min_pct, max_pct, max_positions,
        score_col=score_col, sizing=sizing,
        ticker_max_alloc=TICKER_MAX_ALLOC,
    )


SIZING_MODES = {"raw", "sqrt", "equal"}


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
@click.option(
    "--score-col",
    type=click.Choice(["score", "score_martin", "score_sortino", "score_rank"]),
    default="score",
    help="Which score column to rank/select on.",
)
@click.option(
    "--sizing",
    type=click.Choice(["raw", "sqrt", "equal"]),
    default="raw",
    help="Position sizing mode: raw=score-weighted, sqrt=compressed, equal=1/N.",
)
def main(min_allocation: float, max_allocation: float, capital: int, max_positions: int,
         min_adv: float, score_col: str, sizing: str):
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
    scores_clean = add_rank_scores(scores_clean)
    print_scores_table(scores_clean)
    print(f"\n[score_col={score_col}, sizing={sizing}]")
    alloc = allocate(scores_clean, capital, min_allocation, max_allocation, max_positions,
                     score_col=score_col, sizing=sizing)
    alloc, overlap_excl = apply_etf_overlap(alloc, scores_clean, capital, min_allocation,
                                             max_allocation, max_positions,
                                             score_col=score_col, sizing=sizing)
    alloc, sleeve_excl = apply_sleeve_caps(alloc, scores_clean, capital, min_allocation,
                                            max_allocation, max_positions, score_col, sizing)
    if sleeve_excl:
        print(f"[dim]Sleeve caps: " + ", ".join(f"{t}({r})" for t, r in sleeve_excl.items()) + "[/]")

    if alloc.is_empty():
        print("No positions passed filters.")
        return

    print_exclusions(thesis_excl, overlap_excl)
    print_allocation_table(alloc, prices, capital)
    print_portfolio_summary(alloc, scores, capital)


if __name__ == "__main__":
    main()
