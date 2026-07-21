"""Show the strategy's picks AS OF a historical date (no look-ahead)."""

from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO / "india" / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from invest.autoresearch import (  # noqa: E402
    Strategy, _compute_scores, _topk_from_scores, _build_exclude_mask,
)
from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402
from fetch_etf_data import fetch_yfinance  # noqa: E402

HERE = Path(__file__).resolve().parent
STRATEGY_PATH = HERE / "strategy.json"


def load_panel(period="max"):
    keys = list(AI_INFRA_UNIVERSE.keys())
    series, fetched = [], []
    for k in keys:
        df = fetch_yfinance(AI_INFRA_UNIVERSE[k][1], period)
        if df is None or "close" not in df.columns or len(df) < 200:
            continue
        series.append((k, df["date"].to_numpy(), df["close"].to_numpy()))
        fetched.append(k)
    all_dates = sorted({d for _, dts, _ in series for d in dts.tolist()})
    common = np.array(all_dates)
    idx = {d: i for i, d in enumerate(common)}
    prices = np.full((len(common), len(series)), np.nan)
    for j, (_, dts, p) in enumerate(series):
        for d, v in zip(dts, p):
            prices[idx[d], j] = v
    return prices, fetched, common


def main():
    if len(sys.argv) < 2:
        print("usage: snapshot_at_date.py YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)
    target = sys.argv[1]
    raw = json.loads(STRATEGY_PATH.read_text())
    strat = Strategy.from_dict(raw)
    prices, fetched, dates = load_panel("max")
    # Find the index of the closest date <= target (no look-ahead)
    target_arr = np.array(dates, dtype="datetime64[D]")
    target_dt = np.datetime64(target, "D")
    valid = np.where(target_arr <= target_dt)[0]
    if len(valid) == 0:
        print(f"No data on or before {target}", file=sys.stderr)
        sys.exit(2)
    cur_idx = valid[-1]
    actual_date = dates[cur_idx]
    print(f"Snapshot at {actual_date} (idx={cur_idx})")
    print(f"Strategy: variant={strat.score_variant} n={strat.n_positions} "
          f"hmm_states={strat.hmm_states} hmm_profile={strat.hmm_profile}")

    # Use only data available up to cur_idx
    win_depth = max(252, max(strat.lookbacks) + strat.skip_days + 5)
    window = prices[max(0, cur_idx - win_depth):cur_idx + 1, :]
    exclude = _build_exclude_mask(fetched)
    scores = _compute_scores(window, strat.lookbacks, strat.weights,
                              strat.skip_days, strat.score_variant,
                              exclude_mask=exclude)
    topk = _topk_from_scores(scores, strat.n_positions)
    if len(topk) == 0:
        print("No qualifying picks (insufficient history)")
        return
    print(f"\nTop {strat.n_positions} picks (sortino_vnorm score):")
    print(f"{'#':>3} {'ticker':14s} {'theme':22s} {'score':>10s}")
    print("-" * 55)
    for rank, idx in enumerate(topk, 1):
        ticker = fetched[idx]
        theme = AI_INFRA_UNIVERSE[ticker][3]
        sc = float(scores[idx])
        print(f"{rank:>3} {ticker:14s} {theme:22s} {sc:>10.3f}")


if __name__ == "__main__":
    main()
