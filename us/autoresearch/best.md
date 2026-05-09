# Current Best — Iteration 1 (Baseline)

**Hypothesis:** Sortino-style score with equal weighting and monthly rebalance, established as the best combination from the 27-combo sweep on 2026-05-09.

**Config:** `score_col=score_sortino, sizing=equal, rebal_days=21`

**Metrics:**
- CAGR: **88.0%**
- Martin Ratio: **13.64**
- Ulcer Index: 6.5%
- Max Drawdown: -23%
- Sharpe (informational): 2.07
- Avg positions: 15.0

**Universe:** 127 tickers (Leo + Citrini + Zephyr expansions, AI Power, Biotech)
**Filters:** ADV ≥ $5M, current_dd ≥ -25%, sleeve caps (AI Infra 40%, AI Power 20%, Biotech 15%, Crypto-AI 15%, Energy 15%, Real Assets 20%, Defensive 15%)
**Period:** 3Y walk-forward (2023-05 → 2026-05), 1Y warmup

**Logged at:** 2026-05-09T09:18:00

---

## Score Function (current)

Implemented in `us_portfolio_allocation.py:_score_one()`:

```
score_sortino = (wt_mom × smoothness × vol_factor × high_factor) / dn_vol
```

Where:
- `wt_mom = 0.2*mom_3m + 0.4*mom_6m + 0.4*mom_12m` (skip-1M)
- `smoothness = sqrt(R² × FIP)`
- `vol_factor = clip(1 + 0.15*dv_slope, 0.7, 1.3)` — dollar-volume slope confirmation
- `high_factor` = boost if within 10% of 52WH, penalty if >25% below
- `dn_vol` = annualized stdev of negative returns

## Sizing (current)

Equal-weight: 1/N for selected names, capped at 15% per name, 3% min. Sleeve caps applied post-allocation.

## To Beat

Next experiment must achieve:
- Δ Martin ≥ +0.20 (regardless of Ulcer), OR
- Δ Martin ≥ +0.05 AND Δ Ulcer ≤ +0.005

## Hypotheses Pending

1. MFI-14 volume signal added to score
2. current_dd squared penalty (heavier punishment for already-bleeding names)
3. Sector relative-strength rank (z-score within sleeve)
4. Earnings momentum overlay (build_earnings_momentum is implemented but unused)
5. SPY 50DMA × 200DMA regime gate (go to cash when bearish)
6. Tighter sleeve caps on AI Infra (try 30% vs 40%)
