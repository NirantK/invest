# Nirant's US Investment Decisions — Consolidated Reference

**Source**: Past conversations (Nov 2025 — Jan 2026)  
**Investment Vehicle**: C-Corp Treasury (Scaled Focus Inc.)  
**Broker**: Interactive Brokers (IBKR)  
**Time Horizon**: 3 years  
**Volatility Tolerance**: -20% drawdown acceptable  
**Monitoring Cadence**: Quarterly

---

## 1. Macro Thesis

### India Hedge Logic
India imports **88%+ of crude oil**. A $10/bbl price increase → $12-13B higher import bill → CAD widens 0.3% GDP → INR depreciation → RBI tightens → Indian equity underperformance.

**US oil & gas positions profit from the exact scenario that hurts Indian equity exposure.** This is negative correlation by design.

### Rick Rule's Supply Thesis
- Global oil sector deferring **$2B/day** in sustaining capex
- Supply cliff expected **2027-2028**
- Major integrated oil companies trading at **40% discount to NPV** on conservative oil price assumptions

### Precious Metals Thesis
- Target: **$50+ silver**, **$4,000+ gold**
- Gold/silver ratio at ~87 vs long-term avg ~60 (silver undervalued relative to gold)
- Central bank buying (China, Russia, India) providing structural demand floor

---

## 2. Investment Structure

### Two Portfolio Options Discussed

#### Option A: 3-ETF Portfolio (Simplest)

| ETF | Allocation | Expense | Role |
|-----|------------|---------|------|
| **XLE** | 40% | 0.09% | Oil & gas, India macro hedge |
| **GDX** | 35% | 0.51% | Gold miners |
| **SIL** | 25% | 0.65% | Silver miners |

**Execution time**: 2 hours to set up, 30 minutes per quarter

---

#### Option B: Core + Momentum Satellite (Preferred per discussions)

**Fixed Core (40%) — Always Held**

| Ticker | Name | Allocation | Role |
|--------|------|------------|------|
| **WPM** | Wheaton Precious Metals | 20% | Silver-heavy streaming, zero cost inflation, $1B cash |
| **FNV** | Franco-Nevada | 20% | Gold-heavy streaming, energy royalty buffer, debt-free |

**Why streaming is core**: 75-80% gross margins, near-zero AISC volatility, no capex requirements, no single-mine blowup risk. These are "tollbooth" businesses that collect metal at locked-in discounts regardless of operator performance.

**Satellite (60%) — Momentum-Based Rotation**

| Ticker | Category | Starting Allocation |
|--------|----------|---------------------|
| **PAAS** | Silver Miner | 15% |
| **HL** | Silver Miner | 15% |
| **AEM** | Gold Miner (best operator) | 20% |
| **XLE** | Oil & Gas ETF | 10% |

---

## 3. Momentum Rebalancing Rules

### Quarterly Process

**Step 1: Check Absolute Momentum (Safety Filter)**
- For each satellite asset, check: Is 12-month total return > 0?
- If negative → allocation goes to 0% (rotate to SGOV/cash)

**Step 2: Rank by Relative Momentum**
- Among assets passing filter, rank by 12-month return
- Allocate satellite 60% as:
  - Rank 1: 30%
  - Rank 2: 20%
  - Rank 3: 10%
  - Failed filter: 0%

### Example Scenarios

**Scenario A: Silver Hot, Gold OK, Oil Cold**
- Silver (1st): 30% → 15% PAAS, 15% HL
- Gold (2nd): 20% → AEM
- Oil (3rd, positive): 10% → XLE
- Core: 40% → WPM, FNV

**Scenario B: Oil Hot, Silver OK, Gold Negative**
- Oil (1st): 30% → XLE
- Silver (2nd): 20% → PAAS, HL
- Gold (failed): 0% → SGOV
- Leftover 10% → SGOV
- Core: 40% → WPM, FNV

**Scenario C: Everything Negative (Crisis)**
- All satellite → SGOV (60% in cash)
- Core held: 40% → WPM, FNV (streaming is defensive)

---

## 4. Starting Allocation (Q1 2025 Signal)

Based on late-2025 momentum data:

| Asset | 12M Return | Rank |
|-------|------------|------|
| SIL (silver proxy) | +195% | 1st |
| GDX (gold proxy) | +166% | 2nd |
| XLE (oil proxy) | ~+10-15% | 3rd |

**Resulting Start Portfolio:**

| Ticker | Allocation | Category |
|--------|------------|----------|
| WPM | 20% | Core (fixed) |
| FNV | 20% | Core (fixed) |
| PAAS | 15% | Satellite (Silver, rank 1) |
| HL | 15% | Satellite (Silver, rank 1) |
| AEM | 20% | Satellite (Gold, rank 2) |
| XLE | 10% | Satellite (Oil, rank 3) |

