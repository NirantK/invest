"""
Indian ETF/Stock data fetcher using dual sources:
  1. yfinance (.NS suffix) — market prices, volume, adjusted close
  2. mfapi.in — NAV data, survivorship-bias-free (retains defunct/merged schemes)

Survivorship bias mitigation:
  mfapi.in sources from AMFI (regulatory). Retains data for merged/defunct schemes.
  For ETFs with scheme chains (Benchmark → Goldman Sachs → Nippon), we stitch
  NAV histories together to get the full timeline without gaps.

  Example: Gold BeES has 3 scheme codes spanning 2007-present:
    105085 (Benchmark, 2007-2011) → 115744 (Goldman Sachs, 2011-2016) → 140088 (Nippon, 2016-present)
"""

import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from enum import Enum
from functools import wraps
from pathlib import Path

import httpx
import numpy as np
import polars as pl

CACHE_DIR = Path(__file__).parent.parent / "data" / "etf_cache"
MFAPI_BASE = "https://api.mfapi.in/mf"

SKIP_1M = 21
LOOKBACK_3M = 63
LOOKBACK_6M = 126
LOOKBACK_12M = 252


class DataSource(Enum):
    YFINANCE = "yfinance"
    MFAPI = "mfapi"


# ---------------------------------------------------------------------------
# Universe definition
# (display_name, yfinance_ticker, mfapi_scheme_codes (chain), category)
# mfapi_scheme_codes: list of codes in chronological order for stitching
# ---------------------------------------------------------------------------

