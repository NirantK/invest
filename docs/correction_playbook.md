# 6M Tactical Sleeve — Correction Playbook

**Locked:** 2026-05-09
**Sleeve:** US C Corp / IBKR
**Config:** `score_4w × 10d × 8 pos × 1.0x` (6M Defensive)
**Sleeve size:** $17,800 (~20% of $89,778 NetLiq)
**Hold horizon:** ~6 months from entry, re-screen every 10 trading days

---

## The ONE override rule

**If SPY closes below $663.86 (-10% from 6mo peak of $737.62)** → exit entire tactical sleeve to SGOV. Do not re-enter for 30 days. Re-enter only after SPY closes above its 50DMA.

That's it. No other overrides. Breadth gate inside the screener handles regime shifts automatically (~18% of trading days historically end up in cash).

### Set this in IBKR today

| Alert | Trigger |
|---|---|
| SPY price drop | SPY ≤ $663.86 |
| SPY 200DMA cross | SPY ≤ $670.56 (early-warning, no action) |
| Sleeve drawdown | If sleeve mark-to-market ≤ $14,240 (-20% from $17,800), evaluate exit |

---

## Rebal cadence

- Re-run `pick_tactical.py --capital <current sleeve value> --positions 8 --leverage 1.0 --score score_4w` **every 10 trading days** (~14 rebals over 6mo)
- If picks change >50% (4+ swaps), execute the rotation
- If picks change <50% (≤3 swaps), execute only the swaps, hold the others
- Skip names already held heavy in the rest of the IBKR book (>3% NetLiq concentration)

---

## What "exit" means (mechanically)

If trigger hits during market hours:
```bash
# Liquidate each position to market or fast limit
uv run ~/.claude/skills/ibkr/ibkr.py sell SNDK --execute
uv run ~/.claude/skills/ibkr/ibkr.py sell MU --execute
... (all 8 names)

# Park proceeds in SGOV
uv run ~/.claude/skills/ibkr/ibkr.py buy SGOV <proceeds_amount> --execute
```

If trigger hits overnight: liquidate at market open next trading day. Do not panic-sell after-hours.

---

## What this playbook EXCLUDES (intentionally)

- No "average down" logic. Don't buy more if positions go red.
- No "take profits at +X%". Hold to next rebal date or exit trigger, whichever first.
- No discretionary swaps. Picker decides.
- No stop-loss per position. Sleeve-level drawdown is the only stop.
- No leverage adjustment up. 1.0x stays 1.0x until next strategy review.

---

## Re-evaluation triggers (when to revisit this whole playbook)

| Event | Action |
|---|---|
| 6 months elapsed (≈ 2026-11-09) | Full strategy review — rerun `return_max_3m.py` with current data, decide if 6M Defensive is still optimal |
| SPY -10% trigger fires | Pause + 30-day cooldown + re-evaluate before re-entering |
| Earnings shock on >2 holdings same week | Note in pm_book.md, no action unless SPY trigger fires |
| Margin debit accidentally > $0 | Sell SGOV to clear immediately |

---

## Single-source-of-truth references

- Strategy doc: `docs/return_max_6m_strategy.md`
- Sweep results: `us/autoresearch/return_max_6m_results.json`
- Live picker: `us/scripts/pick_tactical.py`
- Pending/executed trades: pm memory (`pm_trade_log.md`)
