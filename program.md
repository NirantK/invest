# autoresearch — momentum strategy optimization

This is an experiment to have an LLM autonomously improve momentum-based portfolio allocation strategies across two completely separate pools of capital.

## The two portfolios (NO cross-market capital movement)

| | US Portfolio | India Portfolio |
|---|---|---|
| **Capital** | $50,000 USD | ₹200,00,000 (~$200K equiv) |
| **Account** | IBKR C-Corp | Indian demat + MF platforms |
| **Instruments** | US equities, ETFs | Indian MFs (direct plans), equities |
| **Tax** | 21% flat C-Corp on all realized gains | 20% STCG (<1yr), 12.5% LTCG (>1yr, above ₹1.25L) |
| **Costs** | IBKR commissions + spread | 1% exit load (<1yr), zero commission on MFs |
| **Currency** | USD | INR |
| **Can move money between?** | **NO** | **NO** |

**CRITICAL:** These two pools are completely separate. No LRS, no forex, no wire transfers — the paperwork isn't worth it. Optimize each independently. The only cross-market exposure is via India FoFs (see below).

### India's bridge to international: Fund of Funds (FoF)

The India portfolio can access international equity **without** moving money abroad, via FoFs:
- **Nasdaq 100 FoFs** (Motilal Oswal, ICICI Pru, etc.)
- **S&P 500 index FoFs**
- **US equity FoFs** / **Global equity FoFs**
- **Emerging market FoFs**

These are already in the `INDIA_MF_QUERIES` list in backtest.py. FoFs are the **zero-friction instrument** for cross-market exposure:
- No forex conversion needed (invest in INR, fund handles USD conversion internally)
- No LRS limit consumption
- Same tax treatment as domestic MFs (20% STCG, 12.5% LTCG)
- FoF structure handles foreign withholding tax internally
- **Trade-off**: ~0.5-1% higher expense ratio than direct US investment (embedded in NAV)

The optimizer should discover when international FoFs beat domestic Indian equity on momentum and allocate accordingly. This is the India portfolio's key advantage — ₹2Cr can access global markets without paying wire/forex costs.

**US portfolio has no equivalent bridge** — there's no low-cost instrument at IBKR to get Indian equity exposure. So the US portfolio stays US/global-only.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar15`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current branch.
3. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `CLAUDE.md` — investment thesis, constraints, ticker universe rationale.
   - `us/scripts/data_utils.py` — fixed data fetching, caching, earnings. **Do not modify.**
   - `us/scripts/backtest.py` — the file you modify. Signals, scoring, parameter grid, cost model, scenarios.
4. **Verify data exists**: Run both markets to confirm baseline works:
   ```bash
   uv run python us/scripts/backtest.py --top 5 --period max --workers 8 --market us
   uv run python us/scripts/backtest.py --top 5 --period max --workers 8 --market india
   ```
   Use `--period max` for maximum walk-forward folds.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Domain context

### US Portfolio ($50K) — 100-ticker multi-theme momentum
- IBKR C-Corp account, 21% flat tax on ALL realized gains (no long/short distinction)
- **100 tickers** across: precious metals (WPM, FNV, AEM, RGLD, GOAU, SGDM), energy (XOM, CVX, COP, midstream), industrial metals (COPX, URA, PPLT, COPP), LatAm (ILF, NU), factor ETFs (QVAL, QMOM, AVUV, AVDV, IMTM), AI infra (BE, CORZ, IREN, COHR), FANG+ (META, NVDA, TSLA, AVGO), Nifty IT ADRs (INFY, WIT, TCS.NS), Bitcoin (MSTR), software (CSU.TO)
- Safe-haven assets: GLD, SLV, IAU, SGOV, SHV, BIL for dual-momentum risk-off
- 1099 C-corps only (no K-1 MLPs)
- IBKR commissions + bid-ask spread as transaction costs

