"""
Single-shot experiment runner for the Karpathy-mode autoresearch loop.

Reads `strategy.json`, runs walk-forward backtest + stress MC + composite scoring
on the cached price data, and appends one line to `history.jsonl`.

The agent (claude/codex) edits strategy.json between calls; this script never does.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO / "india" / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from invest.autoresearch import (  # noqa: E402
    Strategy, composite, current_picks, load_crash_calibration, stress_mc,
    walk_forward,
)
from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402
from fetch_etf_data import fetch_yfinance  # noqa: E402

HERE = Path(__file__).resolve().parent
STRATEGY_PATH = HERE / "strategy.json"
HISTORY_PATH = HERE / "history.jsonl"
WINNER_PATH = HERE / "WINNER.json"
CRASH_JSON = REPO / "india" / "data" / "em_crash_scenarios.json"

# Universe panel cache — loaded once per process; the agent re-spawns each call
# so this is effectively cached on disk via fetch_etf_data's daily_disk_cache.
def _load_panel_legacy(period: str = "max"):
    keys = list(AI_INFRA_UNIVERSE.keys())
    series = []
    fetched = []
    for k in keys:
        df = fetch_yfinance(AI_INFRA_UNIVERSE[k][1], period)
        if df is None or "close" not in df.columns or len(df) < 200:
            continue
        series.append((k, df["date"].to_numpy(), df["close"].to_numpy()))
        fetched.append(k)
    if not series:
        raise RuntimeError("no data")
    all_dates = sorted({d for _, dts, _ in series for d in dts.tolist()})
    common = np.array(all_dates)
    idx = {d: i for i, d in enumerate(common)}
    prices = np.full((len(common), len(series)), np.nan)
    for j, (_, dts, p) in enumerate(series):
        for d, v in zip(dts, p):
            prices[idx[d], j] = v
    return prices, fetched, common


def main():
    if not STRATEGY_PATH.exists():
        print(f"ERROR: {STRATEGY_PATH} missing — write a strategy.json first.",
              file=sys.stderr)
        sys.exit(2)

    raw = json.loads(STRATEGY_PATH.read_text())
    strat = Strategy.from_dict(raw)

    # Use the corrected loader (auto-fixes corp-action holes like GOLDBEES 2019)
    from ai_infra_autoresearch import fetch_universe
    prices, fetched, _ = fetch_universe("max")
    daily_rets = np.diff(prices, axis=0) / prices[:-1, :]
    daily_rets = np.nan_to_num(daily_rets, nan=0.0, posinf=0.0, neginf=0.0)
    calib = load_crash_calibration(CRASH_JSON)

    from invest.autoresearch import _build_exclude_mask
    cash_idx = fetched.index("LIQUIDBEES") if "LIQUIDBEES" in fetched else -1
    exclude = _build_exclude_mask(fetched)
    bt = walk_forward(prices, strat, cash_idx=cash_idx, exclude_mask=exclude)
    picks = current_picks(prices, fetched, strat)

    if picks and bt["rebal_count"] >= 3:
        pick_idx = [fetched.index(p) for p in picks]
        w = np.ones(len(pick_idx)) / len(pick_idx)
        sub_rets = daily_rets[:, pick_idx]
        mc = stress_mc(sub_rets, w, days=252, n_sims=2000,
                        calib=calib, p_mult=strat.crash_p_mult)
    else:
        mc = {"p5": 0, "p25": 0, "p50": 0, "p75": 0, "p95": 0,
              "dd_wst": 0, "p_loss": 0, "p_dd_30": 0, "p_dd_50": 0}

    score = composite(bt, mc)
    rec = {
        "ts": time.time(),
        "strategy": strat.to_dict(),
        "backtest": bt,
        "mc12m": mc,
        "score": float(score),
        "picks": picks,
    }
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(rec) + "\n")

    # Concise summary to stdout for the agent
    summary = {
        "score": round(score, 3),
        "pain_ratio": round(bt.get("pain_ratio", 0), 2),
        "cagr": round(bt.get("cagr", 0), 3),
        "max_dd": round(bt.get("max_dd", 0), 3),
        "max_dd_dur_months": round(bt.get("max_dd_dur_months", 0), 1),
        "avg_dd_dur_months": round(bt.get("avg_dd_dur_months", 0), 2),
        "rebal_count": bt.get("rebal_count", 0),
        "p_dd_30": round(mc.get("p_dd_30", 0), 3),
        "p_dd_50": round(mc.get("p_dd_50", 0), 3),
        "picks": picks,
    }
    print(json.dumps(summary, indent=2))

    # Stop-condition check
    target_met = (
        bt.get("pain_ratio", 0) >= 8.0
        and bt.get("max_dd_dur_months", 99) <= 20
        and bt.get("cagr", 0) >= 0.30
        and bt.get("rebal_count", 0) >= 30
    )
    if target_met:
        WINNER_PATH.write_text(json.dumps(rec, indent=2))
        print("\n*** TARGET MET — see WINNER.json ***", file=sys.stderr)


if __name__ == "__main__":
    main()