INDIA_UNIVERSE: dict[str, tuple[str, str | None, list[int], str]] = {
    # === International ETFs ===
    "MAFANG":      ("Mirae NYSE FANG+ ETF",       "MAFANG.NS",      [148927],                   "Intl"),
    "MON100":      ("Motilal NASDAQ 100 ETF",      "MON100.NS",      [114984],                   "Intl"),
    "MASPTOP50":   ("Motilal S&P 500 Top 50",      "MASPTOP50.NS",   [],                         "Intl"),
    "HNGSNGBEES":  ("Hang Seng BeES",              "HNGSNGBEES.NS",  [],                         "Intl"),
    # === Commodity: Gold ===
    "GOLDBEES":    ("Nippon Gold BeES",             "GOLDBEES.NS",    [105085, 115744, 140088],   "Gold"),
    "SETFGOLD":    ("SBI Gold ETF",                 "SETFGOLD.NS",    [],                         "Gold"),
    # === Commodity: Silver ===
    "SILVERBEES":  ("Nippon Silver ETF",            "SILVERBEES.NS",  [149758],                   "Silver"),
    # === Commodity: Basket ===
    "COMMOIETF":   ("Nippon Commodity ETF",         "COMMOIETF.NS",   [],                         "Commodity"),
    # === Factor: Momentum ===
    "MOM100":      ("Motilal Momentum 100",         "MOM100.NS",      [],                         "Factor:Mom"),
    "MOM50":       ("Nifty 500 Momentum 50",        "MOM50.NS",       [],                         "Factor:Mom"),
    "MOMENTUM":    ("Momentum ETF",                 "MOMENTUM.NS",    [],                         "Factor:Mom"),
    "MOMOMENTUM":  ("Motilal Momentum ETF",         "MOMOMENTUM.NS",  [],                         "Factor:Mom"),
    # === Factor: Alpha ===
    "ALPHAETF":    ("Nippon Alpha ETF",             "ALPHAETF.NS",    [],                         "Factor:Alpha"),
    "ALPHA":       ("Alpha ETF",                    "ALPHA.NS",       [],                         "Factor:Alpha"),
    # === Factor: Value ===
    "MOVALUE":     ("Motilal Value ETF",            "MOVALUE.NS",     [],                         "Factor:Value"),
    "NV20IETF":    ("ICICI Nifty Value 20",         "NV20IETF.NS",    [],                         "Factor:Value"),
    "NV20BEES":    ("Nippon Value 20 BeES",         "NV20BEES.NS",    [],                         "Factor:Value"),
    # === Factor: Quality ===
    "QUAL30IETF":  ("ICICI Quality 30",             "QUAL30IETF.NS",  [],                         "Factor:Quality"),
    "SBIETFQLTY":  ("SBI Quality ETF",              "SBIETFQLTY.NS",  [],                         "Factor:Quality"),
    "MONQ50":      ("Motilal Quality 50",           "MONQ50.NS",      [],                         "Factor:Quality"),
    "MIDQ50ADD":   ("Motilal Midcap Quality 50",    "MIDQ50ADD.NS",   [],                         "Factor:Quality"),
    # === Factor: Low Volatility ===
    "LOWVOLIETF":  ("ICICI Low Vol 30",             "LOWVOLIETF.NS",  [],                         "Factor:LowVol"),
    # === Factor: Equal Weight ===
    "EQUAL50ADD":  ("Motilal Equal Weight 50",      "EQUAL50ADD.NS",  [],                         "Factor:EqWt"),
    # === Broad Market: Nifty 50 ===
    "NIFTYBEES":   ("Nippon Nifty 50 BeES",         "NIFTYBEES.NS",   [101325, 115728, 140084],   "Nifty50"),
    # === Broad Market: Nifty Next 50 ===
    "JUNIORBEES":  ("Nifty Next 50 BeES",           "JUNIORBEES.NS",  [101621, 115729, 140085],   "NiftyNext50"),
    # === Broad Market: Nifty 100 ===
    "NIF100BEES":  ("Nippon Nifty 100 BeES",        "NIF100BEES.NS",  [121146],                   "Nifty100"),
    "NIF100IETF":  ("ICICI Nifty 100",              "NIF100IETF.NS",  [],                         "Nifty100"),
    # === Broad Market: Nifty 500 ===
    "MONIFTY500":  ("Motilal Nifty 500",            "MONIFTY500.NS",  [],                         "Nifty500"),
    # === Broad Market: Midcap ===
    "MIDCAP":      ("Motilal Midcap 100",           "MIDCAP.NS",      [],                         "Midcap"),
    "MIDCAPIETF":  ("ICICI Midcap 150",             "MIDCAPIETF.NS",  [],                         "Midcap"),
    # === Broad Market: Smallcap ===
    "SMALLCAP":    ("Motilal Smallcap ETF",         "SMALLCAP.NS",    [],                         "Smallcap"),
    "MOSMALL250":  ("Motilal Smallcap 250",         "MOSMALL250.NS",  [],                         "Smallcap"),
    # === Sector: Banking ===
    "BANKBEES":    ("Bank Nifty BeES",              "BANKBEES.NS",    [101296, 115731, 140087],   "Sector:Bank"),
    "PSUBNKBEES":  ("PSU Bank BeES",                "PSUBNKBEES.NS",  [106858, 115747, 140089],   "Sector:PSUBank"),
    # === Sector: IT ===
    "ITBEES":      ("IT Sector BeES",               "ITBEES.NS",      [],                         "Sector:IT"),
    # === Sector: Pharma / Health ===
    "PHARMABEES":  ("Pharma BeES",                  "PHARMABEES.NS",  [],                         "Sector:Pharma"),
    "MOHEALTH":    ("Motilal Healthcare",           "MOHEALTH.NS",    [],                         "Sector:Health"),
    # === Sector: Infra ===
    "INFRABEES":   ("Infra BeES",                   "INFRABEES.NS",   [113287, 115755, 140102],   "Sector:Infra"),
    # === Sector: PSU ===
    "CPSEETF":     ("CPSE ETF (PSU basket)",        "CPSEETF.NS",     [],                         "Sector:PSU"),
    # === Sector: Consumption / FMCG ===
    "CONSUMBEES":  ("Consumption BeES",             "CONSUMBEES.NS",  [],                         "Sector:Consumption"),
    "FMCGIETF":    ("ICICI FMCG ETF",              "FMCGIETF.NS",    [],                         "Sector:FMCG"),
    # === Sector: Auto ===
    "AUTOBEES":    ("Auto Sector BeES",             "AUTOBEES.NS",    [],                         "Sector:Auto"),
    # === Sector: Defence / Make in India ===
    "MODEFENCE":   ("Motilal Defence ETF",          "MODEFENCE.NS",   [],                         "Sector:Defence"),
    "MAKEINDIA":   ("Make in India ETF",            "MAKEINDIA.NS",   [],                         "Sector:MakeInIndia"),
    # === Sector: Realty ===
    "MOREALTY":    ("Motilal Realty ETF",            "MOREALTY.NS",    [],                         "Sector:Realty"),
    # === Sector: Shariah ===
    "SHARIABEES":  ("Shariah BeES",                 "SHARIABEES.NS",  [111832, 115750, 140094],   "Sector:Shariah"),
    # === Debt / Bond ETFs ===
    "LIQUIDBEES":  ("Liquid BeES",                  "LIQUIDBEES.NS",  [101884, 115730, 140086],   "Debt:Liquid"),
    "SETF10GILT":  ("SBI 10Y Gilt ETF",             "SETF10GILT.NS",  [],                         "Debt:Gilt"),
    "MOGSEC":      ("Motilal G-Sec ETF",            "MOGSEC.NS",      [],                         "Debt:GSec"),
    "EBBETF0430":  ("Bharat Bond Apr 2030",         "EBBETF0430.NS",  [],                         "Debt:BharatBond"),
    "EBBETF0431":  ("Bharat Bond Apr 2031",         "EBBETF0431.NS",  [],                         "Debt:BharatBond"),
    "EBBETF0433":  ("Bharat Bond Apr 2033",         "EBBETF0433.NS",  [],                         "Debt:BharatBond"),
    # === REITs & InvITs ===
    "EMBASSY":     ("Embassy Office Parks REIT",    "EMBASSY.NS",     [],                         "REIT"),
    "MINDSPACE":   ("Mindspace Business Parks REIT","MINDSPACE.NS",   [],                         "REIT"),
    "IRFC":        ("Indian Railway Finance Corp",  "IRFC.NS",        [],                         "InvIT"),
    "POWERGRID":   ("Power Grid InvIT",             "POWERGRID.NS",   [],                         "InvIT"),
    # === Large-Cap Singles ===
    "RELIANCE":    ("Reliance Industries",          "RELIANCE.NS",    [],                         "LargeCap"),
    "TCS":         ("TCS",                          "TCS.NS",         [],                         "LargeCap"),
    "INFY":        ("Infosys",                      "INFY.NS",        [],                         "LargeCap"),
    "HDFCBANK":    ("HDFC Bank",                    "HDFCBANK.NS",    [],                         "LargeCap"),
    "ICICIBANK":   ("ICICI Bank",                   "ICICIBANK.NS",   [],                         "LargeCap"),
    "BHARTIARTL":  ("Bharti Airtel",                "BHARTIARTL.NS",  [],                         "LargeCap"),
    "LT":          ("L&T",                          "LT.NS",          [],                         "LargeCap"),
    "SBIN":        ("SBI",                          "SBIN.NS",        [],                         "LargeCap"),
    "ITC":         ("ITC",                          "ITC.NS",         [],                         "LargeCap"),
    "ADANIENT":    ("Adani Enterprises",            "ADANIENT.NS",    [],                         "LargeCap"),
    "ADANIPORTS":  ("Adani Ports",                  "ADANIPORTS.NS",  [],                         "LargeCap"),
    "BAJFINANCE":  ("Bajaj Finance",                "BAJFINANCE.NS",  [],                         "LargeCap"),
    "WIPRO":       ("Wipro",                        "WIPRO.NS",       [],                         "LargeCap"),
    "HCLTECH":     ("HCL Tech",                     "HCLTECH.NS",     [],                         "LargeCap"),
}


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

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

        for f in CACHE_DIR.glob(f"{func.__name__}__*.pkl"):
            if not f.name.endswith(f"__{today}.pkl"):
                f.unlink(missing_ok=True)

        return result

    return wrapper


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

@daily_disk_cache
def fetch_yfinance(ticker: str, period: str = "5y") -> pl.DataFrame | None:
    """Fetch market price data from yfinance."""
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return None

    return pl.DataFrame(
        {
            "date": [d.strftime("%Y-%m-%d") for d in hist.index.to_pydatetime()],
            "close": hist["Close"].values,
            "volume": hist["Volume"].values,
        }
    )


@daily_disk_cache
def fetch_mfapi_nav(scheme_code: int) -> pl.DataFrame | None:
    """Fetch NAV history from mfapi.in (single scheme)."""
    resp = httpx.get(f"{MFAPI_BASE}/{scheme_code}", timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "data" not in data or not data["data"]:
        return None

    records = []
    for item in data["data"]:
        parsed_date = datetime.strptime(item["date"], "%d-%m-%Y")
        nav = float(item["nav"])
        records.append({"date": parsed_date.strftime("%Y-%m-%d"), "nav": nav})

    if not records:
        return None

    return pl.DataFrame(records).sort("date")


def fetch_mfapi_chain(scheme_codes: list[int]) -> pl.DataFrame | None:
    """Fetch and stitch NAV history from a chain of mfapi.in scheme codes.

    Handles AMC transitions (Benchmark → Goldman Sachs → Nippon) by:
    1. Fetching each scheme's NAV history
    2. Normalizing overlapping dates (preferring later scheme)
    3. Concatenating into a single continuous timeline
    """
    if not scheme_codes:
        return None

    all_frames = []
    for code in scheme_codes:
        df = fetch_mfapi_nav(code)
        if df is not None:
            all_frames.append(df)

    if not all_frames:
        return None

    if len(all_frames) == 1:
        return all_frames[0]

    # Stitch: later schemes take priority on overlapping dates
    combined = pl.concat(all_frames)
    # group_by + last gives the latest scheme's NAV for any overlapping date
    combined = (
        combined.sort("date")
        .group_by("date")
        .last()
        .sort("date")
    )
    return combined


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_ticker(
    key: str,
    source: DataSource = DataSource.YFINANCE,
    period: str = "5y",
) -> pl.DataFrame | None:
    """Fetch data for a single ticker by key."""
    if key not in INDIA_UNIVERSE:
        return None

    _, yf_ticker, mfapi_codes, _ = INDIA_UNIVERSE[key]

    if source == DataSource.YFINANCE:
        if yf_ticker is None:
            return None
        return fetch_yfinance(yf_ticker, period)

    return fetch_mfapi_chain(mfapi_codes)


def fetch_all(
    source: DataSource = DataSource.YFINANCE,
    period: str = "5y",
    categories: list[str] | None = None,
) -> pl.DataFrame:
    """Fetch all tickers and return wide-format DataFrame.

    categories: optional filter, e.g. ["Factor:Mom", "Gold", "LargeCap"]
    """
    keys = list(INDIA_UNIVERSE.keys())
    if categories:
        keys = [
            k for k in keys if INDIA_UNIVERSE[k][3] in categories
        ]

    price_col = "close" if source == DataSource.YFINANCE else "nav"
    frames = []

    def _fetch_one(key):
        df = fetch_ticker(key, source, period)
        if df is None:
            return None
        if price_col not in df.columns:
            return None
        return df.select("date", pl.col(price_col).alias(key))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, k): k for k in keys}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                frames.append(result)
            else:
                key = futures[future]
                print(f"  skip {key}")

    if not frames:
        return pl.DataFrame()

    result = frames[0]
    for f in frames[1:]:
        result = result.join(f, on="date", how="full", coalesce=True)
    return result.sort("date")


