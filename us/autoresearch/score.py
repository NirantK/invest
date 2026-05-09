"""
score.py — the file the autonomous research agent edits.

Current baseline: Martin-anchored composite (mom × smoothness × vol_factor × high_factor / ulcer_1y),
combined with 5-signal cross-sectional rank for diversification-friendly selection.

This file is loaded by us/scripts/backtest_v2.py via the --score-fn-from flag (TODO).
For now, the canonical scoring lives in us_portfolio_allocation.py:_score_one() and add_rank_scores().

To experiment, copy those functions here, modify, and point backtest_v2 at this file.

Iteration template:
    1. Read program.md (the autoresearch protocol)
    2. Read experiments.jsonl (the history of attempts)
    3. Pick the next hypothesis
    4. Edit ONE thing here
    5. Run: `uv run python us/scripts/backtest_v2.py`
    6. Append result to experiments.jsonl
    7. Decide keep/revert per program.md rules
"""
from __future__ import annotations

# Currently a thin wrapper that re-exports the production score.
# Phase 2: replace with experimental variants the agent has discovered.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from us_portfolio_allocation import (  # type: ignore  # noqa: E402
    _score_one as score_function,
    add_rank_scores as composite,
    _transform_for_sizing as sizing,
)

__all__ = ["score_function", "composite", "sizing"]

VERSION = "0.1.0-baseline"
HYPOTHESIS = "Baseline: Martin × smoothness × volume × 52WH boost. Cross-sectional rank composite."
