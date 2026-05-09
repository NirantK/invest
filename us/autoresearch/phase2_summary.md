# Phase 2 Sweep — 2026-05-09

**Method:** Block-bootstrap MC (10-day blocks) on each strategy's historical equity curve, 
shifted to target each regime's drift (bull/neutral/bear/shock). Plus 2/3 → 1/3 OOS split.

**Universe:** 162 tickers (162). **Paths:** 1000. **Horizon:** 3Y.

**Score:** weighted average P25 CAGR across regimes (bear weighted 2x) + OOS test CAGR + Martin.

## Ranking (best for blind 3Y hold)

| # | Strategy | Hist CAGR | Hist Martin | OOS Test | Bull P25 | Neut P25 | Bear P25 | Shock P25 | Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `S12_no_inpain` | 122% | 17.40 | +196% | +87% | -11% | -37% | -55% | 122.4 |
| 2 | `S12_no_inpain` | 108% | 13.33 | +194% | +73% | -11% | -38% | -56% | 109.9 |
| 3 | `S12_no_inpain` | 109% | 11.29 | +202% | +72% | -13% | -39% | -57% | 108.6 |
| 4 | `S12_no_inpain` | 103% | 12.80 | +190% | +72% | -10% | -37% | -55% | 107.3 |
| 5 | `S0_baseline_no_adv` | 102% | 13.89 | +183% | +73% | -9% | -35% | -54% | 106.9 |
| 6 | `S0_baseline_no_adv` | 91% | 11.46 | +192% | +64% | -8% | -35% | -54% | 105.1 |
| 7 | `S11_lev15_volt_dd` | 96% | 11.44 | +175% | +67% | -8% | -35% | -54% | 97.8 |
| 8 | `S11_lev15_volt_dd` | 90% | 10.08 | +182% | +61% | -8% | -35% | -54% | 97.1 |
| 9 | `S0_baseline_no_adv` | 100% | 14.40 | +157% | +68% | -9% | -36% | -54% | 93.8 |
| 10 | `S11_lev15_volt_dd` | 92% | 11.78 | +159% | +61% | -8% | -35% | -54% | 88.6 |
| 11 | `S0_baseline_no_adv` | 93% | 10.01 | +167% | +61% | -11% | -37% | -56% | 87.6 |
| 12 | `S12_no_inpain` | 105% | 11.65 | +155% | +69% | -12% | -38% | -57% | 85.7 |
| 13 | `S5_voltarget_25` | 85% | 12.85 | +143% | +62% | -5% | -33% | -51% | 85.2 |
| 14 | `S11_lev15_volt_dd` | 80% | 7.62 | +174% | +50% | -10% | -37% | -56% | 84.5 |
| 15 | `S5_voltarget_25` | 79% | 11.28 | +147% | +56% | -5% | -33% | -51% | 83.1 |
| 16 | `S5_voltarget_25` | 81% | 13.42 | +124% | +57% | -5% | -33% | -52% | 75.8 |
| 17 | `S5_voltarget_25` | 74% | 9.27 | +141% | +51% | -6% | -33% | -52% | 74.1 |
| 18 | `S11_lev15_volt_dd` | 86% | 9.77 | +141% | +56% | -9% | -36% | -55% | 74.1 |
| 19 | `S0_baseline_no_adv` | 81% | 10.16 | +132% | +51% | -10% | -37% | -55% | 68.7 |
| 20 | `S5_voltarget_25` | 69% | 10.08 | +112% | +45% | -7% | -34% | -52% | 59.8 |

## Configurations

### S12_no_inpain

Overrides: `{"current_dd_floor": -1.0}`

- Historical: CAGR 122%, Martin 17.40, Ulcer 7.0%, MaxDD -25%, %time-in-cash 0%
- OOS: train +64% → test +196% (MaxDD -19%)
- Bull MC: P5/P25/P50/P75/P95 CAGR = +56% / +87% / +114% / +142% / +194%
- Neutral MC: P5/P25/P50/P75/P95 CAGR = -26% / -11% / +3% / +16% / +41%
- Bear MC: P5/P25/P50/P75/P95 CAGR = -48% / -37% / -28% / -18% / -1%
- Shock MC: P5/P25/P50/P75/P95 CAGR = -63% / -55% / -49% / -42% / -29%

### S12_no_inpain

Overrides: `{"current_dd_floor": -1.0}`

- Historical: CAGR 108%, Martin 13.33, Ulcer 8.1%, MaxDD -28%, %time-in-cash 0%
- OOS: train +50% → test +194% (MaxDD -19%)
- Bull MC: P5/P25/P50/P75/P95 CAGR = +41% / +73% / +99% / +127% / +178%
- Neutral MC: P5/P25/P50/P75/P95 CAGR = -28% / -11% / +2% / +17% / +43%
- Bear MC: P5/P25/P50/P75/P95 CAGR = -49% / -38% / -28% / -18% / +1%
- Shock MC: P5/P25/P50/P75/P95 CAGR = -64% / -56% / -49% / -42% / -29%

### S12_no_inpain

Overrides: `{"current_dd_floor": -1.0}`

- Historical: CAGR 109%, Martin 11.29, Ulcer 9.7%, MaxDD -34%, %time-in-cash 0%
- OOS: train +43% → test +202% (MaxDD -21%)
- Bull MC: P5/P25/P50/P75/P95 CAGR = +40% / +72% / +100% / +130% / +185%
- Neutral MC: P5/P25/P50/P75/P95 CAGR = -29% / -13% / +2% / +17% / +45%
- Bear MC: P5/P25/P50/P75/P95 CAGR = -50% / -39% / -29% / -18% / +2%
- Shock MC: P5/P25/P50/P75/P95 CAGR = -65% / -57% / -50% / -42% / -28%

### S12_no_inpain

Overrides: `{"current_dd_floor": -1.0}`

- Historical: CAGR 103%, Martin 12.80, Ulcer 8.0%, MaxDD -29%, %time-in-cash 0%
- OOS: train +43% → test +190% (MaxDD -19%)
- Bull MC: P5/P25/P50/P75/P95 CAGR = +43% / +72% / +96% / +121% / +169%
- Neutral MC: P5/P25/P50/P75/P95 CAGR = -25% / -10% / +2% / +16% / +41%
- Bear MC: P5/P25/P50/P75/P95 CAGR = -48% / -37% / -28% / -18% / -1%
- Shock MC: P5/P25/P50/P75/P95 CAGR = -63% / -55% / -49% / -42% / -29%

### S0_baseline_no_adv

Overrides: `{}`

- Historical: CAGR 102%, Martin 13.89, Ulcer 7.4%, MaxDD -24%, %time-in-cash 0%
- OOS: train +43% → test +183% (MaxDD -20%)
- Bull MC: P5/P25/P50/P75/P95 CAGR = +46% / +73% / +97% / +122% / +165%
- Neutral MC: P5/P25/P50/P75/P95 CAGR = -23% / -9% / +4% / +17% / +40%
- Bear MC: P5/P25/P50/P75/P95 CAGR = -46% / -35% / -27% / -17% / -1%
- Shock MC: P5/P25/P50/P75/P95 CAGR = -61% / -54% / -48% / -41% / -29%
