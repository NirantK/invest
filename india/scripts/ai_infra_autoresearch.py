"""
India AI-Infra autoresearch wrapper — thin shim over invest.autoresearch.

Universe lives in ai_infra_universe.py. The loop, scoring, MC, samplers all
live in src/invest/autoresearch.py and are shared with the US side.

Usage:
  uv run python india/scripts/ai_infra_autoresearch.py --iters 500 --period max
  uv run python india/scripts/ai_infra_autoresearch.py --iters 5000 --karpathy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402
from fetch_etf_data import fetch_yfinance  # noqa: E402

from invest.autoresearch import load_crash_calibration, run_loop
from invest.karpathy import make_callback

DATA_DIR = Path(__file__).parent.parent / "data"
CRASH_JSON = DATA_DIR / "em_crash_scenarios.json"


def _paths(tag: str | None):
    suffix = f"_{tag}" if tag else ""
    return (DATA_DIR / f"research_log{suffix}.jsonl",
            DATA_DIR / f"research_best{suffix}.json",
            DATA_DIR / f"karpathy_proposals{suffix}.jsonl")


def _correct_corp_action_jumps(p: np.ndarray, jump_threshold: float = 2.0) -> np.ndarray:
    """Anchor on the most recent price (assume today's value is canonical).
    Walk backwards: any day where the next-day move is > +threshold or
    < -1/(1+threshold) is a yfinance corp-action miss. Multiply all PRIOR
    prices by the jump ratio so the series becomes continuous.

    Direction matters: yfinance often shows correct CURRENT price + scaled-down
    HISTORICAL prices (failed back-adjust). So we trust the present, scale the
    past upward.
    """
    p = p.copy().astype(np.float64)
    if len(p) < 3:
        return p
    # Walk from most recent backwards
    for _ in range(20):  # cap iterations
        rets = np.diff(p) / p[:-1]
        bad_up = np.where(rets > jump_threshold)[0]
        bad_down = np.where(rets < -(1 - 1 / (1 + jump_threshold)))[0]
        bad = sorted(set(bad_up.tolist() + bad_down.tolist()))
        if not bad:
            break
        i = bad[-1]  # most-recent bad jump
        if i + 1 >= len(p):
            break
        ratio = p[i + 1] / p[i]
        if not (np.isfinite(ratio) and ratio > 0):
            break
        # Multiply everything BEFORE i+1 by ratio so the series joins smoothly
        p[: i + 1] = p[: i + 1] * ratio
    return p


GENKA_DIR = Path(__file__).parent.parent / "data" / "genka_prices"


def _load_one_ticker(ticker_key: str, yf_ticker: str, period: str):
    """Prefer genka_prices/{TICKER}.parquet (clean adj_close, corp-actions handled).
    Fall back to yfinance + back-adjust for tickers genka doesn't cover.
    Returns (dates_array, prices_array) or None if no data.
    """
    nse_sym = yf_ticker.replace(".NS", "").replace(".BO", "")
    gpath = GENKA_DIR / f"{nse_sym}.parquet"
    if gpath.exists():
        import polars as pl
        df = pl.read_parquet(gpath).sort("date")
        # HINDZINC has 3.5y gap pre-2006 — drop early bars (per sub-agent note)
        if nse_sym == "HINDZINC":
            df = df.filter(pl.col("date") >= "2006-11-21")
        if len(df) < 200:
            return None
        return df["date"].to_numpy(), df["adj_close"].to_numpy()
    # Fallback to yfinance
    df = fetch_yfinance(yf_ticker, period)
    if df is None or "close" not in df.columns or len(df) < 200:
        return None
    p = _correct_corp_action_jumps(df["close"].to_numpy())
    return df["date"].to_numpy(), p


def fetch_universe(period: str = "3y"):
    """Union-of-dates panel. Prefers genka clean prices, falls back to yfinance
    with auto corp-action correction."""
    keys = list(AI_INFRA_UNIVERSE.keys())
    series = []
    fetched = []
    for k in keys:
        out = _load_one_ticker(k, AI_INFRA_UNIVERSE[k][1], period)
        if out is None:
            continue
        dts, p = out
        series.append((k, dts, p))
        fetched.append(k)
    if not series:
        raise RuntimeError("No data fetched")
    all_dates = set()
    for _, dts, _ in series:
        all_dates.update(dts.tolist())
    common = np.array(sorted(all_dates))
    date_to_idx = {d: i for i, d in enumerate(common)}
    prices = np.full((len(common), len(series)), np.nan)
    for j, (_, dts, p) in enumerate(series):
        for d, v in zip(dts, p):
            prices[date_to_idx[d], j] = v
    return prices, fetched, common


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--period", default="3y")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--print-every", type=int, default=25)
    ap.add_argument("--karpathy", action="store_true",
                    help="enable claude-in-loop strategy proposals")
    ap.add_argument("--batch", type=int, default=50,
                    help="iters per karpathy batch (only when --karpathy)")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--tag", default=None,
                    help="output suffix; lets multiple parallel runs coexist")
    args = ap.parse_args()
    LOG_PATH, BEST_PATH, PROPOSAL_LOG = _paths(args.tag)

    print(f"[ai-infra] fetching universe ({args.period})...")
    prices, fetched, dates = fetch_universe(args.period)
    print(f"  {prices.shape[0]} days × {prices.shape[1]} tickers")

    calib = load_crash_calibration(CRASH_JSON)
    print(f"  crash calibration buckets: {list(calib.keys())}")

    # Optional macro features for HMM
    macro_features = None
    try:
        from macro_pipeline import get_macro_features
        macro_features = get_macro_features(dates)
        print(f"  macro features: {macro_features.shape} (FII/vol/microstructure/concall)")
    except Exception as e:
        print(f"  macro features: unavailable ({e})")

    callback = None
    batch_size = 0
    if args.karpathy:
        PROPOSAL_LOG.unlink(missing_ok=True)
        callback = make_callback(model=args.model, proposal_log=PROPOSAL_LOG)
        batch_size = args.batch
        print(f"  karpathy mode ON  (model={args.model}, batch={args.batch})")

    best = run_loop(
        prices=prices, fetched=fetched, dates=dates, calib=calib,
        n_iters=args.iters, log_path=LOG_PATH, best_path=BEST_PATH,
        seed=args.seed, print_every=args.print_every,
        batch_callback=callback, batch_size=batch_size,
        macro_features=macro_features,
    )

    print(f"\n=== FINAL BEST ===")
    s = best["strategy"]
    print(f"strategy: {s.to_dict() if hasattr(s, 'to_dict') else s}")
    print(f"backtest: {best['backtest']}")
    print(f"mc12m:    {best['mc12m']}")
    print(f"score:    {best['score']:.3f}")
    print(f"picks:    {best['picks']}")
    print(f"\nLog:        {LOG_PATH}")
    print(f"Best:       {BEST_PATH}")
    if args.karpathy:
        print(f"Proposals:  {PROPOSAL_LOG}")


if __name__ == "__main__":
    main()
