# Autoresearch Program: Portfolio Score Function Optimization

You are an autonomous research agent inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — but for portfolio construction, not LLM training.

## The Goal

**Maximize Martin Ratio** of the V2 momentum portfolio on a walk-forward backtest. Martin Ratio = CAGR / Ulcer Index. Returns per unit of pain — the user can take more risk for more return, but **does not eat risk-adjusted returns by Sharpe**. Pain matters; squiggle does not.

## What You Modify

You edit ONE file: `score.py` (in this directory). It exposes:

- `score_function(ticker, prices, returns, closes, dvols) -> dict` — produces per-ticker metrics
- `composite(scores_df) -> pl.DataFrame` — produces the composite score column the allocator uses
- `sizing(score_dict, mode) -> dict` — produces position weights from scores

**Everything is fair game**: signal mix, weights, transformations, lookback windows, novel signals (volume MFI, OBV, relative strength rank, sector momentum, breadth, regime filters, fundamental overlays, anything you can think of).

You may NOT modify:
- The TICKER universe (`us/scripts/us_portfolio_allocation.py:TICKERS`) — that's the canvas
- The walk-forward harness (`us/scripts/backtest_v2.py`) — that's the judge
- The Martin Ratio metric — that's the goal

## Protocol

For each iteration:

1. **Hypothesis.** State in one paragraph what you're trying and why. Cite a source (paper, fintwit, Alpha Architect, AQR) if applicable.
2. **Edit `score.py`.** Make ONE focused change. No giant rewrites.
3. **Run.** `uv run python us/scripts/backtest_v2.py --score-fn-from us/autoresearch/score.py` (single config, fastest signal).
4. **Read result.** Look at Martin, Ulcer, CAGR, MaxDD. The number to beat is the previous best.
5. **Log.** Append to `experiments.jsonl` with: timestamp, hypothesis, diff, metrics, kept-or-reverted.
6. **Decide.** If Martin improved AND Ulcer didn't get materially worse → keep. Else → revert to last best `score.py`.
7. **Iterate.** Move to next hypothesis. Up to 50 iterations per session.

## Constraints

- **Do not optimize for Sharpe.** The user explicitly rejected Sharpe. Optimize for Martin.
- **Do not overfit to 1Y.** Use 3Y walk-forward. If a change only helps recent months, skip it.
- **Avoid look-ahead.** Score function may only use data up to the rebalance date.
- **No synthetic returns.** Real ticker price+volume from yfinance only.
- **Keep it simple.** A 1-line change that improves Martin 0.05 beats a 100-line change that improves it 0.10 — fewer ways for it to break in production.
- **Be skeptical of small gains.** Δ Martin < 0.05 is noise. Don't keep changes below that.

## Hypotheses to Try (Starting Backlog)

P0 — Things to test first (highest expected lift):
- [ ] Replace 0.2/0.4/0.4 momentum weights with 0.4/0.3/0.3 (more recency)
- [ ] Add Money Flow Index (MFI-14) as volume confirmation signal
- [ ] Replace `dist52` with rolling-3M high distance (faster signal)
- [ ] Add `score = score × (1 - 0.5*current_dd)` — penalty for any current drawdown
- [ ] Use `sqrt(score) * sqrt(1/ulcer_1y)` for sizing (vol-parity hybrid)
- [ ] Cross-sectional z-score instead of percentile rank for `score_rank`

P1 — Worth testing:
- [ ] Earnings momentum overlay (`build_earnings_momentum` exists but isn't wired)
- [ ] Sector relative-strength rank (z-score within sleeve)
- [ ] Breakout signal: price > 50DMA × volume > 2× 20-day-avg
- [ ] OBV trend over 60 days as separate signal
- [ ] Trend-quality regime gate: skip allocation when SPY 200DMA below 100DMA

P2 — Speculative:
- [ ] Insider-buying scrape from Form 4 (high effort)
- [ ] 13F change tracker (Leo / Citrini / hedge funds)
- [ ] News sentiment via cheap LLM
- [ ] Cross-asset signals (DXY, VIX, term structure)

## Metrics to Track Per Iteration

```json
{
  "timestamp": "2026-05-09T08:00:00",
  "hypothesis": "Add MFI-14 to score",
  "diff_summary": "Added 14-day Money Flow Index, multiplied score by (mfi/50)^0.5",
  "config": {"score_col": "score", "sizing": "sqrt", "rebal_days": 21},
  "metrics": {"cagr": 0.452, "martin": 5.21, "ulcer": 0.087, "max_dd": -0.18, "sharpe": 1.92},
  "vs_baseline": {"martin_delta": 0.34, "ulcer_delta": -0.005, "kept": true}
}
```

## Decision Rules

- **Keep** if Δ Martin ≥ +0.05 AND Δ Ulcer ≤ +0.005 (5bps tolerance)
- **Keep** if Δ Martin ≥ +0.20 (regardless of ulcer — big gain wins)
- **Revert** if Δ Martin < -0.05 OR Δ Ulcer > +0.02
- **Inconclusive** otherwise → don't keep, but record the experiment

## When to Stop

- 50 iterations elapsed
- 5 consecutive reverts (signal you're hill-climbing a local max)
- Martin ratio > 6.0 achieved (extraordinary, worth manual review before continuing)
- User intervention

## How to Resume

Read `experiments.jsonl`. The last `kept: true` entry is the current `score.py` baseline. The most recent score function on disk should match that. If they disagree, restore from the kept entry.

## Output Files

- `score.py` — the current best score function
- `experiments.jsonl` — append-only log of all attempts
- `best.md` — summary of the current best result + which iteration achieved it
- `progress.png` — optional: Martin over iteration count

## Safety

- **Read-only on the rest of the repo.** You may NOT edit `us/scripts/us_portfolio_allocation.py`, `data_utils.py`, or anything in `india/`.
- **No live trading.** This is research only. Backtests against historical yfinance data.
- **No external API calls.** Everything must run on cached data.
- **Commit each kept iteration.** `git commit -am "autoresearch: <hypothesis>"`

---

*Begin with: read `experiments.jsonl` to recover state. If empty, run baseline backtest first to establish the number to beat. Then start iterating.*
