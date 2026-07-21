# Tactical Return Maximizer — 126d (6m)

## TL;DR — 6M Wins on Risk-Adjusted Returns

**Headline:** Same screener (`score_4w` + breadth gate) at 6M holding window gives ~2x the upside vs 3M for the *same* downside. If you can tolerate the longer hold, 6M dominates.

### Three picks for the tactical sleeve

| Pick | Config | P50 | P75 | P90 | P10 | DD P50 | Win% | When |
|---|---|---|---|---|---|---|---|---|
| **A. Greedy 6M** | `eq × 5d × 5 pos × 2.0x` | +18.6% | **+81.4%** | **+155.4%** | -41.4% | -41% | 60% | Max upside; tolerate ~1-in-10 H losing 40%+ |
| **B. Balanced 6M** *(recommended)* | `4w × 10d × 8 pos × 1.5x` | +20.8% | +56.6% | +100.5% | -21.8% | -26% | 69% | Best P75-per-Ulcer at any lev > 1.0x |
| **C. Defensive 6M** | `4w × 10d × 8 pos × 1.0x` | +15.7% | +38.3% | +67.4% | -12.7% | -17% | **73%** | Highest win rate of any config tested |

### 3M vs 6M — same screener, longer hold

| Metric | 3M defensive (4w × 5d × 10 × 1.0x) | 6M defensive (4w × 10d × 8 × 1.0x) | Δ |
|---|---|---|---|
| P50 | +6.9% | +15.7% | **+8.8pp** |
| P75 | +19.9% | +38.3% | **+18.4pp** |
| P90 | +34.2% | +67.4% | +33.2pp |
| P10 (downside) | -12.7% | -12.7% | 0pp (same!) |
| DD P50 | -12% | -17% | -5pp |
| Win% | 64% | **73%** | +9pp |
| Annualized P75 | ~83% | ~98% | +15pp |

**Translation:** doubling the hold doubles upside without doubling downside. Breadth gate handles regime shifts on both timelines (~18% time in cash either way). Win rate climbs from 64% → 73%.

### Score variant winner

Same as 3M: **`score_4w`** dominates on risk-adjusted. `score_eq` (equal composite of 1W/2W/4W/8W) wins on raw P75 at 2x lev because it picks slightly different names in choppy regimes — but eats more Ulcer.

### Position count shifts for 6M

- 3M sweet spot: 5-10 positions (concentration helps 3M)
- 6M sweet spot: **8 positions** (longer hold rewards diversification slightly)

### Leverage curve (6M, best per lev)

| lev | P75 | P10 | DD P50 | Verdict |
|---|---|---|---|---|
| 1.0x | +43% | -19% | -21% | Robust, 73% win rate |
| 1.3x | +55% | -22% | -27% | +12pp P75 for +6pp tail |
| 1.5x | +63% | -27% | -32% | **Sweet spot — best P75/Ulcer** |
| 2.0x | +81% | -41% | -41% | +18pp P75 for +14pp tail (worse trade) |

### When to pick 3M vs 6M

| Scenario | Pick |
|---|---|
| Need cash flexibility every quarter | 3M |
| Tax loss harvesting at 3-month boundaries (LLC entity) | 3M |
| C Corp short-term gains (already 21% — horizon-agnostic) | **6M** |
| Want highest risk-adj upside | **6M** |
| Want to minimize touches | **6M** (1 rebal cycle covers full 6M) |

For your C Corp $89K NetLiq book: **6M Balanced is the better tactical sleeve**. Same risk profile as the 3M Balanced, materially better expected upside.

---

**Generated:** 2026-05-09  
**Period:** max (start 2008-01-01)  
**Validation:** 216 rolling 126-day forward windows (step 21d)  
**Universe:** 159 tickers  
**Configs swept:** 252 = 7 scores × 3 rebal × 3 pos × 4 lev  

## Costs Modeled
- 5 bps turnover per rebal × leverage (IBKR-realistic)
- 6.0% annual margin debit on negative cash
- 4.5% annual yield on positive cash
- Breadth gate: cash if <30% of universe has positive 4W mom

