# Karpathy-mode Autoresearch — Strategy Discovery Loop

You are an autonomous research agent searching for an Indian-equity portfolio
strategy that minimises **time underwater** while preserving CAGR.

## Your loop (DO THIS REPEATEDLY UNTIL TARGET MET)

1. **Read** `history.jsonl` (your own past experiments) — last 30 entries are most relevant.
2. **Edit** `strategy.json` — propose the next strategy you want to try.
3. **Run** `uv run python run_one.py` — runs walk-forward backtest + stress MC + scoring.
4. **Read** the new line in `history.jsonl` to see how the strategy performed.
5. **Decide** what to change next based on results, then repeat from step 2.

Do NOT exit, write reports, or wait for confirmation. Just keep iterating.

## Target (stop only when ALL of these are met)

- `pain_ratio` ≥ **8.0**  (Becker Pain Ratio = CAGR / mean(|DD|))
- `max_dd_dur_months` ≤ **20**  (longest underwater stretch under 20 months)
- `cagr` ≥ **0.30**  (30% annualised, otherwise it's not worth the effort)
- `bt.rebal_count` ≥ 30  (enough rebals for the metrics to be reliable)

If you've tried 200+ experiments without hitting target, write a summary
in `STUCK.md` explaining what you've ruled out and what you'd try with
more time. Then stop.

## Strategy file format (`strategy.json`)

```json
{
  "lookbacks": [126, 252, 504],
  "weights": [0.5, 0.3, 0.2],
  "skip_days": 21,
  "score_variant": "sortino_vnorm",
  "n_positions": 4,
  "rebal_trigger": "score_gap",
  "rebal_min_hold": 25,
  "rebal_max_hold": 45,
  "rebal_jitter": 5,
  "score_gap_pct": 0.10,
  "max_dd_cap": 0.50,
  "crash_p_mult": 1.0,
  "regime_ma": 150,
  "dd_stop_pct": 0.20,
  "target_vol": 0.20,
  "vol_lookback": 42,
  "weight_mode": "sqrt_score",
  "vol_state_mode": "defensive"
}
```

## Search space (allowed values)

| Field | Choices |
|---|---|
| lookbacks | (21,63,252) (42,126,252) (63,126,252) (126,252,504) (252,504,756) (252,504,1260) (504,756,1260) |
| weights | sum to 1.0; e.g. (0.5,0.3,0.2), (0.4,0.4,0.2), (0.3,0.3,0.3), (0.7,0.2,0.1), (0.1,0.3,0.6) |
| skip_days | 0 or 21 |
| score_variant | sortino_pricemom, sortino_vnorm, martin, wtmf, baltas |
| n_positions | 3, 4, 5, 7, 10, 15 |
| rebal_trigger | fixed, name_change, score_gap |
| rebal_min_hold | 15, 20, 25, 30 |
| rebal_max_hold | 35, 40, 50, 60, 80 |
| rebal_jitter | 0, 3, 5, 10 |
| score_gap_pct | 0.05, 0.10, 0.15, 0.25, 0.40 |
| max_dd_cap | 0.30, 0.50, 0.75 |
| crash_p_mult | 0.5, 1.0, 2.0 |
| regime_ma | 0 (off), 100, 150, 200 |
| dd_stop_pct | 0 (off), 0.15, 0.20, 0.30 |
| target_vol | 0 (off), 0.15, 0.20, 0.25, 0.30 |
| vol_lookback | 21, 42, 63 |
| weight_mode | equal, score, sqrt_score |
| vol_state_mode | off, moderate, aggressive, defensive |

## What each metric means (in your `history.jsonl`)

- `pain_ratio` — primary target. Higher = better. Becker formula CAGR / mean(|DD|).
- `max_dd_dur_months` — longest single underwater stretch. The user's main pain.
- `avg_dd_dur_months` — typical underwater stretch.
- `cagr`, `max_dd`, `sortino`, `calmar` — standard backtest metrics.
- `mc12m.p_dd_30`, `p_dd_50` — stress MC probabilities of catastrophic drawdowns.
- `picks` — the actual tickers selected by the strategy at "today's date".

## How to read history.jsonl efficiently

Use `tail -n 30 history.jsonl | python3 -c 'import sys,json; [print(json.dumps({k:v for k,v in json.loads(l).items() if k in {"strategy","backtest","score"}}, separators=(",",":"))[:300]) for l in sys.stdin]'`
to see compact recent results. Or grep for highest scores:
`sort -t, -k... history.jsonl` (or just read the file and pick mentally).

## Tips for fast convergence

1. **Look at param importance** — if every top-10 has `weight_mode = sqrt_score`, don't waste iters on `equal`.
2. **Mutate one knob at a time** when greedy-improving; when stuck, mutate two.
3. **Try bold moves periodically** — every ~10 iters, change `score_variant` entirely or jump to a different lookback regime to escape local optima.
4. **Watch for over-fitting** — if `bt.calmar` is high but `mc12m.p_dd_30` is also high, the backtest is lucky on 30y but stress MC sees future trouble.
5. **The user's hard pain criterion**: `max_dd_dur_months > 24` is unacceptable regardless of returns. Drop strategies that produce this even if `pain_ratio` looks great.

## Files

- `program.md` (this file) — instructions, do not modify
- `strategy.json` — your live strategy params, edit each iteration
- `run_one.py` — the experiment runner, do not modify
- `history.jsonl` — append-only log written by run_one.py, read it
- `STUCK.md` — write here only if you give up
- `WINNER.json` — write here only if you hit target

## Now begin

Read history.jsonl (it may be empty initially), edit strategy.json with your
first proposal, run `uv run python run_one.py`, read the result, decide your
next move. Keep going.