### India Portfolio (₹2Cr) — 255-scheme MF momentum with international FoF access
- **255 mutual fund schemes** (direct growth plans) via mfapi.in, sourced from 65 category queries
- **75 named schemes** in `us/data/mf_scheme_names.json` for human-readable output
- Universe spans 9 categories:
  - **Core equity**: flexi/large/mid/small/multi cap, focused funds (7 queries)
  - **Factor/smart-beta**: alpha, low-vol, momentum, quality, value, dividend yield, equal weight, quant (8 queries)
  - **Index funds**: Nifty 50/Next 50/Midcap 150/Smallcap 250, Sensex, Nifty 500 (6 queries)
  - **Sector/thematic**: banking, pharma, IT, infra, consumption, manufacturing, energy, PSU, defence, realty, etc. (19 queries)
  - **International FoFs**: Nasdaq 100, S&P 500, US equity, global, China, EM (7 queries)
  - **Commodities**: gold, silver, commodities (3 queries)
  - **Hybrid/safe-haven**: liquid, gilt, overnight, money market, balanced advantage, multi-asset (8 queries)
  - **Tax saver**: ELSS (1 query)
- Tax: 20% STCG (<1yr rebal), 12.5% LTCG (>1yr, above ₹1.25L exemption)
- Costs: 1% exit load (<1yr), zero commissions, STT 0.1% on buy+sell
- NAV-based execution (no spread, end-of-day pricing only)
- **MF NAVs already include expense ratios** (deducted daily from NAV)
- Survivorship-bias mitigation via mfapi.in (AMFI source retains defunct/merged schemes)
- `india/scripts/fetch_etf_data.py` provides dual-source fetching (yfinance + mfapi) with scheme chain stitching for ETFs

**What you're optimizing (per market):**
- A walk-forward backtest that sweeps thousands of parameter combos
- Each combo: lookback windows × weight schemes × signal modifiers × position counts × rebalance frequencies
- The strategy scores tickers/schemes by momentum (6 flavors), applies filters, selects top-N

**Key constraints (do NOT violate):**
- All returns must be AFTER costs and taxes
- Walk-forward validation only — no in-sample snooping
- Cannot compare absolute USD returns vs INR returns — use risk-adjusted metrics
- Each market must independently improve or at least not regress

## What matters (ranked)

### Pain philosophy: duration, not depth

Humans live in linear time. A sharp 50% crash that recovers in 3 weeks is a bad week. A slow 15% grind that lasts 18 months is existential dread — you question the thesis, lose sleep, and eventually capitulate at the worst moment. **Max drawdown is a poor proxy for lived pain. Duration is what breaks people.**

There is no hard DD cutoff. A strategy with -60% max DD that always recovers within a month may be preferable to one with -25% max DD that stays underwater for 2 years. The metrics should reflect this:

1. **Absolute after-tax return × UPI** (PRIMARY — you want to be RICH with quick-recovery drawdowns, not safe and poor. A strategy making 4% with UPI=470 is useless. A strategy making 40% with UPI=5 is great. Multiply return × UPI to reward BOTH.)
2. **Best profit after tax** (absolute OOS return — the whole point is to make money)
3. **UPI / Martin ratio** (return / Ulcer Index — penalizes long painful drawdowns. But ONLY meaningful when returns are high. UPI on a money market fund is meaningless.)
4. **Ulcer Index** (lower = better — but only compare Ulcer Index WITHIN strategies that have annualized return > 15%)
5. **Calmar ratio** (return / max drawdown)
6. **Sortino ratio** (risk-adjusted using downside vol)
7. **Max drawdown** (informational only — NOT a hard constraint)

**The goal: make a LOT of money with drawdowns that recover quickly. Not one or the other — BOTH.**

A strategy with +40% annualized and UPI=5 beats a strategy with +4% annualized and UPI=470 every day of the week. The liquid fund that never drops is not a momentum strategy — it's a parking lot.