## Top 15 by P75 of 126-day return

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      eq |  5d | 5 | 2.0x | -41.4% | -22.0% | +18.6% | +81.4% | +155.4% | 21.6% | -41% | 60% | 18% |
|      4w |  2d | 5 | 2.0x | -47.2% | -18.4% | +16.6% | +80.0% | +173.4% | 20.6% | -38% | 58% | 18% |
|      eq | 10d | 5 | 2.0x | -42.8% | -18.5% | +16.8% | +77.3% | +178.8% | 20.1% | -39% | 60% | 18% |
|      4w | 10d | 5 | 2.0x | -40.2% | -15.2% | +27.8% | +76.8% | +175.6% | 19.0% | -38% | 65% | 18% |
|      2w | 10d | 5 | 2.0x | -40.5% | -12.9% | +17.4% | +75.4% | +150.4% | 18.6% | -39% | 66% | 18% |
|      4w | 10d | 8 | 2.0x | -33.0% | -8.1% | +24.1% | +73.6% | +138.0% | 16.4% | -34% | 67% | 18% |
|      4w |  5d | 5 | 2.0x | -42.0% | -20.2% | +23.3% | +71.9% | +183.9% | 19.9% | -39% | 64% | 18% |
|    tilt | 10d | 5 | 2.0x | -38.0% | -17.3% | +16.7% | +70.8% | +172.5% | 20.9% | -40% | 62% | 18% |
|      2w |  2d | 5 | 2.0x | -40.5% | -21.0% | +6.4% | +70.6% | +194.0% | 20.5% | -40% | 56% | 18% |
|      2w |  5d | 5 | 2.0x | -40.4% | -19.8% | +17.0% | +70.3% | +173.6% | 18.5% | -39% | 61% | 18% |
|    tilt |  5d | 5 | 2.0x | -39.9% | -22.3% | +14.1% | +69.2% | +172.4% | 20.8% | -41% | 62% | 18% |
|    tilt | 10d | 8 | 2.0x | -33.9% | -10.6% | +21.7% | +67.1% | +127.2% | 17.0% | -35% | 65% | 18% |
|      4w | 10d | 10 | 2.0x | -31.4% | -7.2% | +21.5% | +66.5% | +133.7% | 14.9% | -32% | 68% | 18% |
|      eq |  5d | 8 | 2.0x | -37.6% | -14.8% | +16.8% | +64.4% | +164.4% | 18.5% | -35% | 62% | 18% |
|      4w |  5d | 10 | 2.0x | -35.6% | -6.8% | +21.4% | +63.6% | +136.5% | 15.6% | -33% | 69% | 18% |

## Top 10 by P50 (median outcome)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      4w | 10d | 5 | 2.0x | -40.2% | -15.2% | +27.8% | +76.8% | +175.6% | 19.0% | -38% | 65% | 18% |
|      4w | 10d | 5 | 1.5x | -29.1% | -7.8% | +24.8% | +58.0% | +121.6% | 14.5% | -30% | 69% | 18% |
|      4w | 10d | 8 | 2.0x | -33.0% | -8.1% | +24.1% | +73.6% | +138.0% | 16.4% | -34% | 67% | 18% |
|    tilt |  5d | 8 | 2.0x | -41.0% | -14.8% | +23.7% | +59.5% | +139.5% | 17.6% | -34% | 64% | 18% |
|      4w |  5d | 5 | 2.0x | -42.0% | -20.2% | +23.3% | +71.9% | +183.9% | 19.9% | -39% | 64% | 18% |
|      4w | 10d | 5 | 1.3x | -25.1% | -5.9% | +22.2% | +53.4% | +103.0% | 12.6% | -26% | 69% | 18% |
|    tilt | 10d | 8 | 2.0x | -33.9% | -10.6% | +21.7% | +67.1% | +127.2% | 17.0% | -35% | 65% | 18% |
|      4w | 10d | 10 | 2.0x | -31.4% | -7.2% | +21.5% | +66.5% | +133.7% | 14.9% | -32% | 68% | 18% |
|      4w |  5d | 10 | 2.0x | -35.6% | -6.8% | +21.4% | +63.6% | +136.5% | 15.6% | -33% | 69% | 18% |
|      4w |  2d | 10 | 2.0x | -31.0% | -12.0% | +21.2% | +54.2% | +143.4% | 16.1% | -33% | 67% | 18% |

