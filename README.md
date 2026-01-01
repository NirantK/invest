# US C-Corp Portfolio Allocation

Systematic portfolio allocation for $60,000 US equities deployment using Sortino-weighted momentum with sector diversification constraints.

## Current Allocation (Q1 2026)

**Final Portfolio (10 positions):**
- PAAS: $9,000 (15.25%) - Silver miner
- HL: $9,000 (15.25%) - Silver miner
- AVDV: $7,000 (11.86%) - Ex-US small cap value
- DFIV: $7,000 (11.86%) - Ex-US value
- AEM: $6,000 (10.17%) - Gold miner
- WPM: $5,000 (8.47%) - Gold/silver streamer
- IVAL: $5,000 (8.47%) - Ex-US quant value
- XOM: $4,000 (6.78%) - US integrated oil major
- SU: $4,000 (6.78%) - Canadian integrated oil major
- FNV: $3,000 (5.08%) - Gold streamer + royalties
- MSTR: $100/month DCA - Bitcoin proxy

**Sector Breakdown:**
- Precious Metals: $32,000 (54.2%)
- Ex-US Value: $19,000 (32.2%)
- Energy: $8,000 (13.6%)

## Key Assumptions

### Price Targets (Informing Thesis)
- **Gold:** $4,000/oz minimum target
- **Silver:** $50/oz minimum target
- **Oil:** Supply crunch expected 2027-2028 (deferred capex thesis)

### Tax & Structure
- **Entity:** US C-Corp (21% flat rate on all income)
- **Tax Treatment:** Dividends = capital gains, focus on total return
- **Form Requirement:** 1099 C-corps only (no K-1 MLPs)

### Rebalancing Strategy
- **Frequency:** Quarterly (every 3 months)
- **Method:** Add new capital to underweight positions
- **No selling:** Avoid creating tax events from rebalancing
- **New capital source:** $20,000 quarterly DCA continuation

## Methodology

### Scoring System
```
Combined Score = (0.5 × 3M_momentum + 0.5 × 6M_momentum) / downside_volatility
```

### Constraints
1. **Position Constraints:**
   - Minimum: 3% ($1,800)
   - Maximum: 15% ($9,000)

2. **Sector Constraints (33% max each):**
   - Gold sector: FNV, AEM
   - Silver sector: PAAS, HL
   - Mixed precious: WPM (50/50 gold/silver)
   - Oil & Gas: All energy stocks
   - Ex-US Value: AVDV, DFIV, IVAL

3. **Filters:**
   - Positive combined momentum only
   - 1099 C-corps only (no K-1 partnerships)

## Project Structure

```
.
├── nbs/
│   ├── us_portfolio_allocation.py      # Main allocation engine
│   ├── portfolio_simulation.py         # Monte Carlo risk analysis
│   ├── oil_gas_comprehensive.py        # 26-stock energy sector analysis
│   ├── canadian_nyse_only.py          # Canadian energy (NYSE only)
│   └── canadian_oil_gas_high_yield.py # High-yield Canadian analysis
├── docs/
│   └── investment_decision_log.md      # Complete decision history
└── data/
    └── kasliwal_holdings_flat.csv      # INR portfolio context
```

## Usage

### Run Current Allocation
```bash
uv run python nbs/us_portfolio_allocation.py --min-allocation 0.03 --max-allocation 0.15
```

### Monte Carlo Simulation
```bash
uv run python nbs/portfolio_simulation.py
```

### Comprehensive Energy Analysis
```bash
uv run python nbs/oil_gas_comprehensive.py
```

## Next Quarter Checklist (Q2 2026)

### Data Update
- [ ] Fetch latest 3-year price history (Jan 2023 - Mar 2026)
- [ ] Update total return calculations with new dividends
- [ ] Verify all tickers still trade and have data

### Rebalancing Calculation
- [ ] Run `us_portfolio_allocation.py` with updated data
- [ ] Compare new allocation vs current holdings
- [ ] Calculate dollar amounts to add to each underweight position
- [ ] **Do not sell** overweight positions (tax-efficient rebalancing)

### New Capital Deployment
- [ ] Source: $20,000 new capital from quarterly DCA budget
- [ ] Method: Add to underweight positions only
- [ ] Formula: `new_target_weight - current_weight × portfolio_value`

### Sector Review
- [ ] Check if any sectors hit 33% cap
- [ ] Review if new stocks should be added to universe
- [ ] Verify no stocks converted to K-1 issuers (tax status changes)

### Momentum Regime Check
- [ ] Compare current 3M/6M momentum vs previous quarter
- [ ] Flag any stocks with negative momentum (pause DCA)
- [ ] Check if sector leadership changed (precious metals vs energy vs ex-US)

### Risk Monitoring
- [ ] Portfolio max drawdown vs -15% target
- [ ] Individual position drawdowns vs historical
- [ ] Correlation changes between sectors

### Execution
- [ ] DCA new capital over 1 month: 4 weekly buys
- [ ] Update position tracking spreadsheet
- [ ] Document any deviations from model in decision log

## Price Target Monitoring

Track quarterly to validate thesis:

| Asset | Current (Q1 2026) | Target | % to Target |
|-------|-------------------|--------|-------------|
| Gold | $TBD | $4,000/oz | TBD% |
| Silver | $TBD | $50/oz | TBD% |
| WTI Oil | $TBD | Supply crunch indicator | - |

If targets hit, consider taking partial profits and rotating to other opportunities.

## Key Insights

1. **Scale > Yield:** Don't chase high yields on small positions (Canadian 10% yields rejected)
2. **Concentration helps returns:** But sector caps prevent eliminating entire theses
3. **Tax structure matters:** 21% flat rate means total return > yield optimization
4. **Process > Prediction:** Systematic scoring beats thesis-only allocation
5. **Simplicity premium:** 10 positions with 1099s beats 22 positions with K-1 complexity

See `docs/investment_decision_log.md` for complete decision history and rationale.

## Dependencies

- Python 3.11+
- uv (package manager)
- yfinance (market data)
- pandas, numpy (data processing)
- click (CLI interface)

Install with:
```bash
uv sync
```

## License

Private investment research - not financial advice.
