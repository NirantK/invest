# Investment Portfolio Management

This repo manages two portfolios:
1. **US C-Corp** (via IBKR) - US equities with Sortino-weighted momentum
2. **INR Personal** (India) - Mutual funds and Indian equities

## Project Context

**Purpose:** Allocate $60,000 in US equities through C-Corp structure with:
- Momentum-based allocation (3M/6M combined score)
- Sector caps to force diversification (33% max per sector)
- Tax-efficient rebalancing (add capital, never sell)
- 1099 C-corps only (avoid K-1 complexity)

**Current State (Q1 2026):**
- **⚠️ NOTHING DEPLOYED YET** - all amounts are targets
- $60,000 initial capital to be allocated via 12-week DCA
- Quarterly rebalancing planned with $20,000 new capital each quarter

## Development Setup

- **Python:** 3.11+ required
- **Package Manager:** `uv` (use `uv run` instead of `python`)
- **Key Dependencies:** yfinance, pandas, numpy, click, ib-async, httpx

Install:
```bash
uv sync
```

## Code Style

- Line length: 88
- Double quotes
- Follow happy path conventions (avoid try-except blocks)
- Use `uv run python` for all script execution

## Project Structure

```
.
├── us/                               # US C-Corp Portfolio (IBKR)
│   ├── scripts/
│   │   ├── us_portfolio_allocation.py    # Main allocation engine
│   │   ├── portfolio_simulation.py       # Monte Carlo risk analysis
│   │   ├── oil_gas_comprehensive.py      # Sector analysis
│   │   ├── ibkr_client.py                # IBKR API wrapper
│   │   └── correlation_analysis.py       # Correlation analysis
│   └── data/
│       ├── correlation_matrix.csv
│       └── portfolio_comparison.json
│
├── india/                            # INR Personal Portfolio
│   ├── scripts/
│   │   ├── fetch_mf_nav.py               # mfapi.in integration
│   │   └── *.ipynb                       # Analysis notebooks
│   └── data/
│       ├── kasliwal_holdings_flat.csv
│       └── 2026-01-21-*.csv              # Portfolio snapshots
│
├── docs/
│   └── investment_decision_log.md    # Complete decision history
└── README.md
```

## Data Sources

| Source | Purpose | Module |
|--------|---------|--------|
| IBKR API | Real-time US portfolio | `us/scripts/ibkr_client.py` |
| yfinance | US stock prices | `us/scripts/us_portfolio_allocation.py` |
| mfapi.in | Indian MF NAV data | `india/scripts/fetch_mf_nav.py` |

### IBKR Setup

Requires TWS or IB Gateway running with API enabled:
1. TWS: Edit > Global Configuration > API > Settings
2. Enable "ActiveX and Socket Clients"
3. Port: 7497 (TWS) or 4001 (Gateway)
4. Set in `.env`: `IBKR_PORT=7497` and `IBKR_CLIENT_ID=1`

### mfapi.in

Free API for Indian mutual fund NAV data. No auth required.
- Docs: https://www.mfapi.in/
- Example: `uv run python india/scripts/fetch_mf_nav.py`

## Key Assumptions & Constraints

### Price Targets (Thesis Validation)
- Gold: $4,000/oz minimum
- Silver: $50/oz minimum
- Oil: Supply crunch 2027-2028 (deferred capex thesis)
- Copper: Electrification supercycle (EVs, grid, AI data centers)
- Uranium: Nuclear renaissance, supply deficit post-2025

### Tax Strategy
- C-Corp @ 21% flat rate (dividends = capital gains)
- 1099 C-corps only (exclude all K-1 MLPs)
- **Rebalancing:** Add capital to underweight positions, never sell (avoid tax events)

### Allocation Constraints
1. **Position:** 3% min, 15% max
2. **Sector:** 33% max per sector (gold/silver/mixed/oil&gas/copper/uranium/ex-US)
3. **Filters:** Positive momentum only, 1099 only

### Investment Themes (9-Position Portfolio)
| Theme | Ticker | Thesis |
|-------|--------|--------|
| Copper | COPX | Electrification: EVs (80kg/car), grid upgrades, AI data centers |
| Gold/Silver | WPM, FNV | Streamers: 80% margins, no op risk, central bank buying |
| Uranium | URA | Nuclear renaissance, 10-year supply deficit, SMR buildout |
| Platinum | PPLT | Hydrogen fuel cells, automotive catalysts, supply deficit |
| Ex-US Momentum | IMTM | Factor diversification, non-US winners |
| Ex-US Value | AVDV | US overvaluation hedge, small cap value tilt |
| LatAm | ILF | Commodity beta, EM discount to DM |
| Bitcoin | MSTR | Digital gold, asymmetric upside (small position) |

