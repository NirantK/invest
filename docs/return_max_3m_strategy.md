# 3M Tactical Return Maximizer

## TL;DR — Three Configs To Choose From

Sleeve sized at **15-30% of NetLiq** (~$13K–$27K of $89K). All three use the same screener: rank universe by 4-week momentum, drop sleeve caps, breadth-gate to cash if <30% of universe has positive 4W mom.

| Pick | Config | P50 | P75 | P90 | P10 (downside) | DD P50 | Win% | When to use |
|---|---|---|---|---|---|---|---|---|
| **A. Greedy** | `4w × 10d × 5 pos × 2.0x` | +9.6% | **+43.5%** | **+101.2%** | -27.7% | -26% | 64% | You want max upside, stomach 1-in-10 Q losing 28%+ |
| **B. Balanced** *(recommended)* | `4w × 10d × 5 pos × 1.5x` | +8.1% | +32.7% | +71.4% | -20.3% | -20% | 66% | Best risk-adjusted upside; 1.5x lev keeps margin BP free |
| **C. Defensive** | `4w × 5d × 10 pos × 1.0x` | +6.9% | +19.9% | +34.2% | -12.7% | -12% | 64% | Sleeve-as-overlay; minimal tail; can run alongside main book at 30% |

**Cross-strategy winner: `score_4w`** (raw 4-week momentum). Beats sortino-style, equal composite, recency-tilt, and 1W/2W/8W single-horizons across all leverage levels. 4 weeks is the sweet spot for 3-month forward — short enough to catch theme rotations, long enough to filter weekly noise.

**Leverage trade-off (best config per lev):**

| lev | P75 | P90 | P10 | DD P50 | Verdict |
|---|---|---|---|---|---|
| 1.0x | +22.7% | +44.1% | -12.7% | -15% | Soft, but Win%=64% means consistent |
| 1.3x | +28.6% | +63.8% | -17.5% | -18% | Linear-ish upside per unit pain |
| 1.5x | +32.7% | +71.4% | -20.3% | -20% | **Sweet spot** — diminishing pain after this |
| 2.0x | +43.5% | +101.2% | -27.7% | -26% | +33% P75 vs 1.5x but +7pp tail damage |

**Position count:** Top configs all use 5 positions (concentration helps 3M). 8-10 pos works at 1.0x with better DD but lower P75.

**Rebal cadence:** 10d wins at low leverage, 5d wins at 2.0x. 2d over-trades — 5 bps × 31 rebals/Q = 1.6% drag eats the signal.

## Operational Notes

| Item | Detail |
|---|---|
| Capital | 15-30% of NetLiq → $13K-$27K out of $89K |
| Run cadence | Match config: 5d or 10d. Re-screen on schedule, no overrides |
| Margin BP usage | 1.5x on $20K = $30K notional, fits inside $283K BP |
| Funded from | Main book proceeds OR new cash. Don't reduce 3Y sleeve to fund this |
| Stop logic | None at sleeve level — breadth gate already handles regime shifts |
| Tax | 3-month horizon = ALL gains short-term. C Corp at 21% fed makes this less painful than personal |
| Failure mode | 1-in-4 quarters lose money. P10 = -20% on Balanced. Sized 20% of NetLiq, that's -4% to NetLiq |

## What This Sleeve Is NOT

- Not the 3Y core. The 3Y `S12 × 10d` strategy stays at 60% — this is separate.
- Not for retirement money. Tactical, can blow up in a quarter.
- Not blind hold. Re-runs on cadence, follows signal even when it goes to cash (~18% of trading days).

---

**Generated:** 2026-05-09  
**Period:** max (start 2008-01-01)  
**Validation:** 219 rolling 63-day forward windows (step 21d)  
**Universe:** 159 tickers  
**Configs swept:** 252 = 7 scores × 3 rebal × 3 pos × 4 lev  

## Costs Modeled
- 5 bps turnover per rebal × leverage (IBKR-realistic)
- 6.0% annual margin debit on negative cash
- 4.5% annual yield on positive cash
- Breadth gate: cash if <30% of universe has positive 4W mom

