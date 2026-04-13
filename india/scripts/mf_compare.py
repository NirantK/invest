"""
Compare Indian mutual funds using mfapi.in
Reusable — add funds to UNIVERSE dict, run with uv run python india/scripts/mf_compare.py

Metrics: CAGR, 3Y rolling median/avg/min/p25/p75, max drawdown, recovery time
"""

import datetime
import json
import time
from pathlib import Path

import numpy as np
import requests
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

# === FUND UNIVERSE ===
# Add scheme codes here. Find codes at: https://api.mfapi.in/mf/search?q=FUND_NAME

UNIVERSE = {
    # Multi-Asset
    "Tata Multi-Asset": 148053,
    "Nippon Multi-Asset": 148457,
    "ICICI Pru Multi-Asset": 120334,
    "HDFC Multi-Asset": 119131,
    "HDFC MA Active FOF": 148903,
    "Quant Multi-Asset": 120821,
    "SBI Multi-Asset": 119843,
    "Axis Multi-Asset": 120524,
    "Capitalmind Multi-Asset": 154232,
    # Flexi Cap
    "PPFAS Flexi Cap": 122639,
    "JM Flexicap": 120492,
    "Quant Flexi Cap": 120843,
    "Quant Active": 120823,
    "Capitalmind Flexi Cap": 153738,
    # Value
    "ICICI Value Discovery": 120594,
    "SBI Contra": 120578,
    # Small Cap
    "Nippon Small Cap": 118778,
    "Kotak Small Cap": 125497,
    "Axis Small Cap": 125354,
    "Quant Small Cap": 120828,
    # Mid Cap
    "Motilal Midcap": 127042,
    "HDFC Mid Cap": 118989,
    # Momentum / Factor
    "Tata Midcap Mom50": 150738,
    "UTI N200 Mom30": 148703,
    "ICICI Alpha LowVol30": 149158,
    "ICICI N100 LowVol30": 148822,
    # Hybrid
    "ICICI Pru BAF": 120377,
    "PPFAS Cons Hybrid": 145455,
    # Benchmark
    "UTI Nifty 50": 120716,
}


CACHE_DIR = Path(__file__).parent.parent / "data" / "nav_cache"


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=5, max=60, jitter=5),
    reraise=True,
)
def _fetch_from_api(scheme_code: int) -> dict:
    """Single API call with tenacity backoff."""
    resp = requests.get(
        f"https://api.mfapi.in/mf/{scheme_code}", timeout=90
    )
    resp.raise_for_status()
    data = resp.json()
    if "data" not in data or not data["data"]:
        raise ValueError(f"No data for {scheme_code}")
    return data


def _parse_nav_data(raw: list) -> tuple[np.ndarray, list]:
    """Parse raw mfapi data into navs array + dates list."""
    navs = np.array(
        [float(e["nav"]) for e in raw][::-1], dtype=np.float64
    )
    dates = [
        datetime.datetime.strptime(e["date"], "%d-%m-%Y").date()
        for e in raw
    ][::-1]
    valid = navs > 0
    return navs[valid], [d for d, v in zip(dates, valid) if v]


