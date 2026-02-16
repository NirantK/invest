# Print Layer Consolidation for us_portfolio_allocation.py

**Date:** 2026-02-16
**Status:** Decided

## What We're Building

Consolidated print output for the portfolio allocation script using `rich` library. Replaces 11 scattered print sections (~200 lines of f-strings) with 3 structured outputs.

## Key Decisions

1. **Use `rich.table.Table`** for all tabular output (replaces f-string alignment)
2. **3-table layout:**
   - `print_scores_table(scores)` — all per-ticker metrics in one table
   - `print_allocation_table(alloc, capital)` — final allocation + weekly DCA
   - `print_portfolio_summary(alloc, scores, capital)` — risk metrics, category exposure, MSTR footnote
3. **Trim aggressively** — remove banners, notes section, "improvements" list, raw weights dump
4. **MSTR DCA** — footnote in summary panel, not a separate section

## Design: 3-Table Layout

### Table 1: Scores (`print_scores_table`)
Columns: Ticker | 3M | 6M | 12M | Wt Mom | Quality | Score | Max DD | Status

- Merges current momentum table + drawdown table
- Status column: PASS/FAIL based on combined momentum > 0
- Color: green for PASS, red for FAIL (rich styling)

### Table 2: Allocation (`print_allocation_table`)
Columns: Ticker | $ Alloc | Weight% | Price | Shares | Weekly DCA

- Merges current allocation + weekly DCA plan
- Only shows active positions (alloc > 0)

### Table 3: Portfolio Summary (`print_portfolio_summary`)
`rich.Panel` with key-value pairs:

```
Portfolio Risk
  Positions: 12 | Top 3: 45.2% | Max weight: 18.1%
  Vol: 22.1% | Downside vol: 15.3%

Momentum
  3M: +8.2% | 6M: +12.1% | 12M: +18.5%
  Quality: 0.72 | Score: 3.41

Drawdown
  Max DD: -18.2% | Current: -3.1% | Worst 3M: -12.4%
  Pain ratio: 1.02

Categories
  Precious Metals: $8,000 (20.0%)
  Energy: $12,000 (30.0%)
  ...

MSTR: DCA $40/mo (momentum: -2.1%)
```

## What's Removed

- "US PORTFOLIO ALLOCATION" banner + improvements list
- "DRAWDOWN ANALYSIS" separate section header
- Raw weights before constraints
- "NOTES" section (static text)
- Duplicate category display (allocation by category + category exposure)
