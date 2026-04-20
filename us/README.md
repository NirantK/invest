# US C-Corp Portfolio

Systematic portfolio allocation for Scaled Focus Inc via Interactive Brokers.

## Strategy

| Aspect | Approach |
|--------|----------|
| Method | Sortino-weighted momentum (3M+6M) |
| Sectors | Gold, Silver, Oil & Gas, Ex-US Value |
| Constraints | 3% min, 15% max per position; 33% max per sector |
| Tax | 1099 C-corps only (no K-1 MLPs) |
| Rebalancing | Quarterly, add capital only (never sell) |

## Scripts

| Script | Purpose |
|--------|---------|
| `us_portfolio_allocation.py` | Main allocation engine |
| `portfolio_simulation.py` | Monte Carlo risk analysis |
| `oil_gas_comprehensive.py` | Energy sector analysis |
| `ibkr_client.py` | IBKR API wrapper |
| `correlation_analysis.py` | Cross-asset correlation |

## Quick Start

```bash
# Run allocation
uv run python us/scripts/us_portfolio_allocation.py --min-allocation 0.03 --max-allocation 0.15

# Monte Carlo simulation
uv run python us/scripts/portfolio_simulation.py

# IBKR connection (requires TWS/Gateway running)
uv run python us/scripts/ibkr_client.py
```

## IBKR Setup

1. TWS: Edit > Global Configuration > API > Settings
2. Enable "ActiveX and Socket Clients"
3. Port: 7497 (TWS) or 4001 (Gateway)
4. Add to `.env`:
   ```
   IBKR_PORT=7497
   IBKR_CLIENT_ID=1
   ```

## Current Allocation (Q1 2026 Target)

| Ticker | Weight | Category |
|--------|--------|----------|
| PAAS | 15.25% | Silver miner |
| HL | 15.25% | Silver miner |
| AVDV | 11.86% | Ex-US Value |
| DFIV | 11.86% | Ex-US Value |
| AEM | 10.17% | Gold miner |
| WPM | 8.47% | Streamer (mixed) |
| IVAL | 8.47% | Ex-US Value |
| XOM | 6.78% | Oil major |
| SU | 6.78% | Canadian oil |
| FNV | 5.08% | Streamer (gold) |

**Status:** Not yet deployed. Initial DCA planned for Q1 2026.