When comparing experiments:
- Primary: best annualized return among configs with UPI > 3 (filters out strategies that recover too slowly)
- Secondary: best UPI among configs with annualized return > 15% (filters out parking-lot strategies)
- Tertiary: absolute OOS return, Calmar, Sortino
- Also track: win rate across folds, Ulcer Index

### Correctness above performance

A backtest that shows +200% but has a data leak is worthless. Correctness is non-negotiable:
- **No look-ahead bias**: signals must use only data available BEFORE the decision point
- **No survivorship bias**: be skeptical of short-history tickers dominating rankings
- **Realistic costs**: all returns must be after commissions, spreads, and taxes
- **Walk-forward only**: no in-sample fitting, no peeking at future folds
- **Verify anomalies**: any single-fold return >100% or <-50% should be investigated, not celebrated
- **Data quality checks**: NaN, inf, >20% single-day returns, holiday gaps — clip or flag, don't trust
- When in doubt, the more conservative assumption is correct

## Experimentation

**Time budget:** Use `--period max` and `--workers 8`. More data = more folds = more robust walk-forward validation. If a single run exceeds 30 minutes, kill it.

**What you CAN do:**
- Modify `us/scripts/backtest.py` — this is the only file you edit. Everything is fair game:
  - New momentum signal functions (new flavors beyond the 6 existing ones)
  - New signal modifiers (new quality filters, regime detection, etc.)
  - Modified scoring logic (how signals combine into a final score)
  - New parameter grid entries (lookback combos, weight schemes, rebal frequencies)
  - Improved position weighting (beyond equal-weight and inverse-vol)
  - Better cost model (more realistic slippage, tax-loss harvesting)
  - New scenario analyses that surface useful insights
  - Pruning logic improvements (smarter runtime parameter elimination)
  - Ticker universe changes (add/remove tickers with rationale)
  - Market-specific signal tuning (e.g., different lookbacks for India MFs vs US ETFs)

**What you CANNOT do:**
- Modify `us/scripts/data_utils.py`. It is read-only. Contains data fetching, caching, earnings.
- Install new packages beyond what's in `pyproject.toml` (numpy, pandas, click, rich, yfinance, httpx).
- Introduce look-ahead bias (using future data in scoring decisions).
- Remove the walk-forward validation structure (no in-sample-only results).
- Remove the transaction cost model.
- Move capital between markets in the optimization (they are independent).

**DATA IS NOT PRISTINE — defend against:**
- **NaN/inf prices**: yfinance returns NaN for delisted tickers, missing days, corporate actions. India MF NAVs have gaps on holidays. Always use `np.nan_to_num()` after any division or log.
- **Survivorship bias**: Some tickers in the universe may have been added AFTER they already performed well. Be skeptical of short-history tickers dominating rankings.
- **Split/dividend artifacts**: yfinance adjusted close can have jumps on ex-dates. The `build_total_return()` in data_utils handles this, but momentum signals computed on raw price ratios can still spike on corporate action days.
- **Stale prices**: Commodity ETFs with low volume (PPLT, URNJ) may have stale prices on low-volume days. Don't trust single-day returns > 20% without verification.
- **India MF NAV quirks**: NAVs are end-of-day only, no intraday. Holiday gaps can create artificial momentum spikes. `fetch_all_mf_numpy()` forward-fills, but lookback windows that straddle long holiday gaps (Diwali week) will see compressed returns.
- **India FoF NAV lag**: International FoFs (Nasdaq 100, S&P 500) reflect the underlying with a 1-day lag due to time zones + NAV computation. Momentum signals on these will be slightly stale vs real-time US prices.
- **Currency effects**: India MFs are INR-denominated. US tickers are USD. Do NOT compare absolute returns across markets — compare risk-adjusted metrics (Calmar, UPI, Sortino) which are currency-neutral.
- **Earnings data quality**: Not all tickers have earnings data on yfinance. `build_earnings_momentum()` returns NaN for missing data. The `use_earnings` signal flag should gracefully handle this. India MFs have no earnings data — this signal is US-only.
- **General rule**: If a signal produces inf, NaN, or returns >1000%, the data is bad. Clip, don't trust.

