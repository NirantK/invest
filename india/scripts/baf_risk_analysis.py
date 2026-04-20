"""
Balanced Advantage Fund (BAF) Risk/Pain Metrics Analysis
Fetches NAV data from mfapi.in and computes comprehensive risk metrics.
"""

import datetime
import requests
import numpy as np

# Scheme codes for top BAFs (Direct Growth)
SCHEMES = {
    "ICICI Pru BAF": 120377,
    "HDFC BAF": 118968,
    "Kotak BAF": 144335,
    "Edelweiss BAF": 118615,
    "Tata BAF": 146010,
    "SBI BAF": 149134,
    "Nippon BAF": 118736,
    "Quantum Liquid": 103734,
}


def fetch_nav(scheme_code: int) -> tuple[np.ndarray, np.ndarray]:
    """Fetch NAV data from mfapi.in. Returns (dates_array, nav_array) sorted ascending."""
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()["data"]

    dates = []
    navs = []
    for entry in data:
        dt = datetime.datetime.strptime(entry["date"], "%d-%m-%Y").date()
        dates.append(dt)
        navs.append(float(entry["nav"]))

    # mfapi returns newest first, reverse to ascending
    dates = np.array(dates[::-1])
    navs = np.array(navs[::-1], dtype=np.float64)

    # Filter out zero or negative NAVs
    valid = navs > 0
    dates = dates[valid]
    navs = navs[valid]
    return dates, navs


def compute_metrics(dates: np.ndarray, navs: np.ndarray) -> dict:
    """Compute all risk/pain metrics for a NAV series."""
    n = len(navs)
    if n < 30:
        return {}

    # Basic
    days = (dates[-1] - dates[0]).days
    years = days / 365.25
    total_return = navs[-1] / navs[0]
    cagr = total_return ** (1.0 / years) - 1.0 if years > 0 else 0.0

    # Daily returns
    daily_ret = np.diff(navs) / navs[:-1]

    # Drawdown series
    running_max = np.maximum.accumulate(navs)
    drawdowns = (navs - running_max) / running_max  # negative values

    # Max drawdown
    max_dd = drawdowns.min()

    # RoMAD / Calmar
    romad = cagr / abs(max_dd) if max_dd != 0 else np.inf

    # Longest drawdown duration (days from peak to recovery)
    longest_dd_days = 0
    current_dd_start = None
    for i in range(n):
        if drawdowns[i] < 0:
            if current_dd_start is None:
                current_dd_start = i
        else:
            if current_dd_start is not None:
                dd_days = (dates[i] - dates[current_dd_start]).days
                longest_dd_days = max(longest_dd_days, dd_days)
                current_dd_start = None
    # Handle ongoing drawdown
    if current_dd_start is not None:
        dd_days = (dates[-1] - dates[current_dd_start]).days
        longest_dd_days = max(longest_dd_days, dd_days)

    # Ulcer Index (RMS of drawdowns)
    ulcer_index = np.sqrt(np.mean(drawdowns**2))

    # Pain Index (mean of absolute drawdowns)
    pain_index = np.mean(np.abs(drawdowns))

    # Rolling returns
    worst_1y = np.nan
    worst_6m = np.nan
    neg_1y_pct = np.nan

    # Use ~252 trading days for 1Y, ~126 for 6M
    if n > 252:
        rolling_1y = navs[252:] / navs[:-252] - 1.0
        worst_1y = rolling_1y.min()
        neg_1y_pct = np.mean(rolling_1y < 0) * 100.0

    if n > 126:
        rolling_6m = navs[126:] / navs[:-126] - 1.0
        worst_6m = rolling_6m.min()

    # Sortino ratio (daily, MAR=0, annualized)
    downside = daily_ret[daily_ret < 0]
    downside_vol = np.sqrt(np.mean(downside**2)) * np.sqrt(252) if len(downside) > 0 else 0.0
    mean_annual_ret = np.mean(daily_ret) * 252
    sortino = mean_annual_ret / downside_vol if downside_vol > 0 else np.inf

    # Monthly returns for VaR
    # Approximate: use ~21 trading day blocks
    step = 21
    monthly_rets = []
    for i in range(0, n - step, step):
        mr = navs[i + step] / navs[i] - 1.0
        monthly_rets.append(mr)
    monthly_rets = np.array(monthly_rets)
    var_95 = np.percentile(monthly_rets, 5) if len(monthly_rets) > 0 else np.nan

    return {
        "CAGR": cagr,
        "Max DD": max_dd,
        "RoMAD": romad,
        "Longest DD (days)": longest_dd_days,
        "Ulcer Index": ulcer_index,
        "Pain Index": pain_index,
        "Worst 1Y Ret": worst_1y,
        "Worst 6M Ret": worst_6m,
        "% Neg 1Y Periods": neg_1y_pct,
        "Sortino": sortino,
        "95% VaR (Monthly)": var_95,
        "Period (yrs)": years,
        "Data Points": n,
    }


