"""
Fund rotation backtest using mfapi.in NAV data.

Strategies tested:
1. Buy & Hold (baseline for each fund)
2. Annual 12-1 Momentum Switch (pick best fund each April by trailing 12M-1M return)
3. Annual March Tax-Loss Harvest + April Switch
4. Dual Momentum (absolute + relative: go to liquid if 12M < 0)
5. Semi-Annual Rotation (every 6 months)
6. Factor Rotation (momentum vs small cap vs value based on which factor is winning)

Tax model:
- LTCG: 12.5% on gains above ₹1.25L exemption (holding > 12 months)
- STCG: 20% on all gains (holding < 12 months)
- Tax-loss harvesting: losses offset gains in same FY (April-March)
"""

import datetime
import numpy as np
import requests

# Fund universe — the actual contenders
FUNDS = {
    "Nippon Small Cap": 118778,
    "Kotak Small Cap": 125497,
    "Axis Small Cap": 125354,
    "Motilal Midcap": 127042,
    "HDFC Mid Cap": 118989,
    "Quant Mid Cap": 120841,
    "PPFAS Flexi Cap": 122639,
    "JM Flexicap": 120492,
    "ICICI Value Discovery": 120594,
    "SBI Contra": 120578,
    "UTI N200 Mom30": 148703,
    "Tata Midcap Mom50": 150738,
    "ICICI Alpha LowVol30": 149158,
}

# Liquid fund for parking during risk-off
LIQUID = {"HDFC Liquid": 119065}

INITIAL_CAPITAL = 1_000_000  # ₹10L
LTCG_RATE = 0.125
STCG_RATE = 0.20
LTCG_EXEMPTION = 125_000  # per FY


def fetch_nav(scheme_code: int) -> dict[datetime.date, float]:
    """Fetch NAV data, return as date->nav dict."""
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    resp = requests.get(url, timeout=30)
    data = resp.json().get("data", [])
    result = {}
    for entry in data:
        dt = datetime.datetime.strptime(entry["date"], "%d-%m-%Y").date()
        nav = float(entry["nav"])
        if nav > 0:
            result[dt] = nav
    return result


def to_monthly(nav_dict: dict) -> list[tuple[datetime.date, float]]:
    """Convert daily NAV dict to monthly (last trading day of each month)."""
    by_month = {}
    for dt, nav in sorted(nav_dict.items()):
        key = (dt.year, dt.month)
        by_month[key] = (dt, nav)
    return [(dt, nav) for dt, nav in by_month.values()]


def get_common_monthly(all_navs: dict[str, dict]) -> tuple[list[datetime.date], dict[str, np.ndarray]]:
    """Align all funds to common monthly dates."""
    monthly = {name: to_monthly(navs) for name, navs in all_navs.items()}

    # Find common months
    all_months = None
    for name, data in monthly.items():
        months = {(d.year, d.month) for d, _ in data}
        all_months = months if all_months is None else all_months & months

    common = sorted(all_months)
    dates = []
    arrays = {}

    for name, data in monthly.items():
        month_map = {(d.year, d.month): nav for d, nav in data}
        navs = []
        for ym in common:
            navs.append(month_map[ym])
        arrays[name] = np.array(navs)

    # Build dates list from first fund
    first = list(monthly.values())[0]
    date_map = {(d.year, d.month): d for d, _ in first}
    dates = [date_map[ym] for ym in common]

    return dates, arrays


def momentum_12_1(navs: np.ndarray, idx: int) -> float:
    """12-month return skipping last 1 month."""
    if idx < 12:
        return -999.0
    return navs[idx - 1] / navs[idx - 12] - 1.0