**Simplicity criterion**: All else being equal, simpler is better. A marginal improvement that adds 50 lines of complex signal logic is not worth it. Removing a signal that doesn't help is a great outcome.

**The first run**: Your very first run should always establish the baseline for BOTH markets, so run the script as-is.

## Output format

The script prints multiple scenario tables via Rich. The key metrics to extract:

```bash
# Extract the summary line
grep -A3 "^Summary" run_us.log
grep -A3 "^Summary" run_india.log

# Or look for survivable count
grep "Survivable" run_us.log
grep "Survivable" run_india.log
```

Since Rich tables have ANSI codes, also look at the structured data:
- "RISK TIERS" table for best annualized at each DD cap
- "BEST UPI" table for duration-aware pain-adjusted returns
- "SLEEP AT NIGHT" for DD ≤ 30% configs
- "Signal dominance" section for which signals matter

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated).

**Log TWO rows per experiment** — one for US, one for India.

The TSV has a header row and 11 columns:

```
commit	market	best_calmar	best_upi	best_abs_ret_pct	best_sortino	n_survivable	worst_dd_pct	ulcer_index	status	description
```

1. git commit hash (short, 7 chars)
2. market: `us` ($50K) or `india` (₹2Cr)
3. best Calmar among survivable configs (DD ≤ 50%)
4. best UPI (Martin ratio = ann_return / ulcer_index) — duration-aware pain metric
5. best absolute OOS return % (after tax)
6. best Sortino among survivable configs
7. count of survivable configs
8. worst DD % of the best config
9. Ulcer Index of the best config (lower = less time underwater)
10. status: `keep`, `discard`, or `crash`
11. short text description

Example:

