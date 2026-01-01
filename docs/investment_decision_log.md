# US Portfolio Investment Decision Log

## Executive Summary

This document captures the complete decision-making process for allocating $60,000 in US equities through a C-Corp structure. Over multiple sessions, we evolved from a simple thesis-driven approach to a systematic, data-driven allocation using Sortino-weighted momentum with drawdown analysis.

**Final Allocation (3% Min / 15% Max / 33% Sector Caps):**

| Ticker | Allocation | Weight | Category | Sector |
|--------|------------|--------|----------|---------|
| PAAS | $9,000 | 15.25% | Precious Metals (Miner) | Silver |
| HL | $9,000 | 15.25% | Precious Metals (Miner) | Silver |
| AVDV | $7,000 | 11.86% | Ex-US Value | International |
| DFIV | $7,000 | 11.86% | Ex-US Value | International |
| AEM | $6,000 | 10.17% | Precious Metals (Miner) | Gold |
| WPM | $5,000 | 8.47% | Precious Metals (Streamer) | Mixed 50/50 |
| IVAL | $5,000 | 8.47% | Ex-US Value | International |
| XOM | $4,000 | 6.78% | Energy | Oil & Gas |
| SU | $4,000 | 6.78% | Energy | Oil & Gas |
| FNV | $3,000 | 5.08% | Precious Metals (Streamer) | Gold |
| MSTR | $100/mo DCA | - | Bitcoin Proxy | Digital Assets |

**Category Breakdown:**
- Precious Metals: $32,000 (54.2%) - HL/PAAS (silver), AEM/FNV (gold), WPM (50/50)
- Ex-US Value: $19,000 (32.2%) - AVDV/DFIV/IVAL
- Energy: $8,000 (13.6%) - XOM (US integrated), SU (Canadian integrated)
- Bitcoin (DCA): $100/mo

**Sector Caps (33% maximum each):**
- Silver (PAAS + HL): 30.5% ✓
- Gold (AEM + FNV): 15.3% ✓
- Mixed Precious (WPM): 8.5% ✓
- Oil & Gas (XOM + SU): 13.6% ✓
- Ex-US Value (AVDV + DFIV + IVAL): 32.2% ✓

---

## Part 1: Initial Context & Constraints

### Investor Profile
- **Entity:** US C-Corp (21% flat tax on all income)
- **Investment Horizon:** 3 years
- **Volatility Tolerance:** High (comfortable with -20% drawdowns)
- **Monitoring Cadence:** Quarterly
- **Behavioral Edge:** Ability to hold through drawdowns without panic selling

### Capital Constraints
- **Total US Investable:** $80,000 (over 18 months)
- **Minimum Cash Buffer:** $20,000 (working capital)
- **Maximum Deployable:** $60,000
- **DCA Approach:** Monthly deployment over 3 months

### Existing INR Portfolio Context
- **Total INR Portfolio:** ₹2.48 crore (~$27,559 at ₹89.99/USD)
- **Existing Precious Metals (INR):** $8,026 (SGB, Gold ETF, Silver ETF)
- **Heavy Indian Banking Exposure:** PSU banks, financials
- **Momentum Factor Tilt:** 13.5% in Nifty 200 Momentum 30

---

## Part 2: Investment Thesis Evolution

### Original Thesis

#### Oil/Energy as India Hedge
- India imports 88%+ of crude oil
- $10/barrel increase → $12-13B higher import bill → CAD widens 0.3% of GDP
- Oil spike → INR depreciation → US energy positions profit
- Rick Rule thesis: $2B/day in deferred sustaining capex → supply crunch by 2027-2028

#### Precious Metals Thesis
- Gold target: $4,000+
- Silver target: $50+
- Streamers preferred over physical for operating leverage
- Streamers eliminate operational risk (no mining costs, diversified across 100+ mines)

#### Bitcoin Thesis
- 5% target allocation
- Cannot hold Bitcoin ETF directly (IB account balance too low)
- Proxy via MSTR (Strategy Inc)

### How the Thesis Evolved

**Original Position:** Fixed allocations to streamers (WPM, FNV) as "core" with satellites rotating.