def run_backtest(dates, arrays, liquid_navs, strategy_name, strategy_fn):
    """Run a generic rotation backtest."""
    n = len(dates)
    fund_names = list(arrays.keys())

    capital = INITIAL_CAPITAL
    current_fund = None
    entry_price = 0
    entry_date = dates[0]
    units = 0

    total_tax_paid = 0
    total_switches = 0
    fy_gains = 0  # Track gains within financial year

    values = []

    for i in range(12, n):  # Start after 12 months for momentum calc
        # Get current portfolio value
        if current_fund and current_fund in arrays:
            portfolio_value = units * arrays[current_fund][i]
        elif current_fund == "LIQUID":
            portfolio_value = units * liquid_navs[i]
        else:
            portfolio_value = capital

        # Check if we should switch
        new_fund = strategy_fn(dates, arrays, liquid_navs, i, current_fund)

        if new_fund != current_fund and current_fund is not None:
            # Sell
            if current_fund in arrays:
                sell_nav = arrays[current_fund][i]
            else:
                sell_nav = liquid_navs[i]
            proceeds = units * sell_nav
            gain = proceeds - capital

            # Tax calculation
            holding_months = (dates[i].year - entry_date.year) * 12 + (dates[i].month - entry_date.month)
            if gain > 0:
                if holding_months >= 12:
                    taxable = max(0, gain - LTCG_EXEMPTION)
                    tax = taxable * LTCG_RATE
                else:
                    tax = gain * STCG_RATE
            else:
                tax = 0
                fy_gains += gain  # Accumulate losses for offset

            total_tax_paid += tax
            capital = proceeds - tax
            total_switches += 1

            # Buy new fund
            if new_fund in arrays:
                buy_nav = arrays[new_fund][i]
            else:
                buy_nav = liquid_navs[i]
            units = capital / buy_nav
            entry_price = buy_nav
            entry_date = dates[i]
            current_fund = new_fund

        elif current_fund is None:
            # Initial buy
            new_fund = strategy_fn(dates, arrays, liquid_navs, i, None)
            if new_fund in arrays:
                buy_nav = arrays[new_fund][i]
            else:
                buy_nav = liquid_navs[i]
            units = capital / buy_nav
            entry_price = buy_nav
            entry_date = dates[i]
            current_fund = new_fund

        # Record value
        if current_fund in arrays:
            val = units * arrays[current_fund][i]
        else:
            val = units * liquid_navs[i]
        values.append((dates[i], val, current_fund))

    return values, total_tax_paid, total_switches


# === STRATEGY DEFINITIONS ===

def strategy_buy_hold_nippon(dates, arrays, liquid, i, current):
    return "Nippon Small Cap"

def strategy_buy_hold_kotak(dates, arrays, liquid, i, current):
    return "Kotak Small Cap"

def strategy_buy_hold_tata_mom(dates, arrays, liquid, i, current):
    return "Tata Midcap Mom50"

def strategy_buy_hold_ppfas(dates, arrays, liquid, i, current):
    return "PPFAS Flexi Cap"

def strategy_annual_april_momentum(dates, arrays, liquid, i, current):
    """Switch every April to the fund with best 12-1 momentum."""
    dt = dates[i]
    if current is None or dt.month == 4:
        best_fund = None
        best_mom = -999
        for name, navs in arrays.items():
            mom = momentum_12_1(navs, i)
            if mom > best_mom:
                best_mom = mom
                best_fund = name
        return best_fund
    return current

def strategy_annual_march_harvest_april_switch(dates, arrays, liquid, i, current):
    """Sell losers in March (tax-loss harvest), switch to best momentum in April."""
    dt = dates[i]
    if current is None:
        return strategy_annual_april_momentum(dates, arrays, liquid, i, None)

    # March: if current fund has negative 12M return, sell to harvest loss
    if dt.month == 3:
        if current in arrays:
            ret_12m = arrays[current][i] / arrays[current][max(0, i - 12)] - 1
            if ret_12m < 0:
                return "LIQUID"  # Park in liquid, switch in April
        return current

    # April: switch to best momentum
    if dt.month == 4:
        best_fund = None
        best_mom = -999
        for name, navs in arrays.items():
            mom = momentum_12_1(navs, i)
            if mom > best_mom:
                best_mom = mom
                best_fund = name
        return best_fund

    return current