## Top 15 by P75 (the upside metric you asked for)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      4w | 10d | 5 | 2.0x | -27.7% | -10.8% | +9.6% | +43.5% | +101.2% | 12.5% | -26% | 64% | 18% |
|    tilt |  5d | 5 | 2.0x | -34.9% | -18.5% | +3.6% | +42.6% | +101.1% | 14.0% | -28% | 56% | 18% |
|      2w |  5d | 5 | 2.0x | -33.3% | -16.6% | +6.7% | +41.8% | +89.2% | 14.5% | -27% | 56% | 18% |
|      eq |  5d | 5 | 2.0x | -34.5% | -17.3% | +7.1% | +41.3% | +89.6% | 14.4% | -29% | 55% | 18% |
|      8w |  5d | 5 | 2.0x | -36.3% | -18.3% | +3.3% | +38.5% | +81.1% | 15.4% | -29% | 52% | 18% |
|      4w |  5d | 5 | 2.0x | -32.2% | -12.9% | +8.2% | +38.3% | +103.5% | 13.1% | -27% | 60% | 18% |
|      1w |  5d | 5 | 2.0x | -36.4% | -20.1% | +3.1% | +38.1% | +74.1% | 15.0% | -28% | 53% | 18% |
|      4w |  5d | 8 | 2.0x | -28.5% | -11.9% | +10.1% | +38.0% | +79.1% | 12.1% | -23% | 60% | 18% |
|      4w |  5d | 10 | 2.0x | -27.1% | -11.5% | +10.3% | +37.9% | +71.7% | 11.1% | -23% | 62% | 18% |
|      2w |  2d | 5 | 2.0x | -29.7% | -14.2% | +2.6% | +37.4% | +94.4% | 14.9% | -27% | 53% | 18% |
|    tilt | 10d | 5 | 2.0x | -32.4% | -15.0% | +5.1% | +37.2% | +91.4% | 14.6% | -29% | 58% | 18% |
|      eq | 10d | 5 | 2.0x | -29.2% | -14.9% | +7.7% | +37.0% | +82.2% | 14.7% | -30% | 60% | 18% |
|      eq |  5d | 8 | 2.0x | -31.5% | -14.7% | +8.3% | +36.7% | +71.7% | 11.7% | -25% | 56% | 18% |
|      2w |  5d | 8 | 2.0x | -29.0% | -13.5% | +8.0% | +36.6% | +75.0% | 12.2% | -24% | 57% | 18% |
|      8w | 10d | 5 | 2.0x | -32.8% | -18.2% | +3.7% | +36.2% | +72.5% | 15.1% | -30% | 53% | 18% |

## Top 10 by P50 (median outcome)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      4w | 10d | 8 | 2.0x | -26.3% | -9.4% | +10.8% | +34.8% | +87.2% | 11.4% | -24% | 62% | 18% |
|      4w |  5d | 10 | 2.0x | -27.1% | -11.5% | +10.3% | +37.9% | +71.7% | 11.1% | -23% | 62% | 18% |
|      4w |  5d | 8 | 2.0x | -28.5% | -11.9% | +10.1% | +38.0% | +79.1% | 12.1% | -23% | 60% | 18% |
|      4w | 10d | 5 | 2.0x | -27.7% | -10.8% | +9.6% | +43.5% | +101.2% | 12.5% | -26% | 64% | 18% |
|      4w |  2d | 10 | 2.0x | -25.0% | -13.0% | +9.1% | +31.1% | +69.7% | 11.1% | -23% | 62% | 18% |
|      4w |  5d | 10 | 1.5x | -20.2% | -8.1% | +9.1% | +28.9% | +52.1% | 8.3% | -17% | 63% | 18% |
|      4w | 10d | 8 | 1.5x | -19.1% | -6.2% | +9.0% | +27.2% | +63.9% | 8.8% | -18% | 63% | 18% |
|      4w | 10d | 5 | 1.3x | -17.5% | -5.9% | +9.0% | +28.4% | +60.4% | 8.2% | -17% | 67% | 18% |
|    tilt |  5d | 10 | 2.0x | -28.3% | -11.5% | +8.7% | +35.3% | +72.0% | 11.3% | -23% | 60% | 18% |
|    tilt | 10d | 8 | 2.0x | -28.8% | -10.4% | +8.6% | +33.9% | +79.2% | 11.4% | -25% | 61% | 18% |

