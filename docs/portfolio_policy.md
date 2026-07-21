# Portfolio Policy — US C-Corp Book (IBKR)

Adopted 2026-07-21. Change this file only with backtest evidence or an explicit
decision-log entry. The screener emits a TARGET; trades are the DIFF against the
current book, subject to the turnover budget below. No ad-hoc trades off a fresh
screener run.

## Sleeves and budgets (of ~$43k book)

| Sleeve | Budget | Contents | Managed by |
|--------|--------|----------|------------|
| Savings / CORE (Rule "Talmud Real") | ~13% NetLiq, target TBD at Aug rebalance | AEM, FNV, WPM — gold complex IS the anchor of this book, 3y+ hold | Manual. Annual review. No stop-loss. NEVER momentum-scored. Adds capped at $10k lifetime without a new decision-log entry. |
| Value picks | ≤30% | META, MSFT (FCF compounders), URNM, SRUUF (uranium supply deficit) — each bought on valuation, each needs a written thesis + exit condition | Manual. Quarterly thesis review. NEVER momentum-scored. No stop-loss; exit = thesis broken or target reached. |
| Momentum satellite | ~25% | 5–6 positions × ~$2k | Screener, monthly |
| Cash (SGOV) | $10k floor | SGOV — **untouchable** (owner instruction 2026-07-21) | Never sold to fund trades |

Account also holds free brokerage cash (~$42k as of 2026-07-21, NetLiq ~$84k).
Satellite buys are funded from exits first, then free cash — never from SGOV.

## Momentum satellite rules

- **Canonical run:** `uv run us/scripts/us_portfolio_allocation.py --capital 11000
  --max-positions 6 --min-allocation 0.10 --max-allocation 0.20
  --score-col score_rank --sizing equal`
- **Rank + equal weight, never raw-score sizing** — raw sizing let data artifacts
  (SNDK "+2102%", BW at -95% dd) take 15% weights.
- **Sanity gate:** any name with 12M momentum > +300% needs a manual check for
  spinoff/split artifacts before buying.
- **Entry:** in the top-6 rank output at month-end rebalance.
- **Exit:** falls below median PASS rank at month-end, OR -20% from entry price.
  Whichever first. Exits execute; they are not advisory.
- **Turnover budget:** max 3 satellite trades per month.
- **Regime overlay:** if SPY < 200dma at month-end, halve the satellite, park
  proceeds in SGOV. Momentum crashes cluster in broad-drawdown regimes.
- **Min position $1.5k.** Sub-$1k positions are forbidden — the 12-name tail of
  $300–500 lottery tickets (all one AI-infra/crypto macro trade, all -20 to -40%)
  is what this policy exists to prevent.

## Cadence

- **Monthly rebalance:** first Monday. Run screener, diff vs book, execute ≤3
  trades, log entry vs SPY benchmark in `docs/investment_decision_log.md`.
- **Quarterly thesis review:** uranium contract cycle / supply-demand, gold.
- **No parameter changes on trade days.** Tweak → backtest → log → then trade.

## What went wrong before (why these rules)

1. Screener re-run with different knobs each week → each run implied 100%
   turnover → nobody executed it → ad-hoc discretion did instead.
2. In-pain filter was an entry gate misread as portfolio advice; no exit rule
   existed at all, so losers were held past every signal.
3. Raw-score sizing concentrated on score outliers, which are usually data bugs.
4. Per-ticker caps without theme caps allowed ~50% of the book in one macro trade.
