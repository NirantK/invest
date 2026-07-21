# AI-Infra Autoresearch Loop — `program.md`

Karpathy-style autonomous-research loop adapted from
[autoresearch-macos](https://github.com/karpathy/autoresearch).
Instead of training an LLM on tinystories and minimising val_bpb, this loop
sweeps **portfolio strategy parameters** on the AI-infra India universe and
maximises a composite of out-of-sample Sortino × Calmar × crash-resilience.

## What gets iterated

The agent (or random search) modifies `ai_infra_strategy.py` — a single dict
of strategy hyperparameters:

```python
STRATEGY = {
    "lookbacks":      (126, 252, 504),    # 3 momentum windows in trading days
    "weights":        (0.5, 0.3, 0.2),    # sum to 1.0
    "skip_days":      21,                  # 1M skip
    "score_variant":  "sortino_vnorm",     # see SCORE_VARIANTS
    "n_positions":    3,                   # holdings count
    "rebal_days":     42,                  # rebalance frequency
    "max_dd_cap":     0.30,                # bucket cap
    "min_history":    252,                 # min days of price history per name
    "crash_p_annual": 0.30,                # MC crash injection probability
}
```

## Score function (higher = better)

```
composite = sortino_oos × calmar_oos × (1 - p_catastrophic)
where p_catastrophic = MC probability of >-30% drawdown over 12M
```

This rewards **return per unit of pain** AND penalises tail risk.

## Loop structure

1. Sample params: 30% random, 70% greedy mutation of current best.
2. Walk-forward backtest on AI-infra universe (~30 OOS windows, 3y history).
3. Stress MC: 10,000 paths × 12M, with calibrated crash injection
   (probabilities + magnitudes from `india/data/em_crash_scenarios.json`).
4. Compute composite score.
5. If best, save to `india/data/research_best.json`. Always append to
   `india/data/research_log.jsonl`.
6. Repeat for N iterations (default 500) or wall-clock budget.

## Crash calibration

EM crash buckets pulled from 1980-2026 history across India, Korea, Japan,
Brazil, Indonesia, Taiwan, Mexico, Thailand, Russia, South Africa.

| Bucket | Magnitude | Duration | Avg recovery | Annual freq (per market) |
|---|---|---|---|---|
| Mild | -10% to -25% | 1-6 mo | 6-12 mo | ~0.6 |
| Severe | -25% to -45% | 4-12 mo | 12-30 mo | ~0.15 |
| Catastrophic | >-45% | 12-24 mo | 24-60 mo | ~0.04 |

## How to run

```bash
# One-shot best-strategy search (500 iters, ~15 min on cached data)
uv run python india/scripts/ai_infra_autoresearch.py --iters 500

# Overnight (nohup, longer budget)
nohup uv run python india/scripts/ai_infra_autoresearch.py --iters 5000 > research.log &
```

## Outputs

- `india/data/research_log.jsonl` — every experiment, one line per iter
- `india/data/research_best.json` — best strategy + metrics + holdings
- `india/data/research_progress.png` — composite score over time
