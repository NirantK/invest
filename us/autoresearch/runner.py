"""
Single-experiment runner for autoresearch.

Runs ONE backtest with the score function from `score.py`, captures metrics,
appends to experiments.jsonl, and decides keep/revert per program.md rules.

Usage:
    uv run python us/autoresearch/runner.py --hypothesis "Description" \
        --score-col score_martin --sizing sqrt --rebal 63

The agent is expected to:
    1. Modify score.py
    2. Call this runner with a clear hypothesis description
    3. Read experiments.jsonl to compare against current best
    4. Either git commit (kept) or git checkout score.py (reverted)
"""

import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
LOG = HERE / "experiments.jsonl"
BEST = HERE / "best.md"


def _load_history() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]


def _current_best(history: list[dict]) -> dict | None:
    kept = [h for h in history if h.get("kept")]
    if not kept:
        return None
    return max(kept, key=lambda h: h["metrics"]["martin"])


def _git_diff_score() -> str:
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", str(HERE / "score.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    return result.stdout[:2000]


@click.command()
@click.option("--hypothesis", required=True, help="One-sentence rationale for this experiment.")
@click.option("--score-col", default="score_martin",
              type=click.Choice(["score", "score_martin", "score_sortino", "score_rank"]))
@click.option("--sizing", default="sqrt", type=click.Choice(["raw", "sqrt", "equal"]))
@click.option("--rebal", default=63, type=int, help="Rebalance days (21=monthly, 63=quarterly, 126=semi).")
@click.option("--auto-decide/--no-auto-decide", default=True,
              help="Apply program.md keep/revert rules automatically.")
def main(hypothesis: str, score_col: str, sizing: str, rebal: int, auto_decide: bool):
    history = _load_history()
    baseline = _current_best(history)

    print(f"Hypothesis: {hypothesis}")
    print(f"Config: score_col={score_col}, sizing={sizing}, rebal={rebal}d")
    if baseline:
        print(f"Baseline: Martin={baseline['metrics']['martin']:.2f} "
              f"(from iter {baseline.get('iteration', '?')})")

    # Run the backtest using the canonical harness (it imports from score.py automatically
    # since score.py re-exports from the production module).
    sys.path.insert(0, str(ROOT / "us" / "scripts"))
    from backtest_v2 import run_backtest, fetch_total_return_index  # type: ignore
    from us_portfolio_allocation import TICKERS  # type: ignore

    print("Fetching data...")
    prices, closes, dvols = fetch_total_return_index(TICKERS, period="3y")
    print(f"  {len(prices.columns) - 1} tickers, {len(prices)} days")

    print("Running backtest...")
    result = run_backtest(prices, closes, dvols, score_col, sizing, rebal)

    metrics = {
        "cagr": result.cagr, "sharpe": result.sharpe, "martin": result.martin,
        "ulcer": result.ulcer, "max_dd": result.max_dd, "total_return": result.total_return,
        "avg_positions": result.avg_positions, "n_rebalances": result.n_rebalances,
    }
    print(f"  CAGR={metrics['cagr']*100:.1f}%  Martin={metrics['martin']:.2f}  "
          f"Ulcer={metrics['ulcer']*100:.1f}%  MaxDD={metrics['max_dd']*100:.0f}%")

    # Decide
    kept = False
    decision_reason = ""
    if auto_decide:
        if baseline is None:
            kept = True
            decision_reason = "no baseline yet"
        else:
            d_martin = metrics["martin"] - baseline["metrics"]["martin"]
            d_ulcer = metrics["ulcer"] - baseline["metrics"]["ulcer"]
            if d_martin >= 0.20:
                kept = True
                decision_reason = f"Δmartin={d_martin:+.2f} (big win)"
            elif d_martin >= 0.05 and d_ulcer <= 0.005:
                kept = True
                decision_reason = f"Δmartin={d_martin:+.2f}, Δulcer={d_ulcer*100:+.1f}bps"
            elif d_martin < -0.05 or d_ulcer > 0.02:
                kept = False
                decision_reason = f"reverted: Δmartin={d_martin:+.2f}, Δulcer={d_ulcer*100:+.1f}bps"
            else:
                kept = False
                decision_reason = f"inconclusive: Δmartin={d_martin:+.2f}"
    print(f"Decision: {'KEEP' if kept else 'REVERT'} — {decision_reason}")

    entry = {
        "iteration": len(history) + 1,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "hypothesis": hypothesis,
        "diff_summary": _git_diff_score()[:500],
        "config": {"score_col": score_col, "sizing": sizing, "rebal_days": rebal},
        "metrics": metrics,
        "kept": kept,
        "decision_reason": decision_reason,
    }
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Logged to {LOG}")

    if kept:
        new_best = entry
        BEST.write_text(
            f"# Current Best — Iteration {new_best['iteration']}\n\n"
            f"**Hypothesis:** {new_best['hypothesis']}\n\n"
            f"**Config:** {new_best['config']}\n\n"
            f"**Metrics:**\n"
            f"- CAGR: {metrics['cagr']*100:.1f}%\n"
            f"- Martin Ratio: **{metrics['martin']:.2f}**\n"
            f"- Ulcer Index: {metrics['ulcer']*100:.1f}%\n"
            f"- Max Drawdown: {metrics['max_dd']*100:.0f}%\n"
            f"- Sharpe: {metrics['sharpe']:.2f}\n\n"
            f"**Logged at:** {new_best['timestamp']}\n"
        )
        print(f"Updated {BEST}")
        # commit happens externally — agent does git add/commit per program.md


if __name__ == "__main__":
    main()
