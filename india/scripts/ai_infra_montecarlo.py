"""
Monte Carlo regime sweep on AI-infra universe — autoresearch-style.

Compares 4 regimes by bootstrap MC over 3y daily returns:
  - winner   : walk-forward winner (MCX/BHARATFORG/MTARTECH/CUMMINSIND)
  - top10_eq : top-10 momentum names equal-weight
  - all92_eq : full universe equal-weight (naive benchmark)
  - themes   : theme-balanced concentrated basket

Run: uv run python india/scripts/ai_infra_montecarlo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402

CAPITAL = 2_500_000
HORIZONS = {"3M": 63, "6M": 126, "12M": 252}
N_SIMS = 10_000
SEED = 42

WINNER = {"MCX": 0.349, "BHARATFORG": 0.20, "MTARTECH": 0.199, "CUMMINSIND": 0.148}
TOP10 = ["MTARTECH", "MCX", "KIRLOSENG", "CUMMINSIND", "BHARATFORG",
         "STLTECH", "POWERINDIA", "APARINDS", "ONGC", "KEI"]

REGIMES = {
    "winner":   WINNER,
    "top10_eq": {k: 1 / 10 for k in TOP10},
    "all92_eq": {k: 1 / len(AI_INFRA_UNIVERSE) for k in AI_INFRA_UNIVERSE},
    "themes": {
        "MTARTECH": 0.15, "MCX": 0.15, "STLTECH": 0.10, "POWERINDIA": 0.10,
        "APARINDS": 0.10, "BHARATFORG": 0.10, "CUMMINSIND": 0.10,
        "KEI": 0.05, "ADANIPOWER": 0.05, "NETWEB": 0.05, "BSE": 0.05,
    },
}


def fetch_returns(tickers: list[str], period: str = "3y"):
    """Fetch each ticker individually so a single bad symbol doesn't poison the batch."""
    import pandas as pd

    yf_tickers = [AI_INFRA_UNIVERSE[k][1] for k in tickers]
    series_list = []
    fetched = []
    for yt in yf_tickers:
        try:
            hist = yf.Ticker(yt).history(period=period, auto_adjust=True)
            if hist.empty or "Close" not in hist.columns:
                continue
            s = hist["Close"].rename(yt)
            series_list.append(s)
            fetched.append(yt)
        except Exception:
            continue
    if not series_list:
        return np.array([]).reshape(0, 0), []
    df = pd.concat(series_list, axis=1).ffill().dropna()
    rets = df.pct_change().dropna().to_numpy()
    return rets, list(df.columns)


def bootstrap(rets, weights, days, n_sims, seed=SEED):
    rng = np.random.default_rng(seed)
    n_hist = rets.shape[0]
    p_rets = rets @ weights
    idx = rng.integers(0, n_hist, size=(n_sims, days))
    sampled = p_rets[idx]
    paths = np.cumprod(1.0 + sampled, axis=1)
    cum = paths[:, -1] - 1.0
    rmax = np.maximum.accumulate(paths, axis=1)
    dd = ((paths - rmax) / rmax).min(axis=1)
    return cum, dd


def fmt(x):
    return f"{x * 100:+.1f}%"


def run_regime(name, basket):
    tickers = list(basket.keys())
    weights = np.array([basket[t] for t in tickers])
    rets, fetched = fetch_returns(tickers)
    keep = [i for i, t in enumerate(tickers) if AI_INFRA_UNIVERSE[t][1] in fetched]
    tickers = [tickers[i] for i in keep]
    weights = weights[keep]
    weights = weights / weights.sum()

    p_rets = rets @ weights
    ann_ret = (1 + p_rets.mean()) ** 252 - 1
    ann_vol = p_rets.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    neg = p_rets[p_rets < 0]
    dn_vol = neg.std() * np.sqrt(252) if len(neg) else 1e-4
    sortino = ann_ret / dn_vol if dn_vol > 0 else 0

    rows = {}
    for label, days in HORIZONS.items():
        ret, dd = bootstrap(rets, weights, days, N_SIMS)
        p = np.percentile(ret, [5, 25, 50, 75, 95])
        rows[label] = {
            "p5": p[0], "p25": p[1], "p50": p[2], "p75": p[3], "p95": p[4],
            "dd_wst": float(np.percentile(dd, 5)),
            "p_big_loss": float(np.mean(ret < -0.20)),
            "p_loss": float(np.mean(ret < 0)),
        }
    return ann_ret, sharpe, sortino, rows, len(tickers), rets.shape[0]


def main():
    print(f"\n{'=' * 110}")
    print(f"AI-Infra Monte Carlo regime sweep — autoresearch-style")
    print(f"  Capital ₹{CAPITAL:,}  |  {N_SIMS} sims  |  3y bootstrap  |  seed {SEED}")
    print(f"{'=' * 110}")

    summary = {}
    for name, basket in REGIMES.items():
        ann, sh, so, rows, n, days = run_regime(name, basket)
        summary[name] = (ann, sh, so, rows, n, days)
        print(f"  [{name:10s}] {n:3d} names, {days}d hist, "
              f"Ann={fmt(ann)}  Sharpe={sh:.2f}  Sortino={so:.2f}")

    print(f"\n{'=' * 110}")
    print(f"REGIME COMPARISON — 12M bootstrap MC outcomes")
    print(f"{'=' * 110}")
    print(f"{'Regime':10s} {'Ann':>7s} {'Sh':>5s} {'So':>5s}  "
          f"{'P5':>8s} {'P25':>8s} {'Med':>8s} {'P75':>8s} {'P95':>8s}  "
          f"{'DD wst':>7s} {'P(loss)':>8s} {'P(<-20)':>8s}")
    print("-" * 110)
    for name, (ann, sh, so, rows, _, _) in summary.items():
        r = rows["12M"]
        print(
            f"{name:10s} {fmt(ann):>7s} {sh:>5.2f} {so:>5.2f}  "
            f"{fmt(r['p5']):>8s} {fmt(r['p25']):>8s} {fmt(r['p50']):>8s} "
            f"{fmt(r['p75']):>8s} {fmt(r['p95']):>8s}  "
            f"{fmt(r['dd_wst']):>7s} {r['p_loss']*100:>7.1f}% {r['p_big_loss']*100:>7.1f}%"
        )

    # Per-horizon for winner
    print(f"\nPer-horizon (winner regime):")
    print(f"{'Horizon':8s} {'P5':>8s} {'Med':>8s} {'P95':>8s}  {'DD wst':>8s} {'P(loss)':>8s}")
    for label in HORIZONS:
        r = summary["winner"][3][label]
        print(f"{label:8s} {fmt(r['p5']):>8s} {fmt(r['p50']):>8s} {fmt(r['p95']):>8s}  "
              f"{fmt(r['dd_wst']):>8s} {r['p_loss']*100:>7.1f}%")

    # Capital outcome — winner only
    print(f"\n12M capital outcome on ₹{CAPITAL:,} — winner regime:")
    r = summary["winner"][3]["12M"]
    for tag, key in [("P5 (bad)", "p5"), ("Median", "p50"), ("P95 (good)", "p95")]:
        v = (1 + r[key]) * CAPITAL
        print(f"  {tag:12s} ₹{v:>14,.0f}")


if __name__ == "__main__":
    main()
