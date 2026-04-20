# INR Personal Portfolio (India)

Personal investment portfolio in Indian Rupees - mutual funds and equities.

## Data Sources

| Source | Purpose |
|--------|---------|
| mfapi.in | Mutual fund NAV data |
| Manual snapshots | Portfolio state tracking |

## Scripts

| Script | Purpose |
|--------|---------|
| `fetch_mf_nav.py` | Fetch MF NAV from mfapi.in |
| `*.ipynb` | Analysis notebooks |

## Quick Start

```bash
# Fetch mutual fund NAV
uv run python india/scripts/fetch_mf_nav.py

# Search for a fund
uv run python -c "from india.scripts.fetch_mf_nav import search_mf; print(search_mf('gold')[:3])"
```

## Data Files

| File Pattern | Content |
|--------------|---------|
| `2026-01-21-*.csv` | Categorized holdings by asset class |
| `2026-01-21-*.xlsx` | Summary spreadsheets |
| `kasliwal_holdings_flat.csv` | Flat holdings export |

## Asset Categories

Based on 2026-01-21 snapshot:

| Category | File |
|----------|------|
| Gold | `2026-01-21-gold.csv` |
| Silver | `2026-01-21-silver.csv` |
| International | `2026-01-21-international.csv` |
| Indian Stocks | `2026-01-21-stocks-india.csv` |
| MF Debt | `2026-01-21-mf-debt.csv` |
| MF Size Factor | `2026-01-21-mf-size.csv` |
| MF Low Vol | `2026-01-21-mf-lowvol.csv` |
| MF Momentum | `2026-01-21-mf-momentum.csv` |

## mfapi.in Reference

Free API for Indian mutual fund NAV data.

```python
from india.scripts.fetch_mf_nav import get_latest_nav, search_mf

# Get NAV for a specific scheme
nav = get_latest_nav(119551)  # Nippon India Gold ETF

# Search by name
funds = search_mf("liquid fund")
```

Common scheme codes:
- 119551: Nippon India Gold ETF
- 120503: HDFC Liquid Fund
- 118989: PPFAS Flexi Cap Fund
