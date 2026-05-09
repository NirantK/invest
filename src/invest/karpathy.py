"""
Claude-in-the-loop strategy proposer for autoresearch.

Spawns `claude --print --bare --model haiku` periodically with the leaderboard
and asks for 5 new candidate strategies in JSON. Cheap and effective steering
beyond random + greedy local search.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from invest.autoresearch import (
    LOOKBACK_CHOICES,
    REBAL_MAX_HOLD,
    REBAL_MIN_HOLD,
    REBAL_TRIGGERS,
    SCORE_GAP_CHOICES,
    SCORE_VARIANTS,
    Strategy,
    WEIGHT_CHOICES,
)
REBAL_JITTER = [0, 3, 5, 10]  # legacy display only — sampler no longer uses


PROMPT_TEMPLATE = """You are an investment research agent. You're optimising a portfolio
strategy for an Indian equity basket. Your goal is to maximise the **composite score**
= OOS_Sortino × OOS_Calmar × (1 - P(12M_drawdown<-30%)).

## Strategy parameter space

```python
lookbacks      ∈ {lookback_choices}
weights        ∈ {weight_choices}
skip_days      ∈ [0, 21]
score_variant  ∈ {score_variants}
n_positions    ∈ [2, 3, 4, 5, 7]
rebal_trigger  ∈ {rebal_triggers}
rebal_min_hold ∈ {rebal_min_hold}
rebal_max_hold ∈ {rebal_max_hold}
rebal_jitter   ∈ {rebal_jitter}
score_gap_pct  ∈ {score_gap_choices}
max_dd_cap     ∈ [0.30, 0.50, 0.75]
crash_p_mult   ∈ [0.5, 1.0, 2.0]
```

## Top {top_n} experiments so far

```json
{leaderboard}
```

## Bottom 5 (for what to AVOID)

```json
{bottom}
```

## Task

Propose **EXACTLY 5 NEW strategies**. Aim for diversity AND for hypotheses informed
by the leaderboard:
- If top strategies cluster on one score variant, test the next-most-similar
- If a param value never appears in the top 10, try it
- Don't just produce slight variants of #1; include at least one bold alternative

Return ONLY a JSON array of 5 strategy objects. Schema:

```json
[
  {{"lookbacks": [126,252,504], "weights": [0.4,0.4,0.2], "skip_days": 21,
    "score_variant": "martin", "n_positions": 4, "rebal_trigger": "fixed",
    "rebal_min_hold": 25, "rebal_max_hold": 40, "rebal_jitter": 0,
    "score_gap_pct": 0.10, "max_dd_cap": 0.50, "crash_p_mult": 1.0,
    "rationale": "1-line why this might beat current best"}},
  ...
]
```

Output JSON only, no prose, no markdown fences, no preamble."""


def _slim(rec):
    return {
        "score": round(rec["score"], 2),
        "strategy": rec["strategy"],
        "backtest": {k: round(v, 3) if isinstance(v, float) else v
                     for k, v in rec["backtest"].items()},
        "p_dd_30": round(rec["mc12m"].get("p_dd_30", 0), 3),
        "picks": rec.get("picks", [])[:5],
    }


def _proposal_to_strategy(p: dict) -> Strategy | None:
    try:
        return Strategy.from_dict(p)
    except (KeyError, ValueError, TypeError) as e:
        print(f"  [karpathy] bad proposal {e}: {str(p)[:200]}")
        return None


def make_callback(model: str = "claude-haiku-4-5-20251001",
                   timeout: int = 180,
                   proposal_log: Path | None = None):
    """Returns a callback(it, top, bottom) -> list[Strategy] usable with run_loop."""
    def _callback(it, top, bottom):
        if not top:
            return []
        prompt = PROMPT_TEMPLATE.format(
            lookback_choices=LOOKBACK_CHOICES,
            weight_choices=WEIGHT_CHOICES,
            score_variants=SCORE_VARIANTS,
            rebal_triggers=REBAL_TRIGGERS,
            rebal_min_hold=REBAL_MIN_HOLD,
            rebal_max_hold=REBAL_MAX_HOLD,
            rebal_jitter=REBAL_JITTER,
            score_gap_choices=SCORE_GAP_CHOICES,
            top_n=len(top),
            leaderboard=json.dumps([_slim(r) for r in top], indent=2),
            bottom=json.dumps([_slim(r) for r in bottom], indent=2),
        )
        cmd = [
            "claude", "--print",
            "--model", model,
            "--dangerously-skip-permissions",
            "--output-format", "text",
        ]
        print(f"  [karpathy] iter={it}: calling {model.split('-')[1]}...")
        t0 = time.time()
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True,
                                   text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"  [karpathy] timeout after {timeout}s")
            return []
        elapsed = time.time() - t0
        if proc.returncode != 0:
            print(f"  [karpathy] claude rc={proc.returncode}: {proc.stderr[:300]}")
            return []
        raw = proc.stdout.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start < 0 or end < 0:
            print(f"  [karpathy] no JSON array in output: {raw[:200]}")
            return []
        try:
            proposals = json.loads(raw[start:end + 1])
        except json.JSONDecodeError as e:
            print(f"  [karpathy] JSON parse failed: {e}")
            return []
        print(f"  [karpathy] +{len(proposals)} candidates ({elapsed:.1f}s)")
        if proposal_log:
            proposal_log.parent.mkdir(parents=True, exist_ok=True)
            with open(proposal_log, "a") as f:
                for p in proposals:
                    f.write(json.dumps({"iter": it, "proposal": p,
                                         "ts": time.time()}) + "\n")
        return [s for s in (_proposal_to_strategy(p) for p in proposals) if s]

    return _callback