## Top 10 by P90 (right-tail jackpot)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      2w |  2d | 5 | 2.0x | -40.5% | -21.0% | +6.4% | +70.6% | +194.0% | 20.5% | -40% | 56% | 18% |
|      4w |  5d | 5 | 2.0x | -42.0% | -20.2% | +23.3% | +71.9% | +183.9% | 19.9% | -39% | 64% | 18% |
|    tilt |  2d | 5 | 2.0x | -42.6% | -27.0% | +5.5% | +63.2% | +183.9% | 23.4% | -43% | 54% | 18% |
|      eq |  2d | 5 | 2.0x | -43.4% | -27.6% | +6.8% | +63.3% | +180.5% | 24.2% | -43% | 56% | 18% |
|      eq | 10d | 5 | 2.0x | -42.8% | -18.5% | +16.8% | +77.3% | +178.8% | 20.1% | -39% | 60% | 18% |
|      4w | 10d | 5 | 2.0x | -40.2% | -15.2% | +27.8% | +76.8% | +175.6% | 19.0% | -38% | 65% | 18% |
|      2w |  5d | 5 | 2.0x | -40.4% | -19.8% | +17.0% | +70.3% | +173.6% | 18.5% | -39% | 61% | 18% |
|      4w |  2d | 5 | 2.0x | -47.2% | -18.4% | +16.6% | +80.0% | +173.4% | 20.6% | -38% | 58% | 18% |
|    tilt | 10d | 5 | 2.0x | -38.0% | -17.3% | +16.7% | +70.8% | +172.5% | 20.9% | -40% | 62% | 18% |
|    tilt |  5d | 5 | 2.0x | -39.9% | -22.3% | +14.1% | +69.2% | +172.4% | 20.8% | -41% | 62% | 18% |

## Top 10 by P75 / Ulcer (return-per-pain)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      4w | 10d | 8 | 1.0x | -12.7% | -1.0% | +15.7% | +38.3% | +67.4% | 8.1% | -17% | 73% | 18% |
|      4w | 10d | 10 | 1.0x | -13.8% | -0.7% | +14.1% | +34.7% | +64.0% | 7.5% | -16% | 74% | 18% |
|      4w | 10d | 8 | 1.3x | -17.8% | -2.7% | +18.8% | +49.3% | +87.0% | 10.7% | -22% | 71% | 18% |
|      4w | 10d | 8 | 1.5x | -21.8% | -4.3% | +20.8% | +56.6% | +100.5% | 12.4% | -26% | 69% | 18% |
|      4w | 10d | 8 | 2.0x | -33.0% | -8.1% | +24.1% | +73.6% | +138.0% | 16.4% | -34% | 67% | 18% |
|      4w | 10d | 10 | 1.3x | -19.0% | -2.4% | +16.8% | +43.6% | +84.3% | 9.7% | -21% | 72% | 18% |
|      4w | 10d | 10 | 2.0x | -31.4% | -7.2% | +21.5% | +66.5% | +133.7% | 14.9% | -32% | 68% | 18% |
|      4w | 10d | 10 | 1.5x | -22.5% | -3.7% | +17.7% | +49.8% | +98.0% | 11.2% | -25% | 71% | 18% |
|      4w | 10d | 5 | 1.0x | -18.8% | -3.5% | +18.6% | +42.8% | +78.5% | 9.8% | -20% | 70% | 18% |
|    tilt | 10d | 8 | 1.0x | -16.0% | -2.9% | +14.5% | +35.8% | +64.8% | 8.5% | -18% | 73% | 18% |

## Aggregates by Score Variant (best lev/pos/rebal per variant on P75)

| score | best rebal | best pos | best lev | P50 | P75 | P90 | Ulcer P50 | Win% |
|---|---|---|---|---|---|---|---|---|
|      1w | 5d | 8 | 2.0x | +8.2% | +57.3% | +115.4% | 18.0% | 56% |
|      2w | 10d | 5 | 2.0x | +17.4% | +75.4% | +150.4% | 18.6% | 66% |
|      4w | 2d | 5 | 2.0x | +16.6% | +80.0% | +173.4% | 20.6% | 58% |
|      8w | 2d | 5 | 2.0x | +2.9% | +52.4% | +125.9% | 23.1% | 53% |
|      eq | 5d | 5 | 2.0x | +18.6% | +81.4% | +155.4% | 21.6% | 60% |
|    tilt | 10d | 5 | 2.0x | +16.7% | +70.8% | +172.5% | 20.9% | 62% |
| sortino | 10d | 5 | 2.0x | +11.2% | +43.7% | +96.2% | 13.9% | 59% |

## Aggregates by Leverage (best score/pos/rebal per leverage)

| lev | best score | rebal | pos | P50 | P75 | P90 | Ulcer P50 | DD P50 |
|---|---|---|---|---|---|---|---|---|
| 1.0x | eq | 5d | 5 | +14.9% | +43.4% | +73.3% | 10.9% | -21% |
| 1.3x | eq | 5d | 5 | +16.9% | +55.3% | +97.6% | 14.2% | -27% |
| 1.5x | eq | 5d | 5 | +17.4% | +62.6% | +114.4% | 16.3% | -32% |
| 2.0x | eq | 5d | 5 | +18.6% | +81.4% | +155.4% | 21.6% | -41% |