def fetch_nav(scheme_code: int) -> tuple[np.ndarray, list] | None:
    """Fetch NAV data with local daily cache + exponential backoff + jitter."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{scheme_code}.json"
    today = datetime.date.today().isoformat()

    # Use cache if from today
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached.get("date") == today and cached.get("data"):
            return _parse_nav_data(cached["data"])

    try:
        data = _fetch_from_api(scheme_code)
        cache_file.write_text(
            json.dumps({"date": today, "data": data["data"]})
        )
        return _parse_nav_data(data["data"])
    except Exception:
        # Fall back to stale cache if available
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
            if cached.get("data"):
                return _parse_nav_data(cached["data"])
        return None


def compute_metrics(navs: np.ndarray, dates: list) -> dict:
    """Compute all metrics for a NAV series."""
    n = len(navs)
    years = (dates[-1] - dates[0]).days / 365.25
    cagr = (navs[-1] / navs[0]) ** (1 / years) - 1

    # Max drawdown
    running_max = np.maximum.accumulate(navs)
    drawdowns = (navs - running_max) / running_max
    max_dd = drawdowns.min()

    # Drawdown duration (longest peak-to-recovery in months)
    max_dd_months = 0
    dd_start = None
    for i in range(n):
        if drawdowns[i] < -0.01:
            if dd_start is None:
                dd_start = i
        else:
            if dd_start is not None:
                months = (dates[i] - dates[dd_start]).days / 30.44
                max_dd_months = max(max_dd_months, months)
                dd_start = None
    if dd_start is not None:
        months = (dates[-1] - dates[dd_start]).days / 30.44
        max_dd_months = max(max_dd_months, months)

    result = {
        "cagr": cagr,
        "max_dd": max_dd,
        "max_dd_months": max_dd_months,
        "years": years,
        "n_points": n,
    }

    # Rolling returns: 1Y, 3Y, 5Y
    for label, td in [("1y", 252), ("3y", 756), ("5y", 1260)]:
        if n > td:
            yr = int(label[0])
            rolling = (navs[td:] / navs[:-td]) ** (1 / yr) - 1
            result[f"roll_{label}_median"] = np.median(rolling)
            result[f"roll_{label}_avg"] = np.mean(rolling)
            result[f"roll_{label}_min"] = np.min(rolling)
            result[f"roll_{label}_p25"] = np.percentile(rolling, 25)
            result[f"roll_{label}_p75"] = np.percentile(rolling, 75)
            result[f"roll_{label}_neg_pct"] = np.mean(rolling < 0) * 100
        else:
            for k in ["median", "avg", "min", "p25", "p75", "neg_pct"]:
                result[f"roll_{label}_{k}"] = None

    # Recent returns
    for label, days in [("1y", 252), ("6m", 126), ("3m", 63)]:
        if n > days:
            result[f"ret_{label}"] = navs[-1] / navs[-days] - 1
        else:
            result[f"ret_{label}"] = None

    return result


def fmt(val, digits=1):
    if val is None:
        return "—"
    return f"{val * 100:.{digits}f}%"


def main():
    print(f"Fetching {len(UNIVERSE)} funds from mfapi.in...")
    print()

    results = {}
    for name, code in UNIVERSE.items():
        data = fetch_nav(code)
        if data is None:
            print(f"  {name}: FAILED")
            continue
        navs, dates = data
        if len(navs) < 100:
            print(f"  {name}: SKIP ({len(navs)} pts)")
            continue
        metrics = compute_metrics(navs, dates)
        results[name] = metrics
        print(f"  {name}: OK ({len(navs)} pts, {metrics['years']:.1f}yr)")

    # Sort by 3Y rolling MEDIAN
    sorted_funds = sorted(
        results.items(),
        key=lambda x: x[1].get("roll_3y_median") or -999,
        reverse=True,
    )

    print()
    print("=" * 110)
    print("SORTED BY 3-YEAR ROLLING MEDIAN RETURN")
    print("=" * 110)
    header = f"{'Fund':<25s} {'CAGR':>6s} {'3Y MED':>7s} {'3Y Avg':>7s} {'3Y Min':>7s} {'3Y P25':>7s} {'3Y P75':>7s} {'MaxDD':>7s} {'DD Mo':>5s} {'Yrs':>4s}"
    print(header)
    print("-" * 110)

    for name, m in sorted_funds:
        dd_mo = f"{m['max_dd_months']:.0f}" if m["max_dd_months"] else "—"
        print(
            f"{name:<25s} {fmt(m['cagr']):>6s} {fmt(m.get('roll_3y_median')):>7s} "
            f"{fmt(m.get('roll_3y_avg')):>7s} {fmt(m.get('roll_3y_min')):>7s} "
            f"{fmt(m.get('roll_3y_p25')):>7s} {fmt(m.get('roll_3y_p75')):>7s} "
            f"{fmt(m['max_dd']):>7s} {dd_mo:>5s} {m['years']:>4.1f}"
        )

    # Multi-asset specific comparison
    ma_funds = [
        (n, m)
        for n, m in sorted_funds
        if any(
            kw in n.lower()
            for kw in ["multi", "balanced", "baf", "hybrid"]
        )
    ]
    if ma_funds:
        print()
        print("=" * 110)
        print("MULTI-ASSET / HYBRID FUNDS ONLY")
        print("=" * 110)
        print(header)
        print("-" * 110)
        for name, m in ma_funds:
            dd_mo = f"{m['max_dd_months']:.0f}" if m["max_dd_months"] else "—"
            print(
                f"{name:<25s} {fmt(m['cagr']):>6s} {fmt(m.get('roll_3y_median')):>7s} "
                f"{fmt(m.get('roll_3y_avg')):>7s} {fmt(m.get('roll_3y_min')):>7s} "
                f"{fmt(m.get('roll_3y_p25')):>7s} {fmt(m.get('roll_3y_p75')):>7s} "
                f"{fmt(m['max_dd']):>7s} {dd_mo:>5s} {m['years']:>4.1f}"
            )


if __name__ == "__main__":
    main()
