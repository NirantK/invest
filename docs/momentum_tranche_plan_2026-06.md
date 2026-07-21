# Momentum Rotation — 3-Tranche Deployment (June 2026)

**Created:** 2026-06-16 (IST) · **Method:** backtested winner = sortino-select + equal-weight + monthly cadence (see `docs/backtest_summary.md`)
**Account:** IBKR US C-Corp (live). Gateway must be running (`localhost:4001`) to execute.

## Decisions locked
- **Sells:** all 3 at once at the T1 open (no drip on exits we've decided to cut).
- **Buys:** 3 equal weekly tranches, averaging into all 15 names (~$483/name/week).
- **Execution:** human-in-the-loop. Each tranche = re-run screener → review drift → present DRY-RUN orders → wait for explicit "go" → `--execute`. **Never auto-execute.**

## Sells (T1 open, ~$11.7K proceeds)
| Sell | Shares | Est. proceeds | Note |
|---|---|---|---|
| VLO | 15 | ~$3,712 | +$57 — laggard vs picks |
| LIT | 40 | ~$3,328 | −$295 — weakest, lithium rolling over |
| NET | 20 | ~$4,702 | −$209 — screener rank #75, ~zero momentum |

Cash for buys = ~$11.7K proceeds + $10K new = **~$21,742**.

## Buys — top 15 (backtested method, SNDK excluded), equal-weight
Total ~$1,449/name; **~$483/name per tranche**.

| # | Ticker | Sleeve |
|---|---|---|
| 1 | LITE | AI Infra |
| 2 | BE | AI Infra |
| 3 | TSEM | AI Infra |
| 4 | INTC | AI Infra |
| 5 | HUT | AI Infra |
| 6 | COHR | AI Infra |
| 7 | NBIS | Software Infra (ClickHouse ~25%) |
| 8 | APLD | AI Infra |
| 9 | SII | Precious Mgr (Sprott) |
| 10 | IREN | AI Infra |
| 11 | FRDM | EM factor |
| 12 | CVE | Energy |
| 13 | CIFR | AI Infra |
| 14 | SU | Energy |
| 15 | AVDV | Intl value |

## Tranche schedule (US market open 09:30 ET = 19:00 IST)
| Tranche | Date | Buys |
|---|---|---|
| T1 | Tue 2026-06-16 | sells + ~$7,247 |
| T2 | Tue 2026-06-23 | ~$7,247 |
| T3 | Tue 2026-06-30 | ~$7,247 |

## Weekly review checklist (run each Tuesday)
1. `cd executive-function/invest && uv run python scripts/us_portfolio_allocation.py` + the sortino/equal-weight/SNDK-excluded/`current_dd >= -25%` top-15 method.
2. Report drift vs prior week (new entrants, drops, rank changes — esp. whether gold/ag/Cameco have cleared the −25% drawdown gate yet).
3. Present that week's tranche as DRY-RUN IBKR orders.
4. Wait for explicit approval, then `--execute`.

## Universe changes made this session
- Added: SII (Precious Mgr), CCJ (Uranium, in thesis group), Agriculture sleeve (NTR/MOS/CF/ADM/CTVA), Software Infra sleeve (NET/SNOW/NBIS).
- Could not add (private, no ticker): ClickHouse, Render, Databricks, Vercel. (K-1 vehicles DBA/CORN/WEAT excluded by choice; cotton/rice have no clean vehicle.)