**Evolution:** Let ALL securities compete on pure Sortino basis. The data showed:
1. Miners (HL, PAAS) had stronger momentum than streamers
2. FNV's negative 3-month momentum (-4.72%) hurt its score despite positive 6-month
3. Energy (XOM, XLE) had weak momentum signals vs precious metals
4. Ex-US Value ETFs provided crucial diversification with lower drawdowns

---

## Part 3: Major Decisions & Turning Points

### Decision 1: Venture Debt Rejection

**Context:** Offered $50,000 minimum at 18-25% XIRR, 18-month term from India-based counterparty expanding within Workday SaaS ecosystem by acquiring a US Delaware C-Corp.

**Analysis:**
- Estimated loss probability: 5-15%
- Expected value: 0.85 × 21.5% + 0.15 × (-100%) = +3.28% expected return
- But: Single counterparty concentration (83% of deployable capital)

**Decision:** SKIP
- No thesis expression (oil/metals/BTC)
- Illiquid for 18 months
- Public markets offer similar upside with diversification and liquidity

### Decision 2: From Fixed Allocations to Pure Competition

**Original Approach:** Fixed 30% precious metals cap, fixed energy allocation.

**Problem Identified:** Initial allocation was called "garbage" - too simplistic, forced energy even when momentum was weak.

**New Approach:** All securities compete on Sortino basis. Categories tracked for reporting only, no caps enforced.

**Result:** Energy got 0% allocation because XOM score (0.59) and XLE score (0.19) couldn't compete with precious metals scores (HL: 3.90, PAAS: 1.83).

### Decision 3: Adding Ex-US Value Competition

**Question Asked:** "Is energy backed by momentum signal, or simply lack of alternatives?"

**Action:** Added Ex-US Value ETFs to compete fairly:
- AVDV (Avantis International Small Cap Value)
- DFIV (DFA International Value)
- IVAL (Alpha Architect Intl Quant Value)
- EFV (iShares MSCI EAFE Value) - later dropped

**Outcome:** Ex-US Value earned ~32% of allocation through legitimate score competition.

### Decision 4: Minimum Position Threshold

**Problem:** With pure Sortino competition, many positions fell below meaningful size.

**Evolution:**
- Started at 10% minimum → only 2 positions (HL, PAAS)
- Tested 5-9% range
- Settled on 5% → 7 positions with good diversification

**Trade-off Analysis:**

| Threshold | Positions | Max Drawdown | Risk-Reward |
|-----------|-----------|--------------|-------------|
| 5% | 7 | -33.4% | 3.09 |
| 7% | 6 | -34.5% | 3.21 |
| 10% | 2 | -37.0% | 2.83 |

### Decision 5: Momentum Weighting Change

**Original:** 6-month momentum only, normalized by Sortino ratio.

**Revised:** Equally weight 3-month and 6-month momentum, normalized by downside volatility.

**Formula:** `Score = (0.5 × mom_3m + 0.5 × mom_6m) / downside_volatility`

**Rationale:** 3-month captures recent trend changes; 6-month captures sustained momentum. Together they're more robust than either alone.

### Decision 6: MSTR Special Treatment

**Problem:** MSTR momentum was deeply negative (-59.63% combined) but thesis remains valid.

**Solution:** Slow DCA at $60/month (0.1% of portfolio) until momentum turns positive, then accelerate.

---

## Part 4: Instruments Considered

### Precious Metals - Streamers/Royalties
| Ticker | Name | Status | Reason |
|--------|------|--------|--------|
| WPM | Wheaton Precious Metals | ✅ INCLUDED | 50% silver streamer, made 5% threshold |
| FNV | Franco-Nevada | ❌ EXCLUDED | Negative 3M momentum (-4.72%), score below threshold |

### Precious Metals - Tier 1 Miners
| Ticker | Name | Status | Reason |
|--------|------|--------|--------|
| HL | Hecla Mining | ✅ INCLUDED | Highest score (3.90), 216% 6M momentum |
| PAAS | Pan American Silver | ✅ INCLUDED | Strong score (1.83), silver exposure |
| AEM | Agnico Eagle | ✅ INCLUDED | Lowest AISC (~$1,275), safe jurisdictions |

### Energy
| Ticker | Name | Status | Reason |
|--------|------|--------|--------|
| XOM | Exxon Mobil | ✅ INCLUDED | Score improved to 0.69 with dividends, earned $4k allocation |
| CVX | Chevron | ❌ EXCLUDED | Score 0.26 below 5% threshold despite ~4% dividend yield |
| XLE | Energy Select Sector SPDR | ❌ EXCLUDED | Score improved to 0.28 with dividends, still below threshold |