**Total Precious Metals Exposure**: 70% (including streamers)  
**Silver Weighting**: ~50%

---

## 5. Rebalancing Triggers (Non-Momentum)

| Condition | Action |
|-----------|--------|
| Silver breaks $60 | Trim AG/high-beta silver by 50%, add to WPM |
| AEM AISC creeps above $1,400 | Investigate operational issues; consider shifting 5-10% to FNV |
| PAAS Juanicipio ramp disappoints (by mid-2026) | Trim to 15%, add to HL |
| Gold/silver ratio compresses below 50:1 | Shift 5% from AEM to PAAS |
| Any ETF deviates >10% from target | Rebalance |

---

## 6. Review Schedule

| Date | Action |
|------|--------|
| **Q2 2026** (Apr-Jun) | First formal review — pull 12M returns, execute rebalancing if needed |
| **Q4 2026** (Oct-Dec) | Second review |
| **Q2 2027** (Apr-Jun) | Third review |
| **Q4 2027** (Oct-Dec) | Assess exit or continuation based on thesis |

**Calendar reminders to set**: Q2 2026, Q4 2026, Q2 2027

---

## 7. Execution Checklist

- [ ] Open IBKR account for C-Corp (if not already done)
- [ ] **Change default tax lot method to Highest Cost** (see Section 7a below)
- [ ] Enable DRIP for dividend reinvestment
- [ ] Deploy capital per starting allocation
- [ ] Set calendar reminders for quarterly reviews
- [ ] Create tracking spreadsheet:

| Date | PAAS 12M | HL 12M | AEM 12M | XLE 12M | Rank Order | Action Taken |
|------|----------|--------|---------|---------|------------|--------------|
| Q1 2025 | | | | | | Initial deploy |
| Q2 2026 | | | | | | |
| Q4 2026 | | | | | | |

---

## 7a. IBKR Tax Lot Settings (Critical for Tax Loss Harvesting)

**Problem**: IBKR defaults to FIFO (First In, First Out), which sells your oldest (often lowest cost) shares first. This maximizes capital gains taxes.

**Solution**: Change default to **Highest Cost** — automatically sells lots with highest cost basis first, minimizing gains or maximizing losses.

### How to Change

1. Log into IBKR Client Portal
2. Go to **Reports → Tax Optimizer**
3. Click **Default Match Method**
4. Change from FIFO to **Highest Cost**
5. Save

### Available Methods

| Method | Use Case |
|--------|----------|
| **Highest Cost** | Best default — minimizes capital gains |
| Maximize Long-Term Loss | Prioritizes selling long-term losses |
| Maximize Short-Term Loss | Prioritizes selling short-term losses |
| Specific Lot | Manual selection per trade (more work) |
| LIFO | Last in, first out |
| FIFO | First in, first out (default, worst for taxes) |

### Notes

- You can override per-trade using Tax Optimizer until 8:30 PM ET on trade day
- Setting Highest Cost as default means you don't have to think about it
- IRS-compliant under "Specific Identification" rules
- Also enable **Tax Loss Harvesting Tool** (Reports → Tax Loss Harvester) for automated loss identification

---

## 8. Expected Return Ranges

At thesis prices ($50 Ag, $4,000 Au) over 3Y:

| Scenario | Portfolio Return | Notes |
|----------|------------------|-------|
| **Bull** | 150-200% | Prices overshoot, M&A premiums |
| **Base** | 80-120% | Prices reach targets, operators execute |
| **Bear** | 30-50% | Thesis takes 4Y not 3Y, execution misses |
| **Downside** | -15 to -25% | Thesis wrong (silver at $30, gold at $3,000) |

Royalty weighting (40%) limits downside while capturing 70-80% of upside in bull cases.

---

## 9. What This Portfolio Excludes (and Why)

| Excluded | Reason |
|----------|--------|
| **Vale (VALE)** | **80% iron ore exposure = China structural decline bet.** Simandou (120Mt/yr) coming 2025-26 crushes pricing power. Indonesian HPAL ($9,800/t cost) eroding Class 1 nickel moat. PT Vale Indonesia halted mining Jan 2026 (quota dispute). Dam liabilities (Brumadinho/Mariana: $30B+) + Lula political interference. Nickel is <10% of revenue—"free call option" isn't free if iron ore keeps falling. 5x more bearish than bullish analyst sentiment. |
| Newmont (NEM) | $1,611 AISC vs $1,300 guidance; worst daily drop in 27 years. Execution risk. |
| Barrick (GOLD) | AISCs among majors' highest. If you want gold, AEM is better. |
| Sibanye-Stillwater | $2.6B writedowns, 60% capacity. Turnaround bet, not growth. |
| Silvercorp (SVM) | Lowest AISC but China jurisdiction = binary political risk |
| Canadian Energy (XEG.TO) | Adds complexity; only worth it if deploying $100K+ |
| DFA Value Funds | Value premium is 10-15Y phenomenon; 3Y horizon too short |
| US Broad Equities | Already correlated to US tech economy via consulting income |

