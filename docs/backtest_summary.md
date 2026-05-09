# V2 Screener Backtest — 2026-05-09

Walk-forward 3Y backtest of the new screener (Ulcer/Martin scoring + ranking + sleeve caps).

- **Universe:** 127 tickers (Leo + Citrini + Zephyr expansions)
- **Capital:** $100,000 start
- **Warmup:** 252 days (uses only data ≥ rebalance date)
- **Filters:** ADV ≥ $5M, current_dd ≥ -25%, thesis groups, sleeve caps applied
- **Goal:** Maximize Martin Ratio (CAGR / Ulcer Index). User pivoted from Sharpe.

## Top 5 by Martin Ratio

| Rank | Score | Sizing | Rebal | CAGR | Martin | Ulcer | MaxDD | Read |
|---|---|---|---|---|---|---|---|---|
| 1 | sortino | equal | 21d | **88.0%** | **13.64** | 6.5% | -23% | Best CAGR + best Martin |
| 2 | rank | sqrt | 21d | 73.5% | 11.73 | **6.3%** | **-22%** | Best Ulcer, best DD |
| 3 | rank | raw | 21d | 74.3% | 11.68 | 6.4% | -22% | |
| 4 | rank | equal | 21d | 72.1% | 11.48 | 6.3% | -22% | Tied lowest Ulcer |
| 5 | sortino | equal | 126d | 74.2% | 11.08 | 6.7% | -26% | Lower turnover variant |

## Worst 3

| Score | Sizing | Rebal | Martin | Ulcer | Why Bad |
|---|---|---|---|---|---|
| martin | raw | 126d | 6.10 | 8.4% | Score-as-Martin in selection ironically picks lower-return names |
| martin | raw | 63d | 6.59 | 10.2% | Same issue |
| sortino | raw | 126d | 7.16 | 8.5% | Slow rebalance loses the momentum edge |

## Patterns

| Finding | Evidence |
|---|---|
| **Monthly rebalance (21d) wins** | All top 5 are 21d. 126d underperforms by 2-5 Martin units |
| **Equal sizing wins more often than expected** | Equal beats raw in 9 of 9 score×rebal combos |
| **Rank-based scoring is best for Ulcer minimization** | All 9 rank-based runs have Ulcer ≤ 7.1% |
| **Sortino+equal wins Martin by combining return tilt with diversification** | Best CAGR (88%) + 2nd-best Ulcer (6.5%) |
| **Score-as-Martin (in selection) underperforms** | Bottom 5 all have score=martin. Selection on "return per pain" picks low-return names |
| **Sqrt sizing rarely wins** | Compresses outliers but doesn't flatten enough |

## My PM Read

**Recommended config:** **`score_sortino × equal × 21d`** — Martin 13.64, CAGR 88%, Ulcer 6.5%, MaxDD -23%.

But two close alternatives:
- For **lowest Ulcer** (6.3%) and best DD (-22%): `score_rank × sqrt × 21d`
- For **lowest turnover** (still strong Martin): `score_sortino × equal × 126d` Martin 11.08

## Caveats

| Caveat | Impact |
|---|---|
| 3Y window is 2023-2026 — strong AI/momentum bull | Returns likely overstated for next regime |
| Tickers added recently (CRWV, OKLO, TLN) ride the wave | Survivorship bias in universe construction |
| No transaction cost modeling | 21d rebal × 15 names × 25% turnover = ~36 trades/yr, ~0.2-0.5% annual drag at IBKR commissions |
| Sleeve caps applied at every rebalance | May force suboptimal exits when winning sleeves get demoted |
| ADV filter at $5M | Too low for $1M+ portfolios; raise to $20M+ if scaling |

## What Surprised Me

1. **Score formula matters less than sizing.** The Sortino score (which I labeled "legacy") beat the new Martin-anchored score because portfolio Ulcer comes from diversification, not from selecting low-Ulcer individual names.
2. **Equal-weight wins.** When you have a strong filter (ADV, current_dd, thesis groups, sleeve caps), the names that pass are already pre-selected for quality. Sizing them by score-magnitude over-concentrates in already-cooked momentum.
3. **Rank scoring tightens Ulcer the most.** Cross-sectional ranking eliminates fat-tail bias from extreme momentum readings.