### Ex-US Value
| Ticker | Name | Status | Reason |
|--------|------|--------|--------|
| AVDV | Avantis Intl Small Cap Value | ✅ INCLUDED | Strong score (1.20), low drawdown |
| DFIV | DFA International Value | ✅ INCLUDED | Gold standard, score (1.22) |
| IVAL | Alpha Architect Intl Quant Value | ✅ INCLUDED | Made threshold at 5% |
| EFV | iShares MSCI EAFE Value | ❌ EXCLUDED | Dropped - iShares inferior to DFA/Avantis |

### Bitcoin Proxy
| Ticker | Name | Status | Reason |
|--------|------|--------|--------|
| MSTR | Strategy Inc | ✅ SPECIAL DCA | Negative momentum, slow DCA until turns positive |
| COIN | Coinbase | ❌ NOT ADDED | More conservative, thesis favors pure BTC exposure |

### Explicitly Excluded
| Ticker | Category | Reason |
|--------|----------|--------|
| CNQ, ARC, Suncor | Canadian Energy | Adds complexity, XLE sufficient |
| Uranium stocks | Energy | 5-7 year thesis, mismatched with 3-year horizon |
| Copper stocks | Commodities | Correlates with Indian economy, reduces hedge |
| Junior miners | Mining | Require active monitoring, binary risk |
| NEM, GOLD | Large Miners | Poor execution, higher AISC than peers |

---

## Part 5: Ideas Changed by Data

### 1. Streamers vs Miners

**Initial Belief:** Streamers (WPM, FNV) are superior due to operating leverage without operational risk.

**Data Showed:** In the current momentum regime, miners (HL, PAAS) dramatically outperform streamers. HL's 216% 6-month momentum crushed WPM's 30%.

**Conclusion:** Let momentum decide. When miner momentum fades, streamers will naturally take over.

### 2. Energy as Permanent Allocation

**Initial Belief:** Energy should always have allocation as India hedge.

**Data Showed:** XOM (+9% 6M mom) and XLE (+4.5% 6M mom) couldn't compete with precious metals or even ex-US value on risk-adjusted basis.

**Conclusion:** Keep energy in competition, but don't force allocation. When oil thesis plays out, momentum will capture it.

### 3. Concentration vs Diversification

**Initial Belief:** More diversification is always better.

**Data Showed:**
- At 10% threshold: 2 positions, -37% max drawdown, 2.83 risk-reward
- At 5% threshold: 7 positions, -33.4% max drawdown, 3.09 risk-reward

**Conclusion:** Some diversification helps, but extreme diversification dilutes winners. 5% threshold balances both.

### 4. Fixed Category Caps

**Initial Belief:** Need 30% precious metals cap to avoid overconcentration.

**Data Showed:** Pure Sortino competition naturally allocates 68% to precious metals because that's where the best risk-adjusted returns are.

**Conclusion:** Caps are artificial constraints. Let the algorithm decide based on data.

### 5. Drawdown Duration Matters

**Initial Belief:** Focus on volatility and max drawdown percentage.

**Data Showed:** HL has -51% max drawdown BUT 363 days underwater. DFIV has only -15% max drawdown and 95 days underwater.

**Conclusion:** Duration matters for psychology. Ex-US value provides recovery speed even if absolute returns are lower.

---

## Part 6: Risk Analysis

### Portfolio-Level Metrics (3-Year History)
- **Maximum Drawdown:** -28.7%
- **Longest Underwater:** 247 days (~8 months)
- **3-Year Total Return:** +200.6%
- **Annualized Return:** +44.7%
- **Pain Ratio:** 1.99

### 3-Month Forward Distribution (Monte Carlo)

| Percentile | Portfolio Value | Return |
|------------|-----------------|--------|
| 1st (worst) | $45,000 | -25% |
| 5th (VaR 95) | $50,000 | -16% |
| 25th | $59,000 | -2% |
| 50th (median) | $66,000 | +10% |
| 75th | $74,000 | +23% |
| 95th | $88,000 | +46% |

### Probability Analysis
- Probability of any loss: 29%
- Probability of >20% loss: 3%
- Probability of >10% gain: 50%
- Probability of >30% gain: 17%

---

## Part 7: Implementation Plan

### 3-Month DCA Schedule

| Month | WPM | PAAS | AEM | HL | AVDV | DFIV | IVAL | MSTR | Total |
|-------|-----|------|-----|-----|------|------|------|------|-------|
| 1 | $1,300 | $3,300 | $1,700 | $7,300 | $2,300 | $2,300 | $1,700 | $100 | $20,000 |
| 2 | $1,300 | $3,300 | $1,700 | $7,300 | $2,300 | $2,300 | $1,700 | $100 | $20,000 |
| 3 | $1,300 | $3,300 | $1,700 | $7,300 | $2,300 | $2,300 | $1,700 | $100 | $20,000 |
| **After** | Stop | $100/mo | Stop | $200/mo | $100/mo | $100/mo | Stop | $100/mo | ~$600/mo |

### Rebalancing Rules
1. **Quarterly:** Rerun allocation script with fresh momentum data
2. **If momentum turns negative:** Pause DCA for that position
3. **If MSTR momentum turns positive:** Accelerate from $60/mo to full allocation
4. **Threshold:** Keep at 5% minimum for position sizing

---

## Part 8: Code Artifacts

### Scripts Created
1. `nbs/us_portfolio_allocation.py` - Main allocation script with click CLI
2. `nbs/portfolio_simulation.py` - Monte Carlo simulation for 3-month outlook

### Key Parameters
```python
TOTAL_CAPITAL = 60_000
MIN_ALLOCATION_PCT = 0.05  # 5% minimum
LOOKBACK_3M = 63   # ~3 months trading days
LOOKBACK_6M = 126  # ~6 months trading days
DCA_MONTHS = 3
BITCOIN_MONTHLY_DCA_PCT = 0.001  # 0.1% for MSTR
```

### Running the Scripts
```bash
# Get allocation at 5% threshold
uv run python nbs/us_portfolio_allocation.py --min-allocation 0.05

# Run Monte Carlo simulation
uv run python nbs/portfolio_simulation.py
```

---

## Part 9: Open Questions & Future Work

1. **Correlation Analysis:** How correlated are HL and PAAS? Should we limit combined exposure?

2. **Regime Detection:** Can we detect when precious metals momentum is fading before it shows in 3-month data?

3. **Tax-Loss Harvesting:** With C-Corp structure, when should we harvest losses?

4. **Rebalancing Frequency:** Is quarterly optimal, or should we use momentum-triggered rebalancing?

5. **MSTR Threshold:** At what momentum level should we accelerate MSTR DCA?

---

## Part 10: Impact of Total Returns (Dividends Included)

### Decision 7: Accounting for Dividend Yields

**Context:** Initial analysis used only price returns, ignoring dividend income. With 21% flat C-Corp tax, dividends are taxed identically to capital gains, making total return the correct metric.

**Energy Stock Dividend Yields:**
- XOM: ~3.5% annual yield
- CVX: ~4.0% annual yield
- XLE: ~3.0% annual yield

**Score Improvements with Dividends Included:**

| Ticker | Price-Only Score | Total Return Score | Improvement |
|--------|------------------|-------------------|-------------|
| XOM | 0.59 | 0.69 | +17% |
| CVX | N/A (not included) | 0.26 | Added back |
| XLE | 0.19 | 0.28 | +47% |

**Allocation Impact:**
- **Before (price-only):** Energy = $0 (0%)
- **After (total return):** Energy = $4,000 (6.7%) via XOM
- CVX and XLE still below 5% threshold but now compete fairly

**Key Insight:** Dividends matter significantly for energy stocks. XLE's score improved 47%, and XOM now earns allocation. However, precious metals momentum is so strong that even with dividends, energy remains a small allocation.

**Implication for Tax Strategy:** The 21% flat rate means no need to prefer capital gains over dividends. Focus purely on total after-tax return, which this analysis now captures correctly.

---

## Part 11: The Canadian High-Yield Detour

### The Search for 7%+ Dividend Yields

**Context:** After seeing energy stocks provide modest yields (XOM 3.4%, CVX 4.5%), we explored Canadian oil & gas companies rumored to offer 7%+ yields.

**Canadian High-Yield Candidates Found:**

| Ticker | Company | Yield | Exchange | Type |
|--------|---------|-------|----------|------|
| IPOOF | InPlay Oil | 10.11% | OTC | Small producer |
| ZPTAF | Surge Energy | 7.50% | OTC | Small producer |
| CRLFF | Cardinal Energy | 7.00% | OTC | Small producer |
| PTRUF | Petrus Resources | 7.00% | OTC | Small producer |
| WCPRF | Whitecap Resources | 6.22% | OTC | Mid-size producer |

**NYSE-Listed Canadian Comparison:**

| Ticker | Company | Yield | Exchange |
|--------|---------|-------|----------|
| ENB | Enbridge | 5.60% | NYSE |
| CNQ | Canadian Natural Resources | 5.10% | NYSE |
| TRP | TC Energy | 4.50% | NYSE |
| SU | Suncor Energy | 4.00% | NYSE |

**Analysis Outcome:**
- Highest yield: IPOOF at 10.11%
- On $4,000 allocation: ~$400/year dividend income vs ~$136 from XOM
- Delta: +$264/year benefit

**Decision:** "This entire composition is kind of pointless. The highest yield I'm able to get is a couple hundred dollars. It's not worth the extra effort."

**Rationale:**
1. **Scale Problem:** $264/year extra income on $60,000 portfolio = 0.44% yield pickup
2. **Operational Complexity:** OTC trading, smaller companies, less liquidity
3. **Risk Adjustment:** Small Canadian producers have higher business risk than XOM
4. **Tax Benefit Dilution:** With 21% C-Corp rate, after-tax pickup is only $208/year
5. **Thesis Purity:** "Let's stick to the simplest, cleanest portfolio"

**Key Lesson:** Don't chase yield for yield's sake. The juice wasn't worth the squeeze when accounting for scale, risk, and complexity.

---

## Part 12: Comprehensive Oil & Gas Sector Analysis

### Expanding the Energy Universe

**Motivation:** After rejecting Canadian high-yield, we cast a wider net across ALL US-listed oil & gas segments to find the best energy exposure.

**Segments Analyzed (26 stocks):**

**Integrated Majors:**
- XOM, CVX (US majors)
- CNQ, SU, CVE (Canadian majors)

**Midstream/Pipelines:**
- ENB, TRP (Canadian C-corps)
- KMI, WMB, OKE (US C-corps, converted from MLPs)
- EPD, ET, MPLX (still MLPs, K-1 issuers)

**Refiners:**
- VLO, PSX, MPC, DINO

**E&P (Exploration & Production):**
- COP, DVN, OXY

**Royalty Companies:**
- VNOM, BSM, DMLP, KRP (all K-1 issuers)

**Energy ETF:**
- XLE (broad energy sector exposure)

**Key Findings:**

**Best 7%+ Yield with Strong Score:**
- MPLX: 7.9% yield, score 1.18 (highest in energy)
- Problem: MLP structure, issues K-1 instead of 1099

**MLPs vs C-Corps Trade-off:**
- MLPs offer higher yields (MPLX 7.9%, EPD 6.8%, ET 8.0%)
- But K-1 tax forms create:
  - Multi-state filing requirements
  - UBTI concerns
  - Cannot e-file early in tax season
  - Accounting fees often exceed yield benefit on small positions

**Decision:** Exclude ALL K-1 issuers, even MPLX with its strong score

**Result:** XOM emerged as best 1099 energy stock (score 0.69), with SU as second-best (score 0.60)

---

## Part 13: Constraint Optimization & The Concentration Paradox

### The Equal-Weight Problem

**Initial Attempt:** 5% minimum, 12% maximum constraints on 12-stock universe

**Result:** All 8 positions converged to equal 12.5% weights
- HL wanted 30.4% but capped at 12%
- Excess redistributed across remaining stocks
- Mathematical inevitability pushed everything to maximum

**User Feedback:** "Wait, what? OK, let's start from the top. Within this, there should be stocks which are below 12% as well. I don't need to max out on all of them."

**Key Insight:** Constraints were creating false equivalence. We needed score-based differentiation WITHIN the constraint bounds.

### Test 1: Lower Minimum to 1%, Raise Maximum to 12%

**Hypothesis:** Lower minimum allows more stocks to survive, higher maximum allows top performers to capture more capital.

**Universe:** Expanded from 12 to 35 stocks (all oil/gas segments + precious metals + ex-US value)

**Result:**
- 22 positions active (out of 27 passing momentum filter)
- Score-based differentiation achieved: PAAS/HL at 11.5%, down to 6 positions at 1.6%
- Energy allocation: $5,000 (8.3%) across XOM, CVX, CNQ, XLE, etc.

**Risk Metrics:**
- Risk-reward ratio: 2.25
- Weighted 6M momentum: +47.4%
- Weighted max drawdown: -26.7%

**Problem:** Too many small positions (22 total). Fragmented allocation dilutes conviction.

### Test 2: Raise Minimum to 5%, Maximum to 15%

**Hypothesis:** Higher minimum eliminates weak positions, forces concentration in winners.

**Result:**
- Only 6 positions survived (PAAS, HL, MPLX, AVDV, DFIV, IVAL)
- Each at ~16.67% (equal weights due to redistribution)
- **Energy allocation: $0 (0%)** - XOM completely eliminated!

**Risk Metrics:**
- Risk-reward ratio: 2.86 (best yet!)
- Weighted 6M momentum: +60.3%
- Weighted max drawdown: -23.8%

**Problem:**
- Eliminated ALL energy stocks - thesis not expressed
- No XOM despite being core to oil thesis
- User wanted FNV, CVX, XLE included but all zeroed out

**User Reaction:** "But why are we removing Franco Nevada, CVX, and Excel? Include them."

### The Concentration Paradox Revealed

**Discovery:** Higher concentration improves risk-adjusted returns BUT eliminates entire sectors.

**Summary of Tests:**

| Config | Positions | Risk-Reward | Energy | Precious Metals | Ex-US Value |
|--------|-----------|-------------|--------|-----------------|-------------|
| 1% min, 12% max | 22 | 2.25 | $5k (8.3%) | $22k (36.7%) | $14k (23.3%) |
| 5% min, 15% max | 6 | 2.86 | $0 (0%) | $20k (33.3%) | $30k (50%) |
| **3% min, 15% max, 33% caps** | **10** | **2.37** | **$8k (13.6%)** | **$32k (54.2%)** | **$19k (32.2%)** |

**Key Insights:**
1. **Concentration helps returns:** 6 positions had best risk-reward (2.86)
2. **But creates sector gaps:** Precious metals momentum crowded out ALL energy
3. **Sector caps solve this:** Force diversification while maintaining high conviction in top picks
4. **3% minimum is sweet spot:** Allows XOM/SU in at 6.8% each, maintains differentiation

### Decision 11: Exclude K-1 Tax Complexity

**Problem:** MLPs (Master Limited Partnerships) and royalty trusts issue K-1 forms instead of 1099s:
- MPLX, EPD, ET (energy MLPs)
- BSM, VNOM, DMLP, KRP (royalty partnerships)

**K-1 Complexity:**
- State tax filing requirements across multiple states
- UBTI (Unrelated Business Taxable Income) issues for certain entities
- Cannot be filed electronically early in tax season
- Accounting complexity far exceeds benefit

**Decision:** EXCLUDE all K-1 issuers, keep only 1099 C-corps

**Kept (converted to C-corps, now issue 1099s):**
- KMI (Kinder Morgan)
- WMB (Williams Companies)
- OKE (ONEOK)

**Result:** MPLX removed despite 7.9% yield and strong score. Allocated capital redistributed to other high-momentum stocks.

### Decision 12: Implement Sector Concentration Caps

**Problem:** With 5% minimum threshold, precious metals consumed 55-67% of portfolio, squeezing out ALL energy stocks including XOM.

**Solution:** Implement 33% maximum caps per sector:
- **Gold Sector:** FNV, AEM (gold-primary streamers/miners)
- **Silver Sector:** PAAS, HL (silver-primary miners)
- **Mixed Precious:** WPM (50/50 gold/silver)
- **Oil & Gas:** All energy stocks (XOM, CVX, CNQ, SU, CVE, XLE, pipelines, refiners, E&P)
- **Ex-US Value:** AVDV, DFIV, IVAL

**Rationale:**
1. Force diversification across uncorrelated sectors
2. Prevent any single thesis from dominating
3. Ensure energy exposure even when precious metals have stronger momentum
4. Maintain thesis expression across all original investment ideas

### Decision 13: Optimize Minimum Threshold

**Trade-off Analysis:**

| Minimum | Positions | Energy | Diversification | Risk-Reward |
|---------|-----------|--------|----------------|-------------|
| 5% | 7 | $0 | Too concentrated | 2.34 |
| 3% | 10 | $8,000 | Better balanced | 2.37 |
| 1% | 22 | $5,000 | Too fragmented | 2.25 |

**Decision:** 3% minimum threshold
- Allows XOM ($4k, 6.8%) and SU ($4k, 6.8%) to pass filter
- Maintains concentration in top positions (PAAS/HL at 15%)
- 10 positions provides adequate diversification
- Slightly better risk-reward than more concentrated alternatives

### Final Constraint Set

**Position Constraints:**
- Minimum: 3% ($1,800)
- Maximum: 15% ($9,000)

**Sector Constraints:**
- Maximum: 33% ($19,800) per sector

**Tax Constraints:**
- Only 1099 C-corps (no K-1 issuers)

**Result:** 10-position portfolio with:
- Precious metals across three distinct sectors (gold/silver/mixed)
- Energy via two integrated oil majors (US + Canadian)
- Ex-US value via three complementary ETFs
- Score-based differentiation within constraints (positions range 5.1% to 15.3%)

### Why SU (Suncor Energy)?