def strategy_dual_momentum_annual(dates, arrays, liquid, i, current):
    """Antonacci dual momentum: absolute + relative, annual April rebalance."""
    dt = dates[i]
    if current is None or dt.month == 4:
        # Find best relative momentum
        best_fund = None
        best_mom = -999
        for name, navs in arrays.items():
            mom = momentum_12_1(navs, i)
            if mom > best_mom:
                best_mom = mom
                best_fund = name

        # Absolute momentum check: if best fund has negative 12M, go to liquid
        if best_mom < 0:
            return "LIQUID"
        return best_fund
    return current

def strategy_semi_annual_momentum(dates, arrays, liquid, i, current):
    """Switch every 6 months (April + October) to best 12-1 momentum."""
    dt = dates[i]
    if current is None or dt.month in (4, 10):
        best_fund = None
        best_mom = -999
        for name, navs in arrays.items():
            mom = momentum_12_1(navs, i)
            if mom > best_mom:
                best_mom = mom
                best_fund = name
        return best_fund
    return current

def strategy_factor_rotation(dates, arrays, liquid, i, current):
    """Rotate between factor groups: small cap, midcap mom, value, flexi.
    Pick the best-performing factor group by 12-1 momentum each April."""
    dt = dates[i]
    if current is None or dt.month == 4:
        groups = {
            "small": ["Nippon Small Cap", "Kotak Small Cap", "Axis Small Cap"],
            "midcap": ["Motilal Midcap", "HDFC Mid Cap", "Quant Mid Cap"],
            "value": ["ICICI Value Discovery", "SBI Contra"],
            "flexi": ["PPFAS Flexi Cap", "JM Flexicap"],
        }

        # For each group, find average 12-1 momentum
        best_group = None
        best_group_mom = -999
        for group_name, funds in groups.items():
            moms = []
            for f in funds:
                if f in arrays:
                    moms.append(momentum_12_1(arrays[f], i))
            avg_mom = np.mean(moms) if moms else -999
            if avg_mom > best_group_mom:
                best_group_mom = avg_mom
                best_group = group_name

        # Within winning group, pick the best individual fund
        best_fund = None
        best_mom = -999
        for f in groups[best_group]:
            if f in arrays:
                mom = momentum_12_1(arrays[f], i)
                if mom > best_mom:
                    best_mom = mom
                    best_fund = f

        if best_mom < 0:
            return "LIQUID"
        return best_fund
    return current

def strategy_quarterly_top3_equal(dates, arrays, liquid, i, current):
    """Every quarter (Jan/Apr/Jul/Oct), equal-weight top 3 by 12-1 momentum.
    Simulated as picking the #1 fund but conceptually top-3."""
    dt = dates[i]
    if current is None or dt.month in (1, 4, 7, 10):
        scored = []
        for name, navs in arrays.items():
            mom = momentum_12_1(navs, i)
            scored.append((name, mom))
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored[0][1] < 0:
            return "LIQUID"
        return scored[0][0]
    return current


