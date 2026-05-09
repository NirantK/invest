# Autoresearch Sweep — 2026-05-09

Tested 16 hypotheses. Each varies ONE+ knobs from the baseline:
`score_sortino × equal × 21d × top 15 × sleeves on × ADV $5M × in-pain -25%`

## Summary table

| Name | CAGR | Martin | Ulcer | MaxDD | AvgPos | Hypothesis |
|---|---|---|---|---|---|---|
| baseline | 93.1% | 10.88 | 8.6% | -28% | 15.0 | Reproduce baseline (sortino × equal × 21d, all gates on) |
| h1_top5 | 114.0% | 8.70 | 13.1% | -34% | 5.0 | Concentrate to top 5 names — let winners dominate (price of  |
| h2_top8 | 93.1% | 9.22 | 10.1% | -32% | 8.0 | Concentrate to top 8 — middle ground vs current 15 |
| h3_no_sleeves | 84.2% | 9.21 | 9.1% | -27% | 15.0 | Drop sleeve caps — let AI Infra run organic (was 64% before  |
| h4_no_adv | 99.8% | 14.38 | 6.9% | -22% | 15.0 | Drop $5M ADV gate — admit thin-tape rockets (some 10x names  |
| h5_no_inpain | 105.8% | 12.48 | 8.5% | -29% | 15.0 | Drop in-pain filter — INTC was -50% before +132%; recovery s |
| h6_raw_top8 | 93.6% | 7.74 | 12.1% | -33% | 8.0 | Score-weighted raw + top 8 — concentration AND magnitude til |
| h7_leverage_13 | 129.0% | 11.69 | 11.0% | -36% | 15.0 | 1.3x leverage — multiplicative on equity curve, equivalent r |
| h8_leverage_15 | 154.9% | 12.23 | 12.7% | -41% | 15.0 | 1.5x leverage — half-step toward 2x (margin-feasible at IBKR |
| h9_rank_top8 | 75.5% | 11.22 | 6.7% | -23% | 8.0 | Score_rank + sqrt + top 8 — diversified-but-concentrated, lo |
| h10_aggressive | 99.3% | 7.69 | 12.9% | -32% | 7.0 | Top 7 + no sleeves + raw weight — combined aggression |
| h11_max_aggression | 131.0% | 6.84 | 19.2% | -50% | 5.0 | Top 5 + no sleeves + no in-pain + 1.3x lev — what 120% guys  |
| h12_top20_safe | 86.8% | 10.89 | 8.0% | -27% | 20.0 | Top 20 — control group: more diversification, lower vol |
| h13_weekly_rebal | 90.4% | 10.64 | 8.5% | -28% | 15.0 | 5-day rebalance — capture short-horizon momentum shifts |
| h14_biweekly_rebal | 92.0% | 10.39 | 8.9% | -29% | 14.9 | 10-day rebalance — between weekly and monthly |
| h15_no_min | 93.1% | 10.88 | 8.6% | -28% | 15.0 | Drop the 3% min-position floor — let small bets through |

## Winners by metric

**Highest CAGR:** h8_leverage_15 — 154.9% (Ulcer 12.7%)
**Highest Martin:** h4_no_adv — Martin 14.38 (CAGR 99.8%, Ulcer 6.9%)
**Lowest Ulcer:** h9_rank_top8 — Ulcer 6.7% (CAGR 75.5%)

## Mechanism reads

- **h1_top5**: ΔCAGR +20.9pp, ΔMartin -2.19, ΔUlcer +4.6pp — *Concentrate to top 5 names — let winners dominate (price of admission:*
- **h2_top8**: ΔCAGR -0.0pp, ΔMartin -1.66, ΔUlcer +1.5pp — *Concentrate to top 8 — middle ground vs current 15*
- **h3_no_sleeves**: ΔCAGR -9.0pp, ΔMartin -1.67, ΔUlcer +0.6pp — *Drop sleeve caps — let AI Infra run organic (was 64% before caps demot*
- **h4_no_adv**: ΔCAGR +6.7pp, ΔMartin +3.50, ΔUlcer -1.6pp — *Drop $5M ADV gate — admit thin-tape rockets (some 10x names live there*
- **h5_no_inpain**: ΔCAGR +12.7pp, ΔMartin +1.60, ΔUlcer -0.1pp — *Drop in-pain filter — INTC was -50% before +132%; recovery setups beat*
- **h6_raw_top8**: ΔCAGR +0.5pp, ΔMartin -3.14, ΔUlcer +3.5pp — *Score-weighted raw + top 8 — concentration AND magnitude tilt*
- **h7_leverage_13**: ΔCAGR +35.9pp, ΔMartin +0.81, ΔUlcer +2.5pp — *1.3x leverage — multiplicative on equity curve, equivalent risk magnif*
- **h8_leverage_15**: ΔCAGR +61.8pp, ΔMartin +1.35, ΔUlcer +4.1pp — *1.5x leverage — half-step toward 2x (margin-feasible at IBKR)*
- **h9_rank_top8**: ΔCAGR -17.6pp, ΔMartin +0.34, ΔUlcer -1.8pp — *Score_rank + sqrt + top 8 — diversified-but-concentrated, lowest-Ulcer*
- **h10_aggressive**: ΔCAGR +6.2pp, ΔMartin -3.19, ΔUlcer +4.4pp — *Top 7 + no sleeves + raw weight — combined aggression*
- **h11_max_aggression**: ΔCAGR +37.9pp, ΔMartin -4.04, ΔUlcer +10.6pp — *Top 5 + no sleeves + no in-pain + 1.3x lev — what 120% guys do*
- **h12_top20_safe**: ΔCAGR -6.3pp, ΔMartin +0.01, ΔUlcer -0.6pp — *Top 20 — control group: more diversification, lower vol*
- **h13_weekly_rebal**: ΔCAGR -2.7pp, ΔMartin -0.24, ΔUlcer -0.1pp — *5-day rebalance — capture short-horizon momentum shifts*
- **h14_biweekly_rebal**: ΔCAGR -1.1pp, ΔMartin -0.49, ΔUlcer +0.3pp — *10-day rebalance — between weekly and monthly*
- **h15_no_min**: ΔCAGR +0.0pp, ΔMartin +0.00, ΔUlcer +0.0pp — *Drop the 3% min-position floor — let small bets through*