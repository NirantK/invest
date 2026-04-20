# Commodity vs Equity Momentum: Lookback Windows, Scoring, and Academic Evidence

Research compiled from 8 parallel searches across academic papers, AQR research, and practitioner sources.

---

## 1. The Foundational Paper: Moskowitz, Ooi, Pedersen (2012) — "Time Series Momentum"

**Source:** Journal of Financial Economics, Vol 104, Issue 2, May 2012, pp. 228-250
**URL:** https://www.sciencedirect.com/science/article/pii/S0304405X11002613
**Also at:** http://docs.lhpedersen.com/TimeSeriesMomentum.pdf

### Key Findings:
- Documents significant **time series momentum (TSMOM)** in equity index, currency, commodity, and bond futures across **58 liquid instruments**
- Returns persist for **1 to 12 months**, then **partially reverse over longer horizons** — consistent with initial under-reaction followed by delayed over-reaction
- A diversified portfolio of TSMOM strategies across all asset classes yields **Sharpe ratio of 1.0+**
- The signal: simply look at whether past 12-month return is positive or negative, then go long (positive) or short (negative)
- **The 12-month lookback works across ALL asset classes** (equities, bonds, currencies, commodities) — the paper does NOT find commodities need shorter windows

### Critical Detail on Lookback:
- The paper tests 1-month, 3-month, and 12-month lookback signals
- All three work, but **12-month has the strongest statistical significance**
- **1-month signal** has higher turnover and lower after-cost returns
- **Combining multiple lookback horizons** (1m, 3m, 12m) improves Sharpe ratio through diversification of signal horizons

---

## 2. AQR: "Demystifying Managed Futures" (Hurst, Ooi, Pedersen, 2013)

**Source:** Journal of Investment Management, Vol. 11, No. 3, 2013, pp. 42-58
**URL:** https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Demystifying-Managed-Futures.pdf

### Key Implementation Details:
- Shows that returns of Managed Futures funds/CTAs can be **explained by time series momentum strategies**
- Discusses critical implementation issues: **risk management, risk allocation across asset classes, trend horizons, portfolio rebalancing frequency, transaction costs, and fees**
- Largest managed futures managers' alphas go to zero after controlling for TSMOM
- **AQR's approach uses a blend of 1-month, 3-month, and 12-month momentum signals** across all asset classes
- They do NOT use different lookbacks for commodities vs equities — they use the SAME multi-horizon blend everywhere

### Signal Construction:
- For each asset at each horizon h (1m, 3m, 12m): sign of past h-month return determines long/short
- Position sizing: inversely proportional to realized volatility (vol-targeting)
- Equal risk allocation across the three horizons
- Monthly rebalancing

---

## 3. AQR: "A Century of Evidence on Trend-Following Investing" (Hurst, Ooi, Pedersen, 2014)

**URL:** https://jkgcapital.com/wp-content/uploads/2017/02/AQR-A-Century-of-Trend-Following-Investing.pdf

### Key Points:
- Extended backtest to **1880**, covering over 130 years
- Tests 1-month, 3-month, and 12-month time series momentum across commodities, equity indices, bond markets, and currency pairs
- **The strategy works consistently across all asset classes and across different eras**
- Combined multi-horizon (1m + 3m + 12m) trend-following generates the most stable returns
- The paper explicitly uses the same horizons for commodities as for equities — no differentiation

---

## 4. AQR: "Trend Following and Rising Rates" (Hurst, Ooi, Stamelos, 2015)

**URL:** https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Trend-Following-and-Rising-Rates2023.pdf

### Lookback Specifics:
- Examines 1-month, 3-month, and 12-month time series momentum strategies for **67 markets** across commodities, equity indices, bond markets, and currency pairs
- Strategy's return characteristics and diversification properties hold in all interest rate environments
- **Consistent use of the same 3 lookback windows (1m, 3m, 12m) across all asset classes**

---

## 5. Research Affiliates: "Walking the Tightrope: Trend Following's Tricky Tradeoffs" (Masturzo, May 2025)

**URL:** https://www.researchaffiliates.com/content/dam/ra/publications/pdf/1077-trend-followings-tricky-tradeoffs-sharpe-ratio-vs-skew.pdf

### Key Insight — The Sharpe Ratio vs. Skew Tradeoff:
- Not all trend strategies are the same
- **Increased positive skewness often comes with LOWER Sharpe ratio**
- The tradeoff is directly related to **signal and portfolio construction decisions**
- Shorter lookback windows generate more positive skew (better tail protection) but lower average returns
- Longer lookback windows generate higher Sharpe ratio but less crisis alpha
- **This is the key practical tradeoff for commodity vs equity momentum design**

---

## 6. Zakamulin & Giner: "Optimal Trend-Following With Transaction Costs"

**URL:** https://www.returnstacked.com/academic-review/optimal-trend-following-with-transaction-costs/
**Paper at:** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4282126

### Key Findings on Optimal Lookback:
- When transaction costs are considered, **optimal lookback windows shift longer**
- Shorter lookback = more trades = higher costs = net returns erode
- The paper finds that popular trend-following approaches **over-trade relative to what's optimal**
- Optimal trend signals use **exponential moving averages (EMAs) rather than simple lookback returns**
- The tradeoff: shorter windows capture turns faster but the higher turnover eats into returns
- **For liquid commodity futures** (low transaction costs), shorter windows remain viable
- **For equity ETFs** (moderate costs, potential slippage), longer windows are more cost-effective

---

## 7. Clare, Seaton & Smith: "Trend following, risk parity and momentum in commodity futures" (2014)

**URL:** https://www.sciencedirect.com/science/article/abs/pii/S1057521913001373
**Published in:** International Review of Financial Analysis, 2014

### Commodity-Specific Findings:
- Studies trend following specifically in commodity futures
- Combines trend-following with risk parity weighting
- Finds that momentum in commodity futures is robust
- Tests multiple lookback periods specific to commodities

---

## 8. Dimensional Fund Advisors Approach to Momentum

**URL:** https://www.dimensional.com/sg-en/insights/myth-busting-with-momentum-how-to-pursue-the-premium

### DFA's Key Points (Wes Crill, PhD):
- Historical US momentum premium: **9.1% per year**
- Momentum has **extreme turnover** and **occasional catastrophic outcomes** (momentum crashes)
- DFA does NOT run a standalone momentum fund — instead uses momentum as a **trading signal within value/size portfolios**
- Their approach: when they need to trade (rebalancing, cash flows), they **tilt toward momentum winners and away from losers**
- This dramatically reduces turnover vs. a pure momentum strategy
- **DFA does not differentiate lookback by asset class** — they use standard 12-month minus 1-month (Jegadeesh-Titman style) for equities
- They do NOT run a commodity momentum strategy

---

## 9. "Momentum Investing: What 159 Years of Data Tell Us" (Larry Swedroe, FA Magazine, Jan 2026)

**URL:** https://www.fa-mag.com/news/momentum-investing--what-159-years-of-data-tells-us-85674.html

### Key Meta-Findings:
- Based on Baltussen, Dom, Van Vliet, Vidojevic (Nov 2025): "Momentum Factor Investing: Evidence and Evolution," Journal of Portfolio Management Vol 52 Issue 3
- Momentum is **remarkably persistent** across 159 years of data
- The premium exists across multiple asset classes and geographies
- The standard momentum lookback (12-1 month: past 12 months excluding the most recent month) remains the workhorse

---

## 10. AQR Time Series Momentum Dataset

**URL:** https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly

- AQR publishes monthly TSMOM factor returns related to the Moskowitz, Ooi, Pedersen (2012) paper
- Data covers the asset-pricing anomaly across commodity, equity, bond, and currency futures
- Signals are constructed using the same lookback methodology across all asset classes

---

## 11. The Georgopoulou & Wang Paper: "The Trend Is Your Friend: Time-Series Momentum Strategies Across Equity and Commodity Markets" (2016)

**URL:** https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2798042_code586501.pdf?abstractid=2618243&mirid=1
**Published in:** Review of Finance

### Direct Equity vs Commodity Comparison:
- Directly compares TSMOM across equity and commodity markets
- Studies whether the same signals work in both domains
- Published in a top-tier journal (Review of Finance)

---

## Practical Synthesis: What Lookback Windows Work for Commodities vs. Equities

### The Academic Consensus:

1. **The same lookback horizons work across asset classes.** Moskowitz et al. (2012) and all subsequent AQR research use 1m, 3m, and 12m lookbacks identically for commodities and equities.

2. **There is NO strong academic evidence that commodities specifically need shorter lookback windows** than equities. The standard multi-horizon blend (1m + 3m + 12m) works everywhere.

3. **However, the WEIGHTING of horizons may differ.** Shorter horizons (1m, 3m) contribute more to:
   - Commodities that are supply-shock driven (oil, natural gas, agricultural)
   - More volatile assets where trends form and break quickly
   - Crisis alpha / positive skew generation

4. **Longer horizons (6m, 12m) contribute more to:**
   - Equity indices with slower-moving macro trends
   - Bond markets where central bank policy shifts play out over quarters
   - Higher Sharpe ratio but lower skew

### The Practical Differences:

| Parameter | Commodity Futures (CTA-style) | Equity ETFs (Your Portfolio) |
|-----------|------------------------------|----------------------------|
| **Typical lookback blend** | 1m + 3m + 12m (equal risk weight) | 3m + 6m + 12m (weighted toward longer) |
| **Optimal single lookback** | 3-6 months (shorter works due to supply shocks) | 6-12 months (longer captures macro trends) |
| **Rebalancing frequency** | Daily to weekly (futures are cheap to trade) | Monthly (ETF transaction costs matter) |
| **Signal type** | Time-series momentum (long/short each asset vs. its own past) | Cross-sectional momentum (rank assets, overweight winners) |
| **Vol targeting** | Standard (each position scaled to target vol) | Optional (position sizing by inverse vol) |
| **Skip period** | Last 1 month (reversal effect) | Last 1 month (standard) |
| **Turnover** | 200-400% annual | 50-150% annual |
| **Transaction cost sensitivity** | Low (liquid futures) | Moderate (ETF spreads, market impact) |

### Why Your Current System (20% x 3M + 40% x 6M + 40% x 12M) Is Reasonable for Equity ETFs:

Your weighting scheme in `us_portfolio_allocation.py` already reflects the academic consensus for equity-style momentum:
- Skipping the most recent 21 trading days (~1 month) avoids short-term reversal
- Heavy weighting on 6M and 12M captures the macro momentum that works best in equities
- Light weighting on 3M adds some responsiveness without excessive turnover
- The smoothness overlay (R-squared and FIP) is a practical addition beyond what the academic papers use

### If You Were Adding Commodity-Specific Scoring:

For a commodity futures or commodity ETF allocation, the research suggests:
- **Increase the weight on shorter lookbacks**: e.g., 30% x 1M + 35% x 3M + 35% x 12M
- **Or use a pure TSMOM signal**: is the 12-month return positive? Long. Negative? Avoid/short
- **Add a breakout/trend signal**: is price above its 50-day or 100-day moving average?
- **Increase rebalancing frequency** if using futures (weekly), but keep monthly for ETFs
- **Consider adding a carry signal** (contango/backwardation) alongside momentum — this is what AQR and most sophisticated commodity allocators do

### Key Papers to Cite:

1. **Moskowitz, Ooi, Pedersen (2012)** — "Time Series Momentum" — the foundational paper establishing TSMOM across asset classes with 1m/3m/12m lookbacks
2. **Hurst, Ooi, Pedersen (2013)** — "Demystifying Managed Futures" — implementation details for TSMOM in practice
3. **Hurst, Ooi, Pedersen (2014)** — "A Century of Evidence on Trend-Following" — 130+ year backtest confirming multi-horizon robustness
4. **Zakamulin & Giner** — "Optimal Trend-Following With Transaction Costs" — shows longer lookbacks become optimal when costs are considered
5. **Research Affiliates (2025)** — "Walking the Tightrope" — Sharpe ratio vs. skew tradeoff, directly relevant to horizon choice
6. **Baltussen, Dom, Van Vliet, Vidojevic (2025)** — "Momentum Factor Investing: Evidence and Evolution" — 159-year comprehensive study
7. **Georgopoulou & Wang (2016)** — "The Trend Is Your Friend" — direct equity vs commodity TSMOM comparison