# ---------------------------------------------------------------------------
# Momentum scoring (mirrors US script logic)
# ---------------------------------------------------------------------------

def compute_momentum(prices: pl.DataFrame, key: str) -> dict | None:
    """Compute momentum metrics for one ticker."""
    if key not in prices.columns:
        return None

    p = prices[key].drop_nulls().to_numpy()
    n = len(p)

    if n < LOOKBACK_3M + SKIP_1M:
        return None

    def mom(lookback):
        if n < lookback + SKIP_1M:
            return 0.0
        end_idx = n - SKIP_1M
        start_idx = end_idx - lookback
        return (p[end_idx - 1] / p[start_idx]) - 1

    mom_3m = mom(LOOKBACK_3M)
    mom_6m = mom(LOOKBACK_6M)
    mom_12m = mom(LOOKBACK_12M)
    wt_mom = 0.2 * mom_3m + 0.4 * mom_6m + 0.4 * mom_12m

    returns = np.diff(p) / p[:-1]
    neg_returns = returns[returns < 0]
    dn_vol = neg_returns.std() * np.sqrt(252) if len(neg_returns) > 0 else 0.0001

    running_max = np.maximum.accumulate(p)
    drawdown = (p - running_max) / running_max
    max_dd = drawdown.min()
    current_dd = drawdown[-1]

    # Sortino-weighted score (same as US script)
    score = wt_mom / dn_vol if dn_vol > 0 else 0.0

    return {
        "key": key,
        "name": INDIA_UNIVERSE[key][0],
        "category": INDIA_UNIVERSE[key][3],
        "records": n,
        "mom_3m": mom_3m,
        "mom_6m": mom_6m,
        "mom_12m": mom_12m,
        "wt_mom": wt_mom,
        "dn_vol": dn_vol,
        "score": score,
        "max_dd": max_dd,
        "current_dd": current_dd,
        "latest_price": float(p[-1]),
    }


def score_all(prices: pl.DataFrame) -> pl.DataFrame:
    """Compute momentum scores for all tickers in prices DataFrame."""
    rows = []
    for key in INDIA_UNIVERSE:
        stats = compute_momentum(prices, key)
        if stats is not None:
            rows.append(stats)
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("score", descending=True)


