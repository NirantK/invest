"""
Comprehensive MF analysis: rolling returns (1Y, 3Y, 5Y) + risk metrics.
Fetches from mfapi.in. Covers flexi caps, multi-asset, momentum, value, quality, low-vol.
"""

import datetime
import numpy as np
import requests


FUNDS = {
    # === FLEXI CAP (long history, proven) ===
    "PPFAS Flexi Cap": 122639,
    "JM Flexicap": 120492,
    # === MULTI-ASSET (correct Direct Growth codes) ===
    "ICICI Pru Multi-Asset": 120334,
    "HDFC Multi-Asset": 119131,
    "HDFC MA Active FOF": 148903,
    "Quant Multi-Asset": 120821,
    "Motilal Multi-Asset": 148454,
    "Tata Multi-Asset": 148053,
    "Nippon Multi-Asset": 148457,
    "SBI Multi-Asset": 119843,
    "WhiteOak Multi-Asset": 151745,
    "Axis Multi-Asset": 120524,
    "Groww Multi-Asset": 153821,
    # === PASSIVE MULTI-ASSET / REBALANCING ===
    "Zerodha Multi-Asset FoF": 153757,
    "ICICI Passive Multi-Asset": 149441,
    # === CAPITALMIND ===
    "Capitalmind Flexi Cap": 153738,
    "Capitalmind Multi-Asset": 154232,
    # === LARGE & MID CAP ===
    "Mirae Large & Mid": 146200,
    "Kotak Equity Opp": 120205,
    # === MOMENTUM INDEX ===
    "UTI N200 Mom30": 148703,
    "Tata Midcap150 Mom50": 150738,
    # === LOW VOL / ALPHA ===
    "ICICI Alpha LowVol30": 149158,
    "ICICI N100 LowVol30": 148822,
    # === VALUE ===
    "ICICI Pru Value Discovery": 120594,
    "SBI Contra": 120578,
    # === SMALL CAP ===
    "Nippon Small Cap": 118778,
    "Quant Small Cap": 120828,
    # === ACTIVE MID CAP ===
    "Motilal Oswal Midcap": 127042,
    # === BENCHMARK ===
    "UTI Nifty 50 Index": 120716,
    # === HYBRID / CONSERVATIVE ===
    "PPFAS Conservative Hybrid": 145455,
    "ICICI Pru BAF": 120377,
}


def fetch_nav(scheme_code: int) -> tuple[np.ndarray, np.ndarray] | None:
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        return None
    payload = resp.json()
    if "data" not in payload or not payload["data"]:
        return None
    data = payload["data"]

    dates, navs = [], []
    for entry in data:
        dt = datetime.datetime.strptime(entry["date"], "%d-%m-%Y").date()
        dates.append(dt)
        navs.append(float(entry["nav"]))

    dates = np.array(dates[::-1])
    navs = np.array(navs[::-1], dtype=np.float64)
    valid = navs > 0
    return dates[valid], navs[valid]


def compute_full_metrics(dates, navs):
    n = len(navs)
    days = (dates[-1] - dates[0]).days
    years = days / 365.25
    cagr = (navs[-1] / navs[0]) ** (1.0 / years) - 1.0

    daily_ret = np.diff(navs) / navs[:-1]
    running_max = np.maximum.accumulate(navs)
    drawdowns = (navs - running_max) / running_max
    max_dd = drawdowns.min()

    # Ulcer Index
    ulcer = np.sqrt(np.mean(drawdowns**2))

    # Pain Index
    pain = np.mean(np.abs(drawdowns))

    # Sortino (annualized, MAR=0)
    downside = daily_ret[daily_ret < 0]
    dn_vol = np.sqrt(np.mean(downside**2)) * np.sqrt(252) if len(downside) > 0 else 0
    mean_ann = np.mean(daily_ret) * 252
    sortino = mean_ann / dn_vol if dn_vol > 0 else np.inf

    # Calmar (CAGR / |MaxDD|)
    calmar = cagr / abs(max_dd) if max_dd != 0 else np.inf

    # UPI (Martin Ratio = excess return / ulcer index)
    risk_free_ann = 0.06  # ~6% India risk-free
    upi = (cagr - risk_free_ann) / ulcer if ulcer > 0 else np.inf

    # Rolling returns
    result = {
        "cagr": cagr,
        "max_dd": max_dd,
        "ulcer": ulcer,
        "pain": pain,
        "sortino": sortino,
        "calmar": calmar,
        "upi": upi,
        "years": years,
    }

    for yr_label, td in [("1y", 252), ("3y", 756), ("5y", 1260)]:
        if n > td:
            rolling = navs[td:] / navs[:-td]
            if yr_label != "1y":
                y = int(yr_label[0])
                rolling = rolling ** (1.0 / y) - 1.0
            else:
                rolling = rolling - 1.0
            result[f"roll_{yr_label}_avg"] = np.mean(rolling)
            result[f"roll_{yr_label}_med"] = np.median(rolling)
            result[f"roll_{yr_label}_min"] = np.min(rolling)
            result[f"roll_{yr_label}_max"] = np.max(rolling)
            result[f"roll_{yr_label}_p25"] = np.percentile(rolling, 25)
            result[f"roll_{yr_label}_p75"] = np.percentile(rolling, 75)
            result[f"roll_{yr_label}_neg_pct"] = np.mean(rolling < 0) * 100
        else:
            for k in ["avg", "med", "min", "max", "p25", "p75", "neg_pct"]:
                result[f"roll_{yr_label}_{k}"] = None

    return result