```
commit	market	best_calmar	best_upi	best_abs_ret_pct	best_sortino	n_survivable	worst_dd_pct	ulcer_index	status	description
a1b2c3d	us	3.44	2.15	171.0	3.83	74874	-38.5	18.2	keep	baseline 5y ($50K)
a1b2c3d	india	2.80	1.90	95.0	2.40	5200	-32.0	15.1	keep	baseline 5y (₹2Cr)
b2c3d4e	us	3.91	2.52	185.3	4.01	76000	-35.2	16.8	keep	add mean-reversion for gold
b2c3d4e	india	2.80	1.90	95.0	2.40	5200	-32.0	15.1	discard	no change for India MFs
```

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar15`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Tune `us/scripts/backtest.py` with an experimental idea by directly hacking the code.
3. git commit
4. Run the experiment for BOTH markets:
   ```bash
   uv run python us/scripts/backtest.py --top 5 --period max --workers 8 --market us > run_us.log 2>&1
   uv run python us/scripts/backtest.py --top 5 --period max --workers 8 --market india > run_india.log 2>&1
   ```
   Or use the wrapper: `uv run evaluate.py --period max --workers 8 > run.log 2>&1`
5. Read out the results: `tail -80 run_us.log` and `tail -80 run_india.log`
6. If the output is empty or shows a Python traceback, the run crashed. Run `tail -n 50 run_us.log` and attempt a fix.
7. Record results in the TSV (TWO rows: one `us`, one `india`)
8. Apply the keep/discard rule (see below)

**Keep/discard rule (each market judged independently):**
- US and India are separate optimization problems — judge each on its own merits
- If a change improves one market and doesn't affect the other → keep
- If a change improves one but breaks the other → keep only for the market it helps (revert the other if needed)
- If both are unchanged or worse → discard, git reset back

**Comparison rule per market:** An experiment is "better" for a market if:
- Best annualized return among configs with UPI > 3 improved (high return + tolerable pain), OR
- Returns stayed the same but UPI improved (same money, less pain), OR
- Both stayed the same but Calmar or Sortino improved

**Correctness check:** Before declaring improvement, verify:
- No single-fold return > 200% (investigate if so — likely data artifact)
- No NaN or inf in results
- Configs with ann. return > 15% and UPI > 3 actually exist (not just edge cases)
- Sanity check: does the strategy make economic sense?

**Timeout**: ~10 min per market, ~20 min total per experiment. If a run exceeds 20 minutes, kill it.

**Crashes**: If a run crashes, use your judgment. Typos → fix and re-run. Fundamentally broken idea → skip, log "crash", move on.

**NEVER STOP**: Once the experiment loop has begun, do NOT pause to ask the human. The human may be asleep. You are autonomous. If you run out of ideas, think harder:
- Read academic finance papers referenced in the code comments (AQR, Alpha Architect)
- Try combining signals that individually didn't help
- Try removing signals to simplify
- Try different ticker universes (tech-heavy, energy-heavy, broad market)
- Try asymmetric lookback weights (overweight recent momentum)
- Try regime-adaptive signals (different params for high-vol vs low-vol)
- Try alternative risk metrics (CVaR, Omega ratio)
- Try smarter position sizing (Kelly criterion, risk parity)

## Research ideas backlog

Here are concrete ideas to try, roughly ordered by expected impact:

### Signal improvements
1. **Momentum crash filter**: Skip assets with 1-month return < -20% (catching knives)
2. **Cross-sectional momentum**: Rank vs peer group, not absolute (relative strength)
3. **Mean-reversion overlay**: For gold/silver, add short-term mean reversion (5-day RSI < 30 = boost)
4. **Earnings surprise momentum**: Weight recent earnings surprises more heavily (US only)
5. **Sector momentum**: Score entire sectors, then pick best within best sectors
6. **Correlation-aware selection**: Penalize correlated holdings to improve diversification

### India-specific ideas
7. **FoF vs domestic rotation**: When Indian equity momentum is weak, rotate to international FoFs (Nasdaq 100, S&P 500). This is the key advantage of the India portfolio — international diversification without moving money.
8. **LTCG optimization**: For India, prefer rebalance frequencies ≥ 252 days to get 12.5% LTCG rate instead of 20% STCG. The cost model should capture that longer holding periods save 7.5% tax.
9. **Exit load avoidance**: Prefer holding periods > 1 year to avoid the 1% exit load on MF redemptions.
10. **NAV lag exploitation**: India international FoFs reflect US markets with 1-day lag. The momentum signal may be stale — try shorter lookbacks for FoFs.

### Parameter space
11. **Adaptive lookbacks**: Use recent volatility to adjust lookback window dynamically
12. **Non-linear weight decay**: Exponential decay on lookback weights instead of fixed
13. **Dynamic position count**: More positions in high-vol (diversify), fewer in low-vol (concentrate)
14. **Market-specific grids**: Different parameter ranges for US vs India (e.g., Indian MFs may favor longer lookbacks due to lower liquidity)

### Cost/execution
15. **Tax-loss harvesting**: Allow selling losers before year-end even if momentum is positive (US C-Corp)
16. **Partial rebalancing**: Only trade if position is >5% off target (reduce turnover)
17. **Urgency-based execution**: Skip rebalance if signals are weak (low conviction threshold)
18. **Holding period optimization**: Model the tax savings of holding > 1 year in India (STCG 20% → LTCG 12.5%)

### Architecture
19. **Two-stage scoring**: First filter (hard cutoffs), then score (continuous ranking) — currently mixed
20. **Ensemble scoring**: Average scores from multiple lookback configs for robustness
21. **Walk-forward with expanding window**: Compare fixed vs expanding training window
22. **Separate parameter grids per market**: The same grid runs for both markets, but maybe US favors different combos than India. Consider market-conditional parameter ranges.