# ---------------------------------------------------------------------------
# Survivorship bias check
# ---------------------------------------------------------------------------

def check_survivorship_bias() -> None:
    """Verify scheme chains have continuous coverage."""
    chains_to_check = {
        k: v for k, v in INDIA_UNIVERSE.items() if len(v[2]) > 1
    }

    print(f"\n--- Survivorship Bias Check ({len(chains_to_check)} chains) ---")
    for key, (name, _, codes, _) in chains_to_check.items():
        total_records = 0
        segments = []
        for code in codes:
            df = fetch_mfapi_nav(code)
            if df is None:
                segments.append(f"  {code}: NO DATA")
                continue
            n = len(df)
            total_records += n
            first = df["date"].min()
            last = df["date"].max()
            segments.append(f"  {code}: {n} records ({first} to {last})")

        status = "OK" if total_records > 0 else "MISSING"
        print(f"[{status}] {key} ({name}) — {total_records} total records")
        for s in segments:
            print(f"    {s}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fmt_pct(v):
    return f"{v * 100:+.1f}%" if v else "N/A"


def main():
    print("=" * 110)
    print(f"INDIA UNIVERSE — {len(INDIA_UNIVERSE)} tickers | yfinance + mfapi.in")
    print("=" * 110)

    # Count by category
    cats = {}
    for _, (_, _, _, cat) in INDIA_UNIVERSE.items():
        cats[cat] = cats.get(cat, 0) + 1
    print("Categories:", "  ".join(f"{c}:{n}" for c, n in sorted(cats.items())))

    # Fetch yfinance prices
    print("\nFetching yfinance prices...")
    yf_prices = fetch_all(DataSource.YFINANCE)
    fetched = [c for c in yf_prices.columns if c != "date"]
    print(f"Got {len(fetched)} / {len(INDIA_UNIVERSE)} tickers from yfinance")

    # Score and rank
    scores = score_all(yf_prices)
    if scores.is_empty():
        print("No scores computed.")
        return

    # Print by category
    all_cats = sorted(set(INDIA_UNIVERSE[k][3] for k in INDIA_UNIVERSE))
    for cat in all_cats:
        cat_scores = scores.filter(pl.col("category") == cat)
        if cat_scores.is_empty():
            continue

        print(f"\n--- {cat} ({len(cat_scores)} tickers) ---")
        print(f"{'Key':14s} {'Name':30s} {'3M':>7} {'6M':>7} {'12M':>7} {'Score':>7} {'MaxDD':>7} {'CurrDD':>7} {'Price':>10}")
        print("-" * 110)
        for row in cat_scores.iter_rows(named=True):
            print(
                f"{row['key']:14s} {row['name']:30s} "
                f"{fmt_pct(row['mom_3m']):>7} {fmt_pct(row['mom_6m']):>7} {fmt_pct(row['mom_12m']):>7} "
                f"{row['score']:>7.2f} "
                f"{fmt_pct(row['max_dd']):>7} {fmt_pct(row['current_dd']):>7} "
                f"{row['latest_price']:>10.2f}"
            )

    # Top 20 overall
    print(f"\n{'=' * 110}")
    print("TOP 20 BY SORTINO-WEIGHTED MOMENTUM SCORE")
    print(f"{'=' * 110}")
    print(f"{'#':>3} {'Key':14s} {'Category':18s} {'3M':>7} {'6M':>7} {'12M':>7} {'Score':>7} {'MaxDD':>7}")
    print("-" * 90)
    for i, row in enumerate(scores.head(20).iter_rows(named=True), 1):
        print(
            f"{i:>3} {row['key']:14s} {row['category']:18s} "
            f"{fmt_pct(row['mom_3m']):>7} {fmt_pct(row['mom_6m']):>7} {fmt_pct(row['mom_12m']):>7} "
            f"{row['score']:>7.2f} {fmt_pct(row['max_dd']):>7}"
        )

    # Survivorship bias check for chained schemes
    check_survivorship_bias()

    # mfapi chain coverage for ETFs with chains
    chains = {k: v for k, v in INDIA_UNIVERSE.items() if len(v[2]) > 1}
    if chains:
        print(f"\n--- mfapi.in Stitched NAV History ---")
        for key in chains:
            df = fetch_ticker(key, DataSource.MFAPI)
            if df is not None:
                print(f"  {key:14s}  {len(df)} records  {df['date'].min()} to {df['date'].max()}")

    print(f"\n{'=' * 110}")


if __name__ == "__main__":
    main()