def pct(v, digits=1):
    return f"{v*100:.{digits}f}%" if v is not None else "—"


def main():
    all_metrics = {}
    for name, code in FUNDS.items():
        print(f"Fetching {name}...", end=" ", flush=True)
        result = fetch_nav(code)
        if result is None:
            print("FAILED")
            continue
        dates, navs = result
        if len(navs) < 100:
            print(f"SKIP ({len(navs)} pts, too short)")
            continue
        print(f"{len(navs)} pts, {dates[0]}→{dates[-1]}")
        all_metrics[name] = compute_full_metrics(dates, navs)

    # === TABLE 1: CAGR + Risk Metrics (sorted by UPI) ===
    print("\n" + "=" * 140)
    print("RISK-ADJUSTED RETURNS (sorted by UPI = Martin Ratio)")
    print("=" * 140)
    hdr = f"{'Fund':<28s} {'CAGR':>7s} {'MaxDD':>7s} {'Ulcer':>7s} {'Pain':>7s} {'Sortino':>8s} {'Calmar':>7s} {'UPI':>7s} {'Yrs':>5s}"
    print(hdr)
    print("-" * 140)
    ranked = sorted(all_metrics.items(), key=lambda x: x[1].get("upi", 0), reverse=True)
    for name, m in ranked:
        print(f"{name:<28s} {pct(m['cagr']):>7s} {pct(m['max_dd']):>7s} {m['ulcer']:.4f}  {m['pain']:.4f}  {m['sortino']:>7.2f} {m['calmar']:>7.2f} {m['upi']:>7.2f} {m['years']:>5.1f}")

    # === TABLE 2: 3Y Rolling (sorted by avg) ===
    print("\n" + "=" * 140)
    print("3-YEAR ROLLING RETURNS (sorted by average)")
    print("=" * 140)
    hdr = f"{'Fund':<28s} {'Latest':>8s} {'Avg':>8s} {'Med':>8s} {'P25':>8s} {'P75':>8s} {'Min':>8s} {'Max':>8s} {'%Neg':>6s}"
    print(hdr)
    print("-" * 140)
    has_3y = [(n, m) for n, m in all_metrics.items() if m.get("roll_3y_avg") is not None]
    has_3y.sort(key=lambda x: x[1]["roll_3y_avg"], reverse=True)
    for name, m in has_3y:
        # Latest = use avg as proxy (mfapi doesn't give us latest easily here)
        print(f"{name:<28s} {pct(m['roll_3y_avg']):>8s} {pct(m['roll_3y_avg']):>8s} {pct(m['roll_3y_med']):>8s} {pct(m['roll_3y_p25']):>8s} {pct(m['roll_3y_p75']):>8s} {pct(m['roll_3y_min']):>8s} {pct(m['roll_3y_max']):>8s} {m['roll_3y_neg_pct']:>5.1f}%")

    # === TABLE 3: 1Y Rolling (sorted by avg) ===
    print("\n" + "=" * 140)
    print("1-YEAR ROLLING RETURNS (sorted by average)")
    print("=" * 140)
    hdr = f"{'Fund':<28s} {'Avg':>8s} {'Med':>8s} {'P25':>8s} {'P75':>8s} {'Min':>8s} {'Max':>8s} {'%Neg':>6s}"
    print(hdr)
    print("-" * 140)
    has_1y = [(n, m) for n, m in all_metrics.items() if m.get("roll_1y_avg") is not None]
    has_1y.sort(key=lambda x: x[1]["roll_1y_avg"], reverse=True)
    for name, m in has_1y:
        print(f"{name:<28s} {pct(m['roll_1y_avg']):>8s} {pct(m['roll_1y_med']):>8s} {pct(m['roll_1y_p25']):>8s} {pct(m['roll_1y_p75']):>8s} {pct(m['roll_1y_min']):>8s} {pct(m['roll_1y_max']):>8s} {m['roll_1y_neg_pct']:>5.1f}%")

    # === TABLE 4: Downside protection ===
    print("\n" + "=" * 140)
    print("DOWNSIDE PROTECTION (sorted by worst 3Y rolling return)")
    print("=" * 140)
    hdr = f"{'Fund':<28s} {'Worst3Y':>8s} {'Worst1Y':>8s} {'MaxDD':>8s} {'%Neg1Y':>8s} {'%Neg3Y':>8s} {'Ulcer':>8s}"
    print(hdr)
    print("-" * 140)
    has_3y.sort(key=lambda x: x[1].get("roll_3y_min", -999), reverse=True)
    for name, m in has_3y:
        w1y = pct(m.get("roll_1y_min")) if m.get("roll_1y_min") is not None else "—"
        neg1y = f"{m.get('roll_1y_neg_pct', 0):.1f}%" if m.get("roll_1y_neg_pct") is not None else "—"
        print(f"{name:<28s} {pct(m['roll_3y_min']):>8s} {w1y:>8s} {pct(m['max_dd']):>8s} {neg1y:>8s} {m['roll_3y_neg_pct']:>7.1f}% {m['ulcer']:>7.4f}")


if __name__ == "__main__":
    main()
