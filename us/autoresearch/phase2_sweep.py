"""
Phase 2 sweep: regime gate, DD stop, vol targeting, block-bootstrap MC, OOS split.

For each strategy variant:
  1. Run full-period backtest (3Y) → historical equity curve + metrics
  2. Block-bootstrap MC: resample 10-day blocks of daily returns → N paths × 3Y → percentiles
  3. Multi-regime stress: shift drift to target {bull, neutral, bear, shock}
  4. OOS split: train on first 2Y, test on final 1Y → OOS metrics

Writes:
  - phase2_results.json (raw)
  - phase2_summary.md (ranked recommendation)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import click
import numpy as np
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "us" / "scripts"))

from backtest_v2 import run_backtest, fetch_total_return_index  # type: ignore
from us_portfolio_allocation import TICKERS  # type: ignore
from invest.montecarlo import (
    block_bootstrap, batched_metrics, Percentiles, PERIODS_PER_YEAR,
)

console = Console()
HERE = Path(__file__).parent

# Strategy presets (Phase 2)
BASELINE = dict(
    score_col="score_sortino", sizing="equal", rebal_days=21,
    max_positions=15, max_pct=0.15, min_pct=0.03,
    min_adv=0.0, current_dd_floor=-0.25,  # default to no-ADV (proven Pareto win)
    use_sleeve_caps=True, leverage=1.0,
)

STRATEGIES = {
    "S0_baseline_no_adv":    {},
    "S1_regime_gate":        {"regime_gate": True},
    "S2_dd_stop_30":         {"dd_stop": 0.30},
    "S3_dd_stop_35":         {"dd_stop": 0.35},
    "S4_voltarget_20":       {"vol_target": 0.20},
    "S5_voltarget_25":       {"vol_target": 0.25},
    "S6_regime_dd35":        {"regime_gate": True, "dd_stop": 0.35},
    "S7_regime_volt20":      {"regime_gate": True, "vol_target": 0.20},
    "S8_volt20_dd35":        {"vol_target": 0.20, "dd_stop": 0.35},
    "S9_all_three_conserv":  {"regime_gate": True, "vol_target": 0.20, "dd_stop": 0.35},
    "S10_lev13_voltarget":   {"leverage": 1.3, "vol_target": 0.18},
    "S11_lev15_volt_dd":     {"leverage": 1.5, "vol_target": 0.20, "dd_stop": 0.35},
    "S12_no_inpain":         {"current_dd_floor": -1.0},
    "S13_no_inpain_volt":    {"current_dd_floor": -1.0, "vol_target": 0.22},
    "S14_no_sleeve_volt":    {"use_sleeve_caps": False, "vol_target": 0.20},
}


REGIME_DRIFT_TARGETS = {
    # Annual drift target after resample. Vol scales naturally with shifted returns.
    "bull":    None,    # use historical returns as-is
    "neutral": 0.10,    # shift to 10% annual drift
    "bear":   -0.20,    # shift to -20%
    "shock":  -0.40,    # shift to -40%
}


def percentiles(values) -> dict:
    """Thin shim — delegate to shared Percentiles."""
    return Percentiles.from_array(np.asarray(values)).to_dict()


def evaluate_strategy(name: str, prices, closes, dvols,
                      n_paths: int = 3000, horizon_years: int = 3,
                      block_size: int = 10, rebal_days: int | None = None) -> dict:
    """Run historical + OOS + block-bootstrap MC across regimes."""
    overrides = STRATEGIES[name]
    config = {**BASELINE, **overrides}
    if rebal_days is not None:
        config["rebal_days"] = rebal_days

    # Full backtest
    full = run_backtest(prices, closes, dvols, **config)
    eq = np.array(full.equity_curve)
    daily_rets = np.diff(eq) / eq[:-1] if len(eq) > 1 else np.array([0.0])

    # OOS: split data 2/3 train, 1/3 test (effective ~2y / 1y on 3y data)
    n_days = len(prices)
    train_end = int(n_days * 0.67)
    train_prices = prices.head(train_end)
    train_closes = closes.head(train_end)
    train_dvols = dvols.head(train_end)
    test_prices = prices.tail(n_days - train_end + 252)  # keep 252-day warmup overlap
    test_closes = closes.tail(n_days - train_end + 252)
    test_dvols = dvols.tail(n_days - train_end + 252)

    train_r = run_backtest(train_prices, train_closes, train_dvols, **config)
    # Test run uses the same config — the "OOS" question is whether the strategy generalizes
    test_r = run_backtest(test_prices, test_closes, test_dvols, **config)

    # Block-bootstrap MC on each regime — vectorized via shared lib
    horizon = horizon_years * PERIODS_PER_YEAR
    regimes_out = {}
    for regime, drift in REGIME_DRIFT_TARGETS.items():
        vol_mult = 1.5 if regime == "shock" else (1.2 if regime == "bear" else 1.0)
        sims = block_bootstrap(daily_rets, n_paths, horizon, block_size,
                                seed=42, drift_target_annual=drift, vol_mult=vol_mult)
        m = batched_metrics(sims)
        regimes_out[regime] = {
            "cagr": Percentiles.from_array(m["cagr"]).to_dict(),
            "ulcer": Percentiles.from_array(m["ulcer"]).to_dict(),
            "max_dd": Percentiles.from_array(m["max_dd"]).to_dict(),
            "martin": Percentiles.from_array(m["martin"]).to_dict(),
        }

    return {
        "name": name,
        "config": overrides,
        "historical": {
            "cagr": full.cagr, "ulcer": full.ulcer, "max_dd": full.max_dd,
            "martin": full.martin, "sharpe": full.sharpe,
            "pct_in_cash": full.pct_in_cash, "n_rebalances": full.n_rebalances,
        },
        "oos": {
            "train": {"cagr": train_r.cagr, "martin": train_r.martin, "ulcer": train_r.ulcer,
                      "max_dd": train_r.max_dd},
            "test": {"cagr": test_r.cagr, "martin": test_r.martin, "ulcer": test_r.ulcer,
                     "max_dd": test_r.max_dd},
        },
        "mc_by_regime": regimes_out,
    }


@click.command()
@click.option("--paths", default=2000, type=int)
@click.option("--years", default=3, type=int)
@click.option("--block-size", default=10, type=int)
@click.option("--strategies", default="all",
              help="Comma-separated names or 'all'.")
@click.option("--rebal-grid", default="21",
              help="Comma-separated rebal_days to test (e.g. '5,10,21,42,63').")
def main(paths, years, block_size, strategies, rebal_grid):
    console.print("[bold cyan]Phase 2 Sweep — block-bootstrap MC + OOS + multi-regime[/]")
    console.print(f"  paths={paths}, years={years}, block_size={block_size}\n")

    if strategies == "all":
        strats = list(STRATEGIES.keys())
    else:
        strats = [s.strip() for s in strategies.split(",")]

    rebal_list = tuple(int(x) for x in rebal_grid.split(",") if x.strip())
    console.print(f"  rebal_days grid: {rebal_list}")

    console.print("Fetching data...")
    prices, closes, dvols = fetch_total_return_index(TICKERS, period="3y")
    console.print(f"  {len(prices.columns) - 1} tickers, {len(prices)} days\n")

    cells = [(s, r) for s in strats for r in rebal_list]
    results = []
    for i, (s, rd) in enumerate(cells, 1):
        label = f"{s} @ {rd}d" if len(rebal_list) > 1 else s
        console.print(f"[{i:2d}/{len(cells)}] {label}")
        r = evaluate_strategy(s, prices, closes, dvols,
                               n_paths=paths, horizon_years=years, block_size=block_size,
                               rebal_days=rd)
        r["rebal_days"] = rd
        r["display_name"] = label
        results.append(r)
        h = r["historical"]
        oos = r["oos"]
        mc_bear = r["mc_by_regime"]["bear"]
        console.print(f"    Hist: CAGR={h['cagr']*100:>+5.0f}%  Martin={h['martin']:>5.2f}  "
                      f"Ulcer={h['ulcer']*100:>4.1f}%  MaxDD={h['max_dd']*100:>4.0f}%  cash={h['pct_in_cash']*100:>3.0f}%")
        console.print(f"    OOS:  train CAGR {oos['train']['cagr']*100:>+5.0f}% → "
                      f"test CAGR {oos['test']['cagr']*100:>+5.0f}%")
        console.print(f"    Bear MC: P25 CAGR {mc_bear['cagr']['p25']*100:>+5.0f}%, "
                      f"P50 {mc_bear['cagr']['p50']*100:>+5.0f}%, "
                      f"P75 Ulcer {mc_bear['ulcer']['p75']*100:.0f}%")

    # Score each strategy: weighted sum across regimes, OOS, historical
    def score_strategy(r):
        hist_martin = r["historical"]["martin"]
        oos_test_cagr = r["oos"]["test"]["cagr"]
        bull_p25 = r["mc_by_regime"]["bull"]["cagr"]["p25"]
        neutral_p25 = r["mc_by_regime"]["neutral"]["cagr"]["p25"]
        bear_p25 = r["mc_by_regime"]["bear"]["cagr"]["p25"]
        shock_p25 = r["mc_by_regime"]["shock"]["cagr"]["p25"]
        # Weight regimes for "blind 3Y hold": equal weight + emphasize bear
        avg_p25 = (bull_p25 + neutral_p25 + 2 * bear_p25 + shock_p25) / 5
        # Combined score: avg P25 + OOS + small Martin tilt
        return avg_p25 * 100 + oos_test_cagr * 50 + hist_martin * 2

    results.sort(key=lambda r: -score_strategy(r))

    # Display top
    table = Table(title="Phase 2 — Cross-Regime Robustness Ranking")
    table.add_column("Strategy", style="cyan", overflow="fold")
    table.add_column("Rebal", justify="right")
    table.add_column("Hist CAGR", justify="right")
    table.add_column("Hist Mart", justify="right")
    table.add_column("OOS Test", justify="right")
    table.add_column("Bull P25", justify="right")
    table.add_column("Neut P25", justify="right")
    table.add_column("Bear P25", justify="right")
    table.add_column("Shock P25", justify="right")
    table.add_column("Score", justify="right")

    for r in results:
        h = r["historical"]
        table.add_row(
            r["name"],
            f"{r.get('rebal_days', 21)}d",
            f"{h['cagr']*100:.0f}%",
            f"{h['martin']:.2f}",
            f"{r['oos']['test']['cagr']*100:+.0f}%",
            f"{r['mc_by_regime']['bull']['cagr']['p25']*100:+.0f}%",
            f"{r['mc_by_regime']['neutral']['cagr']['p25']*100:+.0f}%",
            f"{r['mc_by_regime']['bear']['cagr']['p25']*100:+.0f}%",
            f"{r['mc_by_regime']['shock']['cagr']['p25']*100:+.0f}%",
            f"{score_strategy(r):.1f}",
        )
    console.print(table)

    # Save
    out_json = HERE / "phase2_results.json"
    with out_json.open("w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "config": {"paths": paths, "years": years, "block_size": block_size,
                       "n_strategies": len(strats), "universe_size": len(TICKERS)},
            "results": results,
        }, f, indent=2)

    out_md = HERE / "phase2_summary.md"
    md = [f"# Phase 2 Sweep — {datetime.now().date()}", "",
          f"**Method:** Block-bootstrap MC (10-day blocks) on each strategy's historical equity curve, ",
          f"shifted to target each regime's drift (bull/neutral/bear/shock). Plus 2/3 → 1/3 OOS split.", "",
          f"**Universe:** {len(TICKERS)} tickers (162). **Paths:** {paths}. **Horizon:** {years}Y.", "",
          f"**Score:** weighted average P25 CAGR across regimes (bear weighted 2x) + OOS test CAGR + Martin.", "",
          "## Ranking (best for blind 3Y hold)", "",
          "| # | Strategy | Hist CAGR | Hist Martin | OOS Test | Bull P25 | Neut P25 | Bear P25 | Shock P25 | Score |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        h = r["historical"]
        md.append(
            f"| {i} | `{r['name']}` | {h['cagr']*100:.0f}% | {h['martin']:.2f} | "
            f"{r['oos']['test']['cagr']*100:+.0f}% | "
            f"{r['mc_by_regime']['bull']['cagr']['p25']*100:+.0f}% | "
            f"{r['mc_by_regime']['neutral']['cagr']['p25']*100:+.0f}% | "
            f"{r['mc_by_regime']['bear']['cagr']['p25']*100:+.0f}% | "
            f"{r['mc_by_regime']['shock']['cagr']['p25']*100:+.0f}% | "
            f"{score_strategy(r):.1f} |"
        )
    md += ["", "## Configurations", ""]
    for r in results[:5]:
        md.append(f"### {r['name']}")
        md.append("")
        md.append(f"Overrides: `{json.dumps(r['config'])}`")
        md.append("")
        md.append(f"- Historical: CAGR {r['historical']['cagr']*100:.0f}%, "
                  f"Martin {r['historical']['martin']:.2f}, Ulcer {r['historical']['ulcer']*100:.1f}%, "
                  f"MaxDD {r['historical']['max_dd']*100:.0f}%, %time-in-cash {r['historical']['pct_in_cash']*100:.0f}%")
        md.append(f"- OOS: train {r['oos']['train']['cagr']*100:+.0f}% → test {r['oos']['test']['cagr']*100:+.0f}% "
                  f"(MaxDD {r['oos']['test']['max_dd']*100:.0f}%)")
        for reg in ["bull", "neutral", "bear", "shock"]:
            mc = r["mc_by_regime"][reg]
            md.append(f"- {reg.title()} MC: P5/P25/P50/P75/P95 CAGR = "
                      f"{mc['cagr']['p5']*100:+.0f}% / {mc['cagr']['p25']*100:+.0f}% / "
                      f"{mc['cagr']['p50']*100:+.0f}% / {mc['cagr']['p75']*100:+.0f}% / "
                      f"{mc['cagr']['p95']*100:+.0f}%")
        md.append("")

    out_md.write_text("\n".join(md))
    console.print(f"\n[green]Wrote {out_json} and {out_md}[/]")


if __name__ == "__main__":
    main()
