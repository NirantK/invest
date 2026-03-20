# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Commands

```bash
# Install dependencies
uv sync

# Run main allocation engine (Sortino-weighted momentum)
uv run python us/scripts/us_portfolio_allocation.py --min-allocation 0.03 --max-allocation 0.15 --capital 40000

# Run backtest (walk-forward validated, 6 momentum flavors)
uv run python us/scripts/backtest.py
uv run python us/scripts/backtest.py --top 20 --period 5y --max-dd-cap 0.50

# Monte Carlo risk simulation (3-month forward VaR)
uv run python us/scripts/portfolio_simulation.py

# Sector deep-dive
uv run python us/scripts/oil_gas_comprehensive.py

# Lint
uv run ruff check us/scripts/ india/scripts/
uv run ruff format --check us/scripts/ india/scripts/
```

## Code Style

- **Ruff** for linting+formatting, 88-char lines, double quotes (see `pyproject.toml`)
- Happy path conventions — no try-except blocks
- Vectorize with numpy; use polars over pandas for new code
- Descriptive variable names, enums not magic ints
- Runtime pruning over dead code (filter at execution, don't leave commented blocks)
- **Parquet for all data caches** — never use npz, pickle only for legacy per-scheme MF caches

## Architecture

### Two Portfolios

| Portfolio | Location | Data Source | Purpose |
|-----------|----------|-------------|---------|
| US C-Corp (IBKR) | `us/scripts/` | yfinance, IBKR API | Momentum-based US equity allocation |
| INR Personal | `india/scripts/` | mfapi.in | Indian mutual fund analysis |

### US Scripts — Data Flow

```
us_portfolio_allocation.py    ← Main entry point (click CLI)
  ├── fetch_total_return_index()  → polars DataFrame of adjusted prices
  ├── build_scores()              → per-ticker momentum/risk metrics
  ├── apply_thesis_groups()       → picks best ETF per thesis (fee-adjusted)
  ├── apply_etf_overlap()         → blocks constituents held inside selected ETFs
  ├── allocate()                  → iterative min/max constraint solver
  └── print_*()                   → rich console output

backtest.py                   ← Walk-forward parameter sweep
  ├── Uses data_utils.py for fetching (numpy arrays, not polars)
  ├── 6 LogVariant momentum flavors (arith, log, ewma, vnorm, accel, trim)
  ├── ProcessPoolExecutor with shared-memory
  └── backtest_reports.py for scenario analysis output

data_utils.py                 ← Shared data layer
  ├── daily_disk_cache()          → pickle cache, auto-stale after midnight
  ├── fetch_all_numpy()           → aligned (n_days, n_tickers) matrices
  ├── build_total_return()        → vectorized dividend-adjusted prices
  ├── build_earnings_momentum()   → YoY EPS growth matrix
  └── fetch_all_mf_numpy()        → Indian MF data with incremental caching
```

### Key Design Patterns

- **Daily disk cache**: All yfinance/mfapi fetches are cached as pickle files in `*/data/price_cache/` and `*/data/mf_nav_cache/`. Cache key includes today's date; stale files auto-evict. This means re-runs within a day are instant.
- **Thesis groups**: Competing ETFs for same thesis (e.g., URA vs URNM vs URNJ for uranium) — only the top scorer survives, fee-adjusted.
- **ETF overlap blocking**: If an ETF wrapper is selected (e.g., GOAU), its constituent individual stocks (AEM, WPM, etc.) are blocked to avoid double exposure.
- **Dual data backends**: `us_portfolio_allocation.py` uses polars DataFrames; `backtest.py` and `data_utils.py` use raw numpy arrays for speed. Don't mix them.

### Scoring System

Composite momentum score: `(weighted_momentum × smoothness) / downside_volatility`

- **Momentum**: 20% × 3M + 40% × 6M + 40% × 12M (all skip last 21 trading days)
- **Smoothness**: geometric mean of R² (trend linearity) and FIP (frog-in-the-pan: fraction of positive daily returns)
- **Downside vol**: annualized std of negative returns only

### Allocation Constraints

- Position: 3% min, 15% max (per-ticker overrides in `TICKER_MAX_ALLOC`)
- Max 25 positions
- Only positive momentum passes
- Iterative renormalization loop (up to 100 rounds) to satisfy all constraints

### IBKR Integration

Managed via skill at `~/.claude/skills/ibkr/ibkr.py` — not in this repo. Requires TWS/Gateway running with API enabled.

```bash
# Read operations
uv run ~/.claude/skills/ibkr/ibkr.py positions        # All positions with P&L
uv run ~/.claude/skills/ibkr/ibkr.py account           # Account summary (cash, equity, margin)
uv run ~/.claude/skills/ibkr/ibkr.py quote AAPL        # Real-time quote
uv run ~/.claude/skills/ibkr/ibkr.py quotes AAPL MSFT  # Multiple quotes
uv run ~/.claude/skills/ibkr/ibkr.py value              # Portfolio value breakdown
uv run ~/.claude/skills/ibkr/ibkr.py orders             # Open orders

# Buy/Sell (dry-run by default, add --execute to place)
uv run ~/.claude/skills/ibkr/ibkr.py buy VALE 1000              # Buy $1000 of VALE (dry run)
uv run ~/.claude/skills/ibkr/ibkr.py buy VALE 1000 --execute    # Actually place order
uv run ~/.claude/skills/ibkr/ibkr.py sell VALE                  # Sell all (dry run)
uv run ~/.claude/skills/ibkr/ibkr.py sell VALE --shares 50      # Sell 50 shares
uv run ~/.claude/skills/ibkr/ibkr.py sell VALE --amount 500     # Sell $500 worth

# Cancel orders
uv run ~/.claude/skills/ibkr/ibkr.py cancel 12345               # By order ID
uv run ~/.claude/skills/ibkr/ibkr.py cancel --symbol VALE       # All for symbol
uv run ~/.claude/skills/ibkr/ibkr.py cancel --all               # Cancel everything

# JSON output (any command)
uv run ~/.claude/skills/ibkr/ibkr.py positions --format json
```

| Mode | Gateway Port | TWS Port |
|------|--------------|----------|
| Paper | 4002 | 7497 |
| Live | 4001 | 7496 |

## Data Directories

- `us/data/price_cache/` — yfinance pickle cache (gitignored, regenerates)
- `us/data/mf_nav_cache/` — MF NAV per-scheme pickle cache (legacy, gitignored)
- `us/data/mf_nav_consolidated.parquet` — consolidated MF NAV matrix (fast reload)
- `us/data/mf_schemes_direct_growth.parquet` — master list of Direct Growth MF schemes
- `india/data/` — portfolio snapshots, allocation docs
- `docs/` — decision log, research notes, brainstorms

## Caching Policy

**All caches must use parquet.** Do not use pickle, npz, or Python disk caches for new code. Existing pickle caches (`price_cache/`, `mf_nav_cache/`) are legacy — migrate to parquet when touched. Consolidated parquet caches (e.g. `mf_nav_consolidated.parquet`) should be the primary read path; per-file caches are only for incremental API updates.

## Decision Log

All investment decisions and rationale go in `docs/investment_decision_log.md`. Monthly rebalancing entries follow the pattern "Part X: Month YYYY Monthly Rebalancing".