---

## 10. Key Thesis Learning Areas (for 3Y deep dive)

### XLE / Oil
- OPEC+ production decisions
- US shale breakeven costs
- Permian Basin decline rates
- Refining margins (crack spreads)

### GDX / Gold
- AISC trends across majors
- Gold/real rates relationship
- Central bank gold buying
- M&A activity in juniors

### SIL / Silver
- Silver industrial demand (solar, EVs)
- Gold/silver ratio dynamics
- Mexico/Peru production issues
- Byproduct credit dynamics

---

## Appendix: Portfolio Summary Table

| Component | Ticker | % | Type | Thesis |
|-----------|--------|---|------|--------|
| Wheaton Precious Metals | WPM | 20% | Core | Silver-heavy streamer, zero op risk |
| Franco-Nevada | FNV | 20% | Core | Gold streamer + energy royalties |
| Pan American Silver | PAAS | 15% | Satellite | Primary silver producer, Juanicipio |
| Hecla Mining | HL | 15% | Satellite | US silver production, cost discipline |
| Agnico Eagle | AEM | 20% | Satellite | Best-in-class gold miner, $1,100 AISC |
| Energy Select SPDR | XLE | 10% | Satellite | XOM, CVX, COP; India macro hedge |

**Total instruments**: 6  
**Weighted expense ratio**: ~0.15% (streamers have no expense, XLE at 0.09%)

---

## 11. Current State (Jan 2026)

**As of:** 2026-01-15

### Deployment Status

**⚠️ NOTHING DEPLOYED YET** - All amounts below are TARGET allocations, not actual holdings.

### Target Allocation (When Ready to Deploy)

**Miners (Precious Metals):** $32,000 target
| Ticker | Target | Category |
|--------|--------|----------|
| PAAS | $9,000 | Silver miner |
| HL | $9,000 | Silver miner |
| AEM | $6,000 | Gold miner |
| WPM | $5,000 | Streamer (mixed) |
| FNV | $3,000 | Streamer (gold) |

**Energy (Oil & Gas):** $8,000 target
| Ticker | Target | Category |
|--------|--------|----------|
| XOM | $4,000 | Integrated major |
| SU | $4,000 | Canadian integrated |

**Ex-US Value:** $19,000 target
| Ticker | Target | Category |
|--------|--------|----------|
| AVDV | $7,000 | Avantis Intl Small Cap Value |
| DFIV | $7,000 | DFA International Value |
| IVAL | $5,000 | Alpha Architect Intl Quant Value |

**Bitcoin:** $100/month DCA (while momentum negative)
| Ticker | Monthly | Category |
|--------|---------|----------|
| MSTR | $100 | Bitcoin proxy |

### Reference Prices (Dec 31, 2025)

| Ticker | Reference Price |
|--------|-----------------|
| PAAS | $54.89 |
| HL | $19.50 |
| AEM | $182.04 |
| WPM | $120.90 |
| FNV | $213.11 |
| XOM | $134.09 |
| SU | $49.97 |
| AVDV | $105.53 |
| DFIV | $56.13 |
| IVAL | $35.62 |
| MSTR | $151.95 |

### Momentum Status (as of Jan 2026)

| Ticker | 3M Return | 6M Return | Combined Momentum |
|--------|-----------|-----------|-------------------|
| PAAS | +40.8% | +82.2% | Positive |
| HL | +78.2% | +264.6% | Positive |
| AEM | +15.6% | +59.0% | Positive |
| WPM | +19.2% | +37.6% | Positive |
| FNV | +14.4% | +47.7% | Positive |
| XOM | +11.2% | +8.1% | Positive |
| SU | +16.7% | +15.7% | Positive |
| AVDV | +9.7% | +21.3% | Positive |
| DFIV | +10.8% | +18.4% | Positive |
| IVAL | +7.0% | +17.3% | Positive |
| MSTR | -48.7% | -65.3% | **NEGATIVE** |

### Next Steps

1. **Open IBKR account** for C-Corp (if not done)
2. **Run allocation script** with fresh data before deploying
3. **Deploy via 12-week DCA** - $5,000/week across positions
4. **MSTR:** Start $100/month DCA separately

---

## Open Items

- [ ] **Confirm deployment**: Did you actually execute these trades? IBKR setup discussed but no buy confirmation found.
- [ ] **Set Q2 2026 calendar reminder**
- [ ] **Create tracking spreadsheet** for quarterly 12M returns

---

*Document generated from past conversations (Jan 9, 2026). Updated Jan 22, 2026: Added VALE to exclusions after bear case analysis (China structural decline, Simandou supply, Indonesian HPAL competition, dam liabilities, political risk). Review quarterly and update as positions/thesis evolve.*