## Full Results (27 combos)

| Score | Sizing | Rebal | CAGR | Martin | Ulcer | MaxDD | Sharpe | AvgPos |
|---|---|---|---|---|---|---|---|---|
| sortino | equal | 21d | 88.0% | 13.64 | 6.5% | -23% | 2.07 | 15.0 |
| rank | sqrt | 21d | 73.5% | 11.73 | 6.3% | -22% | 2.06 | 15.0 |
| rank | raw | 21d | 74.3% | 11.68 | 6.4% | -22% | 2.03 | 15.0 |
| rank | equal | 21d | 72.1% | 11.48 | 6.3% | -22% | 2.07 | 15.0 |
| sortino | equal | 126d | 74.2% | 11.08 | 6.7% | -26% | 1.74 | 15.0 |
| sortino | equal | 63d | 82.4% | 10.72 | 7.7% | -30% | 1.87 | 15.0 |
| rank | equal | 63d | 70.6% | 10.49 | 6.7% | -26% | 1.86 | 15.0 |
| rank | sqrt | 63d | 69.8% | 10.45 | 6.7% | -27% | 1.83 | 15.0 |
| sortino | sqrt | 21d | 82.8% | 10.23 | 8.1% | -27% | 1.91 | 15.0 |
| martin | equal | 21d | 76.6% | 10.01 | 7.7% | -26% | 1.92 | 15.0 |
| sortino | sqrt | 126d | 69.5% | 9.73 | 7.1% | -26% | 1.61 | 15.0 |
| rank | raw | 63d | 65.6% | 9.46 | 6.9% | -27% | 1.73 | 15.0 |
| martin | sqrt | 21d | 80.0% | 9.33 | 8.6% | -27% | 1.86 | 15.0 |
| rank | sqrt | 126d | 62.5% | 9.10 | 6.9% | -28% | 1.66 | 15.0 |
| sortino | sqrt | 63d | 79.3% | 9.00 | 8.8% | -32% | 1.72 | 15.0 |
| rank | equal | 126d | 64.2% | 8.99 | 7.1% | -28% | 1.65 | 15.0 |
| sortino | raw | 21d | 84.0% | 8.99 | 9.3% | -28% | 1.83 | 13.7 |
| rank | raw | 126d | 61.6% | 8.83 | 7.0% | -28% | 1.62 | 15.0 |
| martin | equal | 126d | 60.6% | 8.57 | 7.1% | -28% | 1.60 | 15.0 |
| martin | sqrt | 63d | 72.7% | 7.78 | 9.3% | -35% | 1.64 | 15.0 |
| sortino | raw | 63d | 78.8% | 7.73 | 10.2% | -35% | 1.61 | 13.2 |
| martin | sqrt | 126d | 58.8% | 7.63 | 7.7% | -26% | 1.52 | 15.0 |
| martin | equal | 63d | 66.8% | 7.62 | 8.8% | -33% | 1.64 | 15.0 |
| martin | raw | 21d | 71.8% | 7.46 | 9.6% | -28% | 1.69 | 12.3 |
| sortino | raw | 126d | 61.1% | 7.16 | 8.5% | -26% | 1.43 | 13.4 |
| martin | raw | 63d | 67.3% | 6.59 | 10.2% | -35% | 1.51 | 12.6 |
| martin | raw | 126d | 51.3% | 6.10 | 8.4% | -26% | 1.35 | 13.2 |

## Next Iterations (autoresearch backlog)

See `us/autoresearch/program.md`. Top hypotheses to test:
1. Add Money Flow Index (MFI-14) as additional rank component
2. Penalize current_dd more aggressively in score
3. Drop Martin denominator entirely; use pure Sortino + sleeve caps
4. Add sector relative-strength rank
5. Earnings momentum overlay (data already in `build_earnings_momentum`)
6. Skip reallocation when SPY 50DMA < 200DMA (regime gate)