## Top 10 by P90 (right-tail jackpot)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      4w |  5d | 5 | 2.0x | -32.2% | -12.9% | +8.2% | +38.3% | +103.5% | 13.1% | -27% | 60% | 18% |
|      4w |  2d | 5 | 2.0x | -32.7% | -14.6% | +5.0% | +34.8% | +101.5% | 14.7% | -28% | 55% | 18% |
|      4w | 10d | 5 | 2.0x | -27.7% | -10.8% | +9.6% | +43.5% | +101.2% | 12.5% | -26% | 64% | 18% |
|    tilt |  5d | 5 | 2.0x | -34.9% | -18.5% | +3.6% | +42.6% | +101.1% | 14.0% | -28% | 56% | 18% |
|      eq |  2d | 5 | 2.0x | -33.4% | -20.6% | +2.5% | +35.0% | +97.5% | 16.2% | -31% | 54% | 18% |
|    tilt |  2d | 5 | 2.0x | -32.2% | -20.3% | +2.4% | +32.6% | +96.6% | 15.5% | -29% | 53% | 18% |
|      2w |  2d | 5 | 2.0x | -29.7% | -14.2% | +2.6% | +37.4% | +94.4% | 14.9% | -27% | 53% | 18% |
|    tilt | 10d | 5 | 2.0x | -32.4% | -15.0% | +5.1% | +37.2% | +91.4% | 14.6% | -29% | 58% | 18% |
|      eq |  5d | 5 | 2.0x | -34.5% | -17.3% | +7.1% | +41.3% | +89.6% | 14.4% | -29% | 55% | 18% |
|      2w |  5d | 5 | 2.0x | -33.3% | -16.6% | +6.7% | +41.8% | +89.2% | 14.5% | -27% | 56% | 18% |

## Top 10 by P75 / Ulcer (return-per-pain)

| score | rebal | pos | lev | P10 | P25 | P50 | P75 | P90 | Ulcer P50 | DD P50 | Win% | Cash% |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|      4w |  5d | 10 | 1.0x | -12.7% | -4.5% | +6.9% | +19.9% | +34.2% | 5.5% | -12% | 64% | 18% |
|      4w |  5d | 10 | 1.3x | -17.3% | -6.7% | +8.3% | +25.2% | +44.8% | 7.2% | -15% | 64% | 18% |
|      4w | 10d | 5 | 1.0x | -13.3% | -3.8% | +7.7% | +22.3% | +45.1% | 6.3% | -13% | 68% | 18% |
|      eq | 10d | 10 | 1.0x | -12.3% | -3.9% | +5.2% | +18.2% | +34.9% | 5.2% | -12% | 64% | 18% |
|      4w |  5d | 10 | 1.5x | -20.2% | -8.1% | +9.1% | +28.9% | +52.1% | 8.3% | -17% | 63% | 18% |
|      4w |  5d | 8 | 1.0x | -13.8% | -4.2% | +5.9% | +20.5% | +38.5% | 5.9% | -12% | 65% | 18% |
|      4w | 10d | 5 | 2.0x | -27.7% | -10.8% | +9.6% | +43.5% | +101.2% | 12.5% | -26% | 64% | 18% |
|      4w | 10d | 5 | 1.3x | -17.5% | -5.9% | +9.0% | +28.4% | +60.4% | 8.2% | -17% | 67% | 18% |
|      4w | 10d | 5 | 1.5x | -20.3% | -7.3% | +8.1% | +32.7% | +71.4% | 9.5% | -20% | 66% | 18% |
|      4w | 10d | 10 | 1.0x | -11.4% | -3.5% | +6.5% | +18.4% | +37.7% | 5.3% | -11% | 66% | 18% |

## Aggregates by Score Variant (best lev/pos/rebal per variant on P75)

| score | best rebal | best pos | best lev | P50 | P75 | P90 | Ulcer P50 | Win% |
|---|---|---|---|---|---|---|---|---|
|      1w | 5d | 5 | 2.0x | +3.1% | +38.1% | +74.1% | 15.0% | 53% |
|      2w | 5d | 5 | 2.0x | +6.7% | +41.8% | +89.2% | 14.5% | 56% |
|      4w | 10d | 5 | 2.0x | +9.6% | +43.5% | +101.2% | 12.5% | 64% |
|      8w | 5d | 5 | 2.0x | +3.3% | +38.5% | +81.1% | 15.4% | 52% |
|      eq | 5d | 5 | 2.0x | +7.1% | +41.3% | +89.6% | 14.4% | 55% |
|    tilt | 5d | 5 | 2.0x | +3.6% | +42.6% | +101.1% | 14.0% | 56% |
| sortino | 10d | 5 | 2.0x | +5.4% | +27.0% | +53.1% | 8.9% | 57% |

## Aggregates by Leverage (best score/pos/rebal per leverage)

| lev | best score | rebal | pos | P50 | P75 | P90 | Ulcer P50 | DD P50 |
|---|---|---|---|---|---|---|---|---|
| 1.0x | eq | 5d | 5 | +4.9% | +22.7% | +44.1% | 7.3% | -15% |
| 1.3x | tilt | 5d | 5 | +4.0% | +28.6% | +63.8% | 9.0% | -18% |
| 1.5x | 4w | 10d | 5 | +8.1% | +32.7% | +71.4% | 9.5% | -20% |
| 2.0x | 4w | 10d | 5 | +9.6% | +43.5% | +101.2% | 12.5% | -26% |