def main():
    print("Fetching NAV data...")
    all_navs = {}
    for name, code in {**FUNDS, **LIQUID}.items():
        print(f"  {name}...", end=" ", flush=True)
        navs = fetch_nav(code)
        print(f"{len(navs)} days")
        all_navs[name] = navs

    # Separate liquid
    liquid_raw = all_navs.pop("HDFC Liquid")

    print("\nAligning to common monthly dates...")
    # Add liquid back temporarily for alignment
    all_navs_with_liquid = {**all_navs, "LIQUID_ALIGN": liquid_raw}
    dates, arrays = get_common_monthly(all_navs_with_liquid)
    liquid_aligned = arrays.pop("LIQUID_ALIGN")

    print(f"Common period: {dates[0]} to {dates[-1]} ({len(dates)} months)")

    strategies = [
        ("Buy & Hold: Nippon Small Cap", strategy_buy_hold_nippon),
        ("Buy & Hold: Kotak Small Cap", strategy_buy_hold_kotak),
        ("Buy & Hold: PPFAS Flexi Cap", strategy_buy_hold_ppfas),
        ("Annual April 12-1 Momentum", strategy_annual_april_momentum),
        ("March Harvest + April Switch", strategy_annual_march_harvest_april_switch),
        ("Dual Momentum (Annual)", strategy_dual_momentum_annual),
        ("Semi-Annual Momentum", strategy_semi_annual_momentum),
        ("Factor Rotation (Annual)", strategy_factor_rotation),
        ("Quarterly Top Pick", strategy_quarterly_top3_equal),
    ]

    print(f"\n{'='*120}")
    print(f"BACKTEST RESULTS (₹{INITIAL_CAPITAL/100000:.0f}L initial, {dates[12]} to {dates[-1]})")
    print(f"{'='*120}")
    print(f"{'Strategy':<40s} {'Final Val':>12s} {'CAGR':>8s} {'Tax Paid':>10s} {'After-Tax':>12s} {'AT CAGR':>8s} {'Switches':>9s} {'MaxDD':>8s}")
    print("-" * 120)

    for name, fn in strategies:
        values, tax_paid, switches = run_backtest(dates, arrays, liquid_aligned, name, fn)
        if not values:
            continue

        final = values[-1][1]
        start_val = INITIAL_CAPITAL
        n_years = (values[-1][0] - values[0][0]).days / 365.25
        cagr = (final / start_val) ** (1.0 / n_years) - 1.0

        after_tax = final - tax_paid
        at_cagr = (after_tax / start_val) ** (1.0 / n_years) - 1.0

        # Max drawdown
        peak = 0
        max_dd = 0
        for _, v, _ in values:
            peak = max(peak, v)
            dd = (v - peak) / peak
            max_dd = min(max_dd, dd)

        print(f"{name:<40s} ₹{final/100000:>9.1f}L {cagr*100:>7.1f}% ₹{tax_paid/100000:>7.1f}L ₹{after_tax/100000:>9.1f}L {at_cagr*100:>7.1f}% {switches:>8d} {max_dd*100:>7.1f}%")

    # Print what fund was held when, for the best strategies
    print(f"\n{'='*120}")
    print("FUND SELECTION HISTORY: Annual April 12-1 Momentum")
    print(f"{'='*120}")
    values, _, _ = run_backtest(dates, arrays, liquid_aligned, "detail", strategy_annual_april_momentum)
    prev_fund = None
    for dt, val, fund in values:
        if fund != prev_fund:
            print(f"  {dt}: → {fund} (portfolio: ₹{val/100000:.1f}L)")
            prev_fund = fund

    print(f"\n{'='*120}")
    print("FUND SELECTION HISTORY: Factor Rotation")
    print(f"{'='*120}")
    values, _, _ = run_backtest(dates, arrays, liquid_aligned, "detail", strategy_factor_rotation)
    prev_fund = None
    for dt, val, fund in values:
        if fund != prev_fund:
            print(f"  {dt}: → {fund} (portfolio: ₹{val/100000:.1f}L)")
            prev_fund = fund

    print(f"\n{'='*120}")
    print("FUND SELECTION HISTORY: Dual Momentum")
    print(f"{'='*120}")
    values, _, _ = run_backtest(dates, arrays, liquid_aligned, "detail", strategy_dual_momentum_annual)
    prev_fund = None
    for dt, val, fund in values:
        if fund != prev_fund:
            print(f"  {dt}: → {fund} (portfolio: ₹{val/100000:.1f}L)")
            prev_fund = fund


if __name__ == "__main__":
    main()
