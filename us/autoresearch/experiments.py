"""
Run a batch of autoresearch hypotheses. Each varies ONE knob from the baseline.
Logs all results to experiments.jsonl + writes a comparison summary.

Hypotheses focus on understanding what drove winners in the 2023-2026 regime,
and what relaxations of our defensive constraints would have captured more upside.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "us" / "scripts"))

from backtest_v2 import run_backtest, fetch_total_return_index  # type: ignore
from us_portfolio_allocation import TICKERS  # type: ignore

HERE = Path(__file__).parent
LOG = HERE / "experiments.jsonl"
SUMMARY = HERE / "experiments_summary.md"

# Baseline (best from initial 27-combo sweep)
BASELINE = dict(
    score_col="score_sortino", sizing="equal", rebal_days=21,
    max_positions=15, max_pct=0.15, min_pct=0.03,
    min_adv=5_000_000.0, current_dd_floor=-0.25,
    use_sleeve_caps=True, leverage=1.0,
)

# Hypothesis: (name, hypothesis text, overrides_dict)
HYPOTHESES = [
    ("baseline", "Reproduce baseline (sortino × equal × 21d, all gates on)", {}),

    ("h1_top5", "Concentrate to top 5 names — let winners dominate (price of admission: higher Ulcer)",
     {"max_positions": 5, "max_pct": 0.30, "min_pct": 0.05}),

    ("h2_top8", "Concentrate to top 8 — middle ground vs current 15",
     {"max_positions": 8, "max_pct": 0.20, "min_pct": 0.05}),

    ("h3_no_sleeves", "Drop sleeve caps — let AI Infra run organic (was 64% before caps demoted to 40%)",
     {"use_sleeve_caps": False}),

    ("h4_no_adv", "Drop $5M ADV gate — admit thin-tape rockets (some 10x names live there)",
     {"min_adv": 0.0}),

    ("h5_no_inpain", "Drop in-pain filter — INTC was -50% before +132%; recovery setups beat momentum continuation",
     {"current_dd_floor": -1.0}),

    ("h6_raw_top8", "Score-weighted raw + top 8 — concentration AND magnitude tilt",
     {"max_positions": 8, "max_pct": 0.20, "min_pct": 0.05, "sizing": "raw"}),

    ("h7_leverage_13", "1.3x leverage — multiplicative on equity curve, equivalent risk magnification",
     {"leverage": 1.3}),

    ("h8_leverage_15", "1.5x leverage — half-step toward 2x (margin-feasible at IBKR)",
     {"leverage": 1.5}),

    ("h9_rank_top8", "Score_rank + sqrt + top 8 — diversified-but-concentrated, lowest-Ulcer profile",
     {"max_positions": 8, "max_pct": 0.20, "min_pct": 0.05,
      "score_col": "score_rank", "sizing": "sqrt"}),

    ("h10_aggressive", "Top 7 + no sleeves + raw weight — combined aggression",
     {"max_positions": 7, "max_pct": 0.25, "min_pct": 0.05,
      "use_sleeve_caps": False, "sizing": "raw"}),

    ("h11_max_aggression", "Top 5 + no sleeves + no in-pain + 1.3x lev — what 120% guys do",
     {"max_positions": 5, "max_pct": 0.30, "min_pct": 0.05,
      "use_sleeve_caps": False, "current_dd_floor": -1.0, "leverage": 1.3}),

    ("h12_top20_safe", "Top 20 — control group: more diversification, lower vol",
     {"max_positions": 20, "max_pct": 0.10, "min_pct": 0.025}),

    ("h13_weekly_rebal", "5-day rebalance — capture short-horizon momentum shifts",
     {"rebal_days": 5}),

    ("h14_biweekly_rebal", "10-day rebalance — between weekly and monthly",
     {"rebal_days": 10}),

    ("h15_no_min", "Drop the 3% min-position floor — let small bets through",
     {"min_pct": 0.0}),
]


def main():
    print(f"Fetching data ({len(TICKERS)} tickers, 3y)...")
    prices, closes, dvols = fetch_total_return_index(TICKERS, period="3y")
    print(f"  {len(prices.columns)-1} tickers loaded, {len(prices)} days")

    results = []
    history = []
    if LOG.exists():
        history = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]
    next_iter = max((h.get("iteration", 0) for h in history), default=0) + 1

    print(f"\nRunning {len(HYPOTHESES)} hypotheses...\n")
    for i, (name, hypothesis, overrides) in enumerate(HYPOTHESES, 1):
        config = {**BASELINE, **overrides}
        print(f"[{i:2d}/{len(HYPOTHESES)}] {name:20s}", end="", flush=True)
        r = run_backtest(prices, closes, dvols, **config)
        m = dict(cagr=r.cagr, sharpe=r.sharpe, martin=r.martin, ulcer=r.ulcer,
                 max_dd=r.max_dd, total_return=r.total_return,
                 avg_positions=r.avg_positions, n_rebalances=r.n_rebalances)
        print(f"  CAGR={m['cagr']*100:>6.1f}%  Martin={m['martin']:>5.2f}  "
              f"Ulcer={m['ulcer']*100:>4.1f}%  DD={m['max_dd']*100:>4.0f}%  AvgPos={m['avg_positions']:>4.1f}")
        entry = dict(
            iteration=next_iter,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            hypothesis=hypothesis,
            name=name,
            config=overrides if name != "baseline" else config,
            metrics=m,
            kept=False,
            decision_reason="batch sweep — see comparison",
        )
        results.append((name, hypothesis, overrides, m))
        history.append(entry)
        next_iter += 1

    # Append all to log
    with LOG.open("a") as f:
        for entry in history[len(history) - len(HYPOTHESES):]:
            f.write(json.dumps(entry) + "\n")

    # Determine winner per metric
    by_martin = sorted(results, key=lambda r: -r[3]["martin"])
    by_cagr = sorted(results, key=lambda r: -r[3]["cagr"])
    by_ulcer = sorted(results, key=lambda r: r[3]["ulcer"])

    # Write summary
    lines = [
        f"# Autoresearch Sweep — {datetime.now().date()}",
        "",
        f"Tested {len(HYPOTHESES)} hypotheses. Each varies ONE+ knobs from the baseline:",
        "`score_sortino × equal × 21d × top 15 × sleeves on × ADV $5M × in-pain -25%`",
        "",
        "## Summary table",
        "",
        "| Name | CAGR | Martin | Ulcer | MaxDD | AvgPos | Hypothesis |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, hyp, _, m in results:
        lines.append(
            f"| {name} | {m['cagr']*100:.1f}% | {m['martin']:.2f} | "
            f"{m['ulcer']*100:.1f}% | {m['max_dd']*100:.0f}% | {m['avg_positions']:.1f} | {hyp[:60]} |"
        )

    lines += [
        "",
        "## Winners by metric",
        "",
        f"**Highest CAGR:** {by_cagr[0][0]} — {by_cagr[0][3]['cagr']*100:.1f}% (Ulcer {by_cagr[0][3]['ulcer']*100:.1f}%)",
        f"**Highest Martin:** {by_martin[0][0]} — Martin {by_martin[0][3]['martin']:.2f} (CAGR {by_martin[0][3]['cagr']*100:.1f}%, Ulcer {by_martin[0][3]['ulcer']*100:.1f}%)",
        f"**Lowest Ulcer:** {by_ulcer[0][0]} — Ulcer {by_ulcer[0][3]['ulcer']*100:.1f}% (CAGR {by_ulcer[0][3]['cagr']*100:.1f}%)",
        "",
        "## Mechanism reads",
        "",
    ]

    # Compute deltas vs baseline for mechanism reads
    base_metrics = next((m for n, _, _, m in results if n == "baseline"), None)
    if base_metrics:
        for name, hyp, _, m in results:
            if name == "baseline":
                continue
            d_cagr = (m["cagr"] - base_metrics["cagr"]) * 100
            d_martin = m["martin"] - base_metrics["martin"]
            d_ulcer = (m["ulcer"] - base_metrics["ulcer"]) * 100
            lines.append(
                f"- **{name}**: ΔCAGR {d_cagr:+.1f}pp, ΔMartin {d_martin:+.2f}, ΔUlcer {d_ulcer:+.1f}pp — *{hyp[:70]}*"
            )

    SUMMARY.write_text("\n".join(lines))
    print(f"\nSummary → {SUMMARY}")
    print(f"Log    → {LOG}")


if __name__ == "__main__":
    main()