### Exclusions (Do Not Buy)
| Ticker | Reason |
|--------|--------|
| VALE | China iron ore decline, Simandou supply, dam liabilities, Lula risk |
| NEM | Execution issues, AISC overruns |
| GOLD | High AISC vs peers |
| K-1 issuers | Tax complexity for C-Corp |

## Next Quarter Activation (Q2 2026)

When activating in Q2 2026 (approximately April 2026), follow this sequence:

### 1. Data Refresh
```bash
uv run python us/scripts/us_portfolio_allocation.py --min-allocation 0.03 --max-allocation 0.15
```

This will:
- Fetch latest 3-year price history (Jan 2023 - present)
- Calculate total returns with reinvested dividends
- Apply momentum filters (positive 3M+6M only)
- Apply sector caps (33% max per sector)
- Output new recommended allocation

### 2. Rebalancing Analysis

**Target Allocation (9 positions):**

| Ticker | Qty | Avg Cost | Value | Category | Status |
|--------|-----|----------|-------|----------|--------|
| COPX | 12 | $83.08 | $997 | Copper miners ETF | ✓ Filled |
| WPM | 6 | $138.62 | $832 | Streamer (gold/silver) | ✓ Filled |
| FNV | 3 | $252.73 | $758 | Streamer (gold) | ✓ Filled |
| IMTM | 9 | $50.11 | $451 | Ex-US Momentum ETF | ✓ Filled |
| MSTR | 1.77 | $171.03 | $303 | Bitcoin proxy | ✓ Filled |
| PPLT | 6 | — | ~$1,350 | Platinum ETF | Pending |
| URA | 6 | — | ~$330 | Uranium miners ETF | Pending |
| ILF | 15 | — | ~$495 | LatAm equity ETF | Pending |
| AVDV | 3 | — | ~$297 | Ex-US Small Cap Value | Pending |

**Current:** $3,341 deployed (5 positions)
**Target:** ~$6,800 total (9 positions)

**Swing Trade (separate from core allocation):**
| Ticker | Qty | Category | Horizon | Exit Rule |
|--------|-----|----------|---------|-----------|
| NU | 111 | Nubank (Brazil fintech) | 6 months | Sell July 2026 regardless of performance |

**Initial Deployment (if not yet invested):**
1. Run allocation script to get fresh target weights
2. Deploy $60,000 via 12-week DCA (~$5,000/week)
3. Split weekly amount across positions per target weights

**Subsequent Rebalancing (after initial deployment):**
1. Run allocation script to get new target weights
2. Calculate current portfolio value at current prices
3. For each underweight position:
   ```
   buy_amount = (new_target_weight × total_value) - current_holding_value
   ```
4. Use $20,000 new capital to buy underweight positions only
5. **DO NOT SELL** overweight positions

### 3. Momentum Regime Check

**Critical:** Review momentum shifts before deploying capital.

Questions to answer:
- Did any stocks flip to negative momentum? (Pause DCA if yes)
- Did sector leadership change? (Precious metals vs energy vs ex-US)
- Are we in same momentum regime as Q1? (Silver/gold still strong?)

Check this with:
```bash
uv run python us/scripts/portfolio_simulation.py
```

Look for:
- Historical pain analysis (max drawdown changes)
- 3-month forward VaR 95% (should be -10% to -15% range)
- Probability of loss (should be 20-25% range)

### 4. Tax Status Verification

**Critical:** Verify no ETFs/stocks converted to K-1 issuers.

Check each ticker:
- [ ] COPX, URA, PPLT, ILF, IMTM, AVDV still issue 1099s (ETFs)
- [ ] WPM, FNV still issue 1099s (Canadian corps)
- [ ] MSTR still issues 1099 (US corp)
- [ ] No new K-1 conversions

If any converted to K-1: Exclude from new allocation, reallocate capital.

### 5. Sector Cap Review

After running allocation, verify:
- [ ] No sector exceeds 33% of total portfolio
- [ ] Precious metals (WPM + FNV) ≤ 33%
- [ ] Energy transition (COPX + URA + PPLT) ≤ 33%
- [ ] Ex-US (AVDV + IMTM + ILF) ≤ 33%
- [ ] Bitcoin (MSTR) — small allocation, no cap needed