**SU Profile:**
- Canadian integrated oil major (similar to XOM/CVX)
- Refining + upstream production
- Score: 0.60 (combined momentum +11.79%, downside vol 19.56%)
- 25-year dividend growth history
- Max drawdown: -20.7% (better than XOM's -17.9%)

**Selection Rationale:**
1. Second-highest score in oil & gas sector after XOM
2. Canadian diversification vs pure US exposure
3. Both fit within 33% oil & gas sector cap ($8,000 total = 13.6%)
4. Geographic diversification (Western Canada Sedimentary Basin vs Permian/shale)

**XOM + SU Logic:**
- Combined $8,000 (13.6%) expresses oil thesis without over-concentration
- 33% sector cap prevents energy from exceeding precious metals or ex-US value
- Two different jurisdictions reduces single-country policy risk
- Both survived 3-year lookback with positive momentum

---

## Summary: Key Learnings & Insights

### 1. Scale Matters More Than Yield

**Learning:** Don't chase high yields on small positions.

**Example:** Canadian high-yield stocks (IPOOF at 10.11% vs XOM at 3.4%)
- Benefit: +$264/year pre-tax on $4,000 position
- After 21% tax: +$208/year
- Trade-off: OTC complexity, higher risk, less liquidity
- **Decision:** Not worth it for 0.35% portfolio yield improvement

**Principle:** On small portfolios, prioritize quality and simplicity over marginal yield pickup.

### 2. The Concentration-Diversification Trade-off

**Learning:** More concentrated = better returns, but can eliminate entire sectors.

**Data:**
- 6 positions: Risk-reward 2.86, but 0% energy exposure
- 22 positions: Risk-reward 2.25, but too fragmented
- 10 positions with sector caps: Risk-reward 2.37, all sectors represented

**Solution:** Sector concentration caps (33% maximum) force diversification while allowing conviction sizing within sectors.

### 3. Tax Structure Drives Everything

**C-Corp at 21% flat rate implications:**
- Dividends taxed same as capital gains → focus on TOTAL return, not yield vs growth
- K-1 complexity costs more than yield benefit → exclude all MLPs
- Multi-state filing avoided → stick to 1099 C-corps

**Result:** Total return index (dividends reinvested) is the correct comparison metric.

### 4. Let the Data Decide, But Set Guard Rails

**Evolution:**
- **Started:** Thesis-driven with fixed allocations (WPM, XOM as "core")
- **Evolved:** Pure Sortino scoring with ALL stocks competing
- **Refined:** Add constraints to prevent unintended outcomes

**Guard Rails Needed:**
1. Position minimum (3%) - eliminate noise
2. Position maximum (15%) - prevent over-concentration in single stock
3. Sector maximum (33%) - ensure thesis diversification
4. Tax filter (1099 only) - avoid operational complexity

**Philosophy:** Trust the math, but add constraints that encode non-financial preferences (diversification, simplicity, tax efficiency).

### 5. Momentum Overwhelms Fundamentals (Short-Term)

**Observation:** Over 3-year lookback, HL (silver miner) scored 3.90 vs XOM (oil major) at 0.69.

**Why:**
- HL: +137.9% combined momentum despite -50.9% max drawdown
- XOM: +10.6% combined momentum, only -17.9% max drawdown
- Silver momentum crushed oil momentum in 2023-2025 period

**Implication:** This allocation is SPECIFIC to current momentum regime. Will need quarterly rebalancing as momentum shifts.

**Risk:** If precious metals reverse, this portfolio will underperform. Sector caps limit this risk but don't eliminate it.

### 6. The Right Question Changes the Answer

**Wrong question:** "Should I allocate 5% minimum to each stock?"
- **Answer:** Yes → Result: Equal weights, no energy

**Right question:** "How do I maintain score-based allocation while ensuring sector diversification?"
- **Answer:** 3% min + 15% max + 33% sector caps → Result: Differentiated weights, all sectors represented

**Lesson:** Constraint design is as important as the optimization algorithm.

### 7. Simplicity Has Value

**Rejected for complexity:**
- Venture debt: 18-25% XIRR but illiquid, single counterparty
- Canadian OTC stocks: 10% yields but operational hassle
- MLPs: 7-8% yields but K-1 tax forms
- 22-position portfolio: Good diversification but too many moving parts

**Selected for simplicity:**
- 10 liquid, 1099 C-corps
- 3 sectors (precious metals, energy, ex-US value)
- Quarterly rebalancing
- Clear DCA plan

**Value:** Simplicity reduces operational drag, behavioral mistakes, and accounting fees. On small portfolios, these costs compound.

### 8. Geographic and Sector Diversification Matter

**Final allocation spans:**

| Dimension | Coverage |
|-----------|----------|
| Geography | US (XOM), Canada (SU), International (AVDV/DFIV/IVAL) |
| Commodity | Gold (AEM/FNV), Silver (PAAS/HL), Mixed (WPM), Oil (XOM/SU) |
| Asset Class | Equities (90%), Streamers (13.6%), Miners (40.7%), ETFs (32.2%) |
| Market Cap | Large (XOM), Mid (SU), Small Cap Value (AVDV/DFIV/IVAL) |

**Benefit:** Reduces correlation, provides exposure to multiple thesis areas, limits single-point-of-failure risk.

### 9. Process > Prediction

**What we didn't do:**
- Forecast gold price targets
- Predict oil supply/demand
- Time the market entry
- Pick individual companies based on fundamental analysis

**What we did:**
- Systematic scoring (Sortino-weighted momentum)
- Historical drawdown analysis
- Constraint optimization
- Tax-efficient structure selection
- 3-month DCA to average in

**Result:** Repeatable process that adapts as data updates, not dependent on predicting the future.

---

## Appendix: Data Sources & Methodology

### Data
- **Source:** Yahoo Finance via `yfinance` Python package
- **History:** 3 years of daily prices with dividends reinvested (total return)
- **As of:** December 31, 2025
- **Tax Treatment:** 21% flat C-Corp rate means dividends = capital gains, so total return is the correct metric

### Methodology
1. Calculate total return index by reinvesting dividends
2. Calculate 3-month and 6-month momentum from total return prices
3. Calculate downside volatility (annualized std of negative daily returns)
4. Combined Score = (0.5 × mom_3m + 0.5 × mom_6m) / downside_vol
5. Filter: Only positive combined momentum passes (excludes MSTR, OKE, MPC, DINO, OXY)
6. Filter: Only 1099 C-corps (excludes MPLX, EPD, ET, BSM, VNOM, DMLP, KRP)
7. Weight: Proportional to score
8. Constraints applied iteratively:
   - Position minimum: 3% ($1,800) - zero out positions below
   - Position maximum: 15% ($9,000) - cap positions above
   - Sector maximum: 33% ($19,800) per sector - scale down sectors above cap
   - Renormalize to $60,000 total after each constraint application
9. Deploy via 3-month DCA: $20,000/month across all positions

### Simulation
- **Method:** Block bootstrap with 5-day blocks
- **Simulations:** 10,000 paths
- **Horizon:** 63 trading days (~3 months)