def filter_last_n_years(dates, navs, n_years=5):
    """Filter to last n_years of data."""
    cutoff = dates[-1] - datetime.timedelta(days=int(n_years * 365.25))
    mask = dates >= cutoff
    return dates[mask], navs[mask]


def fmt(val, kind="pct"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if kind == "pct":
        return f"{val * 100:+.2f}%"
    if kind == "pct_abs":
        return f"{val * 100:.2f}%"
    if kind == "ratio":
        return f"{val:.2f}"
    if kind == "int":
        return f"{int(val)}"
    if kind == "float":
        return f"{val:.4f}"
    return str(val)


def print_table(title: str, all_metrics: dict[str, dict]):
    """Print a formatted comparison table."""
    print(f"\n{'=' * 120}")
    print(f"  {title}")
    print(f"{'=' * 120}")

    names = list(all_metrics.keys())
    # Column width
    label_w = 22
    col_w = 16

    # Header
    header = f"{'Metric':<{label_w}}"
    for name in names:
        short = name[:col_w - 1]
        header += f"{short:>{col_w}}"
    print(header)
    print("-" * (label_w + col_w * len(names)))

    rows = [
        ("CAGR", "pct"),
        ("Max DD", "pct"),
        ("RoMAD", "ratio"),
        ("Longest DD (days)", "int"),
        ("Ulcer Index", "float"),
        ("Pain Index", "float"),
        ("Worst 1Y Ret", "pct"),
        ("Worst 6M Ret", "pct"),
        ("% Neg 1Y Periods", "ratio"),
        ("Sortino", "ratio"),
        ("95% VaR (Monthly)", "pct"),
        ("Period (yrs)", "ratio"),
        ("Data Points", "int"),
    ]

    for metric_name, kind in rows:
        row = f"{metric_name:<{label_w}}"
        for name in names:
            m = all_metrics[name]
            val = m.get(metric_name)
            if metric_name == "% Neg 1Y Periods":
                row += f"{fmt(val / 100 if val is not None and not np.isnan(val) else val, 'pct_abs'):>{col_w}}"
            else:
                row += f"{fmt(val, kind):>{col_w}}"
        print(row)

    print()


def main():
    print("Fetching NAV data from mfapi.in ...")

    all_data = {}
    for name, code in SCHEMES.items():
        print(f"  Fetching {name} ({code}) ...", end=" ", flush=True)
        dates, navs = fetch_nav(code)
        all_data[name] = (dates, navs)
        print(f"{len(navs)} data points, {dates[0]} to {dates[-1]}")

    # Full history metrics
    full_metrics = {}
    for name, (dates, navs) in all_data.items():
        full_metrics[name] = compute_metrics(dates, navs)

    print_table("FULL HISTORY — Risk & Pain Metrics", full_metrics)

    # Last 5 years
    five_yr_metrics = {}
    for name, (dates, navs) in all_data.items():
        d5, n5 = filter_last_n_years(dates, navs, 5)
        five_yr_metrics[name] = compute_metrics(d5, n5)

    print_table("LAST 5 YEARS — Risk & Pain Metrics", five_yr_metrics)

    # Ranking summary
    print("=" * 80)
    print("  RANKING SUMMARY (Last 5Y, lower rank = better)")
    print("=" * 80)

    baf_names = [n for n in SCHEMES if "Liquid" not in n and "Bench" not in n]
    rank_metrics = ["CAGR", "Max DD", "RoMAD", "Sortino", "Ulcer Index", "Pain Index"]

    # For each metric, rank the BAFs
    rankings = {n: 0 for n in baf_names}
    for metric in rank_metrics:
        vals = []
        for name in baf_names:
            v = five_yr_metrics[name].get(metric, np.nan)
            if v is None or np.isnan(v):
                v = -999 if metric in ["CAGR", "RoMAD", "Sortino"] else 999
            vals.append((name, v))

        # Higher is better for CAGR, RoMAD, Sortino; lower is better for others
        higher_better = metric in ["CAGR", "RoMAD", "Sortino"]
        vals.sort(key=lambda x: x[1], reverse=higher_better)

        print(f"\n  {metric}:")
        for rank, (name, v) in enumerate(vals, 1):
            rankings[name] += rank
            kind = "pct" if metric in ["CAGR", "Max DD"] else ("ratio" if metric in ["RoMAD", "Sortino"] else "float")
            print(f"    {rank}. {name:<20s} {fmt(v, kind)}")

    # Overall
    print(f"\n{'=' * 80}")
    print("  OVERALL COMPOSITE RANKING (sum of ranks, lower = better)")
    print(f"{'=' * 80}")
    sorted_ranks = sorted(rankings.items(), key=lambda x: x[1])
    for rank, (name, score) in enumerate(sorted_ranks, 1):
        print(f"    {rank}. {name:<20s} Score: {score}")


if __name__ == "__main__":
    main()
