"""
Autoresearch evaluator — runs backtest and extracts key metrics.

Wraps us/scripts/backtest.py for both US and India markets, captures output,
and prints machine-readable summaries (like autoresearch train.py does for val_bpb).

Usage:
    uv run evaluate.py                          # Run both US + India
    uv run evaluate.py --market us              # US only
    uv run evaluate.py --market india           # India only
    uv run evaluate.py --period 5y --workers 8  # Custom params
"""

import subprocess
import re
import sys
import time


def extract_metrics(output: str) -> dict:
    """Extract key metrics from backtest Rich output (strip ANSI codes)."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)

    metrics = {
        "best_calmar": 0.0,
        "best_upi": 0.0,
        "best_abs_ret_pct": 0.0,
        "best_sortino": 0.0,
        "n_survivable": 0,
        "worst_dd_pct": 0.0,
        "ulcer_index": 0.0,
        "n_combos": 0,
        "n_folds": 0,
        "median_oos_pct": 0.0,
    }

    # "Survivable (DD≤50%): 3400/12000"
    m = re.search(r"Survivable.*?:\s*(\d+)/(\d+)", clean)
    if m:
        metrics["n_survivable"] = int(m.group(1))
        metrics["n_combos"] = int(m.group(2))

    # "combos=12000  folds=8"
    m = re.search(r"folds=(\d+)", clean)
    if m:
        metrics["n_folds"] = int(m.group(1))

    # "OOS return — best: +120.5%  median: +42.3%  worst: -30.1%"
    m = re.search(r"median:\s*([+\-]?\d+\.?\d*)%", clean)
    if m:
        metrics["median_oos_pct"] = float(m.group(1))

    m = re.search(r"best:\s*([+\-]?\d+\.?\d*)%", clean)
    if m:
        metrics["best_abs_ret_pct"] = float(m.group(1))

    # Parse RISK TIERS for ≤50% row
    for line in clean.split("\n"):
        if "≤50%" in line or "<=50%" in line:
            nums = re.findall(r"[+\-]?\d+\.?\d*", line)
            if len(nums) >= 7:
                # Max DD tier | # Combos | Best Ann. | Calmar | UPI | Ulcer | Sortino | Win%
                metrics["best_calmar"] = max(metrics["best_calmar"], float(nums[3]))
                metrics["best_upi"] = max(metrics["best_upi"], float(nums[4]))
                metrics["ulcer_index"] = float(nums[5])
                metrics["best_sortino"] = max(metrics["best_sortino"], float(nums[6]))

    # Parse BEST UPI table (first data row)
    lines = clean.split("\n")
    in_upi = False
    for line in lines:
        if "BEST UPI" in line:
            in_upi = True
            continue
        if in_upi and re.match(r"\s*1\s", line):
            nums = re.findall(r"[+\-]?\d+\.?\d*", line)
            if len(nums) >= 6:
                # Parse: # | ret | ann | dd | calmar | upi | ulcer | sortino | win | pos
                if metrics["best_upi"] == 0:
                    metrics["best_upi"] = float(nums[4])
                if metrics["ulcer_index"] == 0:
                    metrics["ulcer_index"] = float(nums[5])
            break

    return metrics


def run_market(market: str, period: str, workers: str, top: str) -> tuple[dict, float, str]:
    """Run backtest for one market. Returns (metrics, elapsed, log_content)."""
    cmd = [
        "uv", "run", "python", "us/scripts/backtest.py",
        "--top", top, "--period", period, "--workers", workers,
        "--market", market,
    ]

    print(f"\n{'='*60}")
    print(f"Running {market.upper()}: {' '.join(cmd)}")
    print(f"{'='*60}")
    t0 = time.time()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=1200,  # 20 min hard timeout
    )

    elapsed = time.time() - t0
    log_content = result.stdout
    if result.stderr:
        log_content += "\n--- STDERR ---\n" + result.stderr

    # Write full output to market-specific log
    log_file = f"run_{market}.log"
    with open(log_file, "w") as f:
        f.write(log_content)

    if result.returncode != 0:
        print(f"CRASH (exit code {result.returncode})")
        print(f"stderr tail: {result.stderr[-500:]}")
        return {}, elapsed, log_content

    metrics = extract_metrics(result.stdout)
    return metrics, elapsed, log_content


def main():
    period = "5y"
    workers = "8"
    top = "5"
    markets = ["us", "india"]

    # Parse args
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--period" and i + 1 < len(args):
            period = args[i + 1]
            i += 2
        elif args[i] == "--workers" and i + 1 < len(args):
            workers = args[i + 1]
            i += 2
        elif args[i] == "--top" and i + 1 < len(args):
            top = args[i + 1]
            i += 2
        elif args[i] == "--market" and i + 1 < len(args):
            markets = [args[i + 1]]
            i += 2
        else:
            i += 1

    for market in markets:
        metrics, elapsed, _ = run_market(market, period, workers, top)
        if not metrics:
            print(f"\n--- {market.upper()} CRASHED ---")
            continue

        tax_label = "21% C-Corp" if market == "us" else "20% STCG"
        print(f"\n--- {market.upper()} (after {tax_label} tax) ---")
        print(f"best_abs_ret_pct: {metrics['best_abs_ret_pct']:.1f}")
        print(f"best_calmar:      {metrics['best_calmar']:.4f}")
        print(f"best_upi:         {metrics['best_upi']:.4f}")
        print(f"ulcer_index:      {metrics['ulcer_index']:.1f}")
        print(f"best_sortino:     {metrics['best_sortino']:.4f}")
        print(f"n_survivable:     {metrics['n_survivable']}")
        print(f"worst_dd_pct:     {metrics['worst_dd_pct']:.1f}")
        print(f"n_combos:         {metrics['n_combos']}")
        print(f"n_folds:          {metrics['n_folds']}")
        print(f"median_oos_pct:   {metrics['median_oos_pct']:.1f}")
        print(f"elapsed_seconds:  {elapsed:.1f}")


if __name__ == "__main__":
    main()