### 6. New Stock Candidates

**Current 9-position allocation is final.** Only consider changes if:
- Position momentum turns negative (pause DCA, don't sell)
- Tax status changes (K-1 conversion)
- Fundamental thesis breaks

Run comprehensive analysis if needed:
```bash
uv run python us/scripts/oil_gas_comprehensive.py  # For energy sector
```

### 7. Execution Plan

Once analysis complete:
1. DCA new $20,000 over 4 weeks (weekly buys)
2. Split across underweight positions proportionally
3. Update holdings tracker
4. Document deviations in `docs/investment_decision_log.md`

### 8. Price Target Check

Update this table quarterly:

| Asset | Q1 2026 | Q2 2026 | Target | Status |
|-------|---------|---------|--------|--------|
| Gold (spot) | $TBD | $TBD | $4,000/oz | Monitor |
| Silver (spot) | $TBD | $TBD | $50/oz | Monitor |
| WTI Oil | $TBD | $TBD | Supply crunch | Monitor |

If targets hit:
- Consider partial profit taking (sell overweight portions)
- Rotate to sectors with better risk-reward
- Update decision log with rationale

## Common Issues & Solutions

### Issue: Negative Momentum on Core Holdings

**Symptom:** XOM or PAAS flips to negative combined momentum

**Solution:**
1. Pause DCA on that position
2. Reallocate new capital to other sector stocks
3. Do NOT sell (avoid tax event)
4. Resume DCA when momentum turns positive

### Issue: Sector Exceeds 33% Cap

**Symptom:** Precious metals grows to 40% due to price appreciation

**Solution:**
1. Cap new capital to that sector at $0
2. Allocate all new capital to underweight sectors
3. Natural drift will rebalance over time
4. Do NOT sell overweight sector

### Issue: Stock Converts to K-1 Issuer

**Symptom:** C-corp announces MLP conversion

**Solution:**
1. Immediately exclude from universe
2. Hold existing position (don't trigger tax event)
3. Stop all new DCA to that stock
4. Reallocate new capital to other sector stocks
5. Consider selling during opportune tax year if needed

### Issue: New Stock Dominates Allocation

**Symptom:** New candidate scores 4.0+ (higher than HL's 3.90)

**Solution:**
1. Verify data quality (check for errors, splits, dividends)
2. Check if momentum is sustainable (not just 1-month spike)
3. Apply same constraints (3% min, 15% max, 33% sector cap)
4. Add gradually via DCA (don't deploy all at once)

## Files to Update Each Quarter

1. **docs/investment_decision_log.md**
   - Add "Part X: QX 2026 Quarterly Rebalancing" section
   - Document momentum regime changes
   - Note any stocks added/removed and why
   - Record actual vs model allocation

2. **README.md**
   - Update "Current Allocation" section with Q2 numbers
   - Update price target table
   - Check off completed items in "Next Quarter Checklist"

3. **us/scripts/portfolio_simulation.py**
   - Update PORTFOLIO dict with current holdings (if changed)
   - Verify total capital matches deployed amount

## Decision Philosophy Reminders

1. **Trust the process:** Let Sortino scores decide, don't override for "gut feel"
2. **Sector caps matter:** Even if precious metals score 10x better, cap at 33%
3. **Tax efficiency:** Adding capital is always better than selling + rebalancing
4. **Simplicity premium:** Reject complexity for <0.5% return improvement
5. **Scale > Yield:** Don't chase 10% yields on small positions

## Quick Commands Reference

```bash
# Run full allocation with current constraints
uv run python us/scripts/us_portfolio_allocation.py --min-allocation 0.03 --max-allocation 0.15

# Monte Carlo simulation (10k paths, 3-month horizon)
uv run python us/scripts/portfolio_simulation.py

# Comprehensive energy sector analysis (26 stocks)
uv run python us/scripts/oil_gas_comprehensive.py

# Canadian energy NYSE-only (no OTC)
uv run python us/scripts/canadian_nyse_only.py

# Check dependencies
uv sync
```

## Contact & Continuation

This is a quarterly maintenance project. Each quarter:
1. Review this file for activation instructions
2. Run analysis scripts with fresh data
3. Deploy new capital to underweight positions
4. Update documentation
5. Set reminder for next quarter

**Next Activation:** April 2026 (Q2 rebalancing)
