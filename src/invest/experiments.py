"""
Experiment consolidation — single source of truth across all autoresearch runs.

Reads research_log*.jsonl files (US + India, default + tagged + parallel),
flattens strategy params + backtest + MC fields, dumps to parquet.

CLI:
  uv run python -m invest.experiments consolidate <glob> <out.parquet>
  uv run python -m invest.experiments top <parquet> [--n 20] [--by score]
  uv run python -m invest.experiments importance <parquet>
  uv run python -m invest.experiments winner <glob>
"""

from __future__ import annotations

import glob as _glob
import json
import sys
from pathlib import Path

import polars as pl


# ─── Flatten ─────────────────────────────────────────────────────────────────
_STRAT_KEYS = [
    "lookbacks", "weights", "skip_days", "score_variant", "n_positions",
    "rebal_trigger", "rebal_min_hold", "rebal_max_hold", "rebal_jitter",
    "score_gap_pct", "max_dd_cap", "crash_p_mult", "regime_ma", "dd_stop_pct",
]
_BT_KEYS = ["sortino", "calmar", "max_dd", "cagr", "rebal_count", "avg_hold"]
_MC_KEYS = ["p5", "p25", "p50", "p75", "p95", "dd_wst",
             "p_loss", "p_dd_30", "p_dd_50"]


def _flatten(rec: dict, run_tag: str) -> dict:
    s = rec.get("strategy", {}) or {}
    bt = rec.get("backtest", {}) or {}
    mc = rec.get("mc12m", {}) or {}
    out = {
        "run_tag": run_tag,
        "iter": rec.get("iter"),
        "origin": rec.get("origin"),
        "score": rec.get("score"),
        "picks": ", ".join(rec.get("picks", []) or []),
        "n_picks": len(rec.get("picks", []) or []),
    }
    for k in _STRAT_KEYS:
        v = s.get(k)
        if isinstance(v, (list, tuple)):
            v = ",".join(str(x) for x in v)
        out[f"s_{k}"] = v
    for k in _BT_KEYS:
        out[f"bt_{k}"] = bt.get(k)
    for k in _MC_KEYS:
        out[f"mc_{k}"] = mc.get(k)
    return out


def _tag_from_filename(path: Path) -> str:
    stem = path.stem  # research_log[_<tag>]
    return stem.removeprefix("research_log").removeprefix("_") or "default"


# ─── Public API ──────────────────────────────────────────────────────────────
def consolidate(glob_pattern: str, out_parquet: str | Path) -> pl.DataFrame:
    """Merge all matching JSONL logs into one parquet. Returns the DataFrame."""
    files = sorted(Path(p) for p in _glob.glob(glob_pattern))
    if not files:
        raise FileNotFoundError(f"no files matched {glob_pattern}")

    rows: list[dict] = []
    for fp in files:
        tag = _tag_from_filename(fp)
        for line in fp.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_flatten(json.loads(line), tag))
            except json.JSONDecodeError:
                continue

    if not rows:
        raise ValueError(f"no valid rows in {len(files)} files")

    df = pl.DataFrame(rows)
    out = Path(out_parquet)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out)
    return df


def top_n(parquet: str | Path, n: int = 20, by: str = "score") -> pl.DataFrame:
    df = pl.read_parquet(parquet)
    return df.sort(by, descending=True, nulls_last=True).head(n)


def cross_run_winner(glob_pattern: str) -> dict | None:
    """Find the absolute best record across all matching log files."""
    best = None
    for fp in _glob.glob(glob_pattern):
        for line in Path(fp).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            score = rec.get("score", float("-inf"))
            if best is None or score > best.get("score", float("-inf")):
                rec["_source_file"] = fp
                best = rec
    return best


def param_importance(parquet: str | Path, target: str = "score") -> pl.DataFrame:
    """Per-strategy-param: count of unique values, mean target, top-quartile mean,
    and a simple discriminator (top_q_mean - bot_q_mean) / std(target).

    Discriminator > 0 means the param matters for `target`. Higher = stronger
    signal. Negative means the OPPOSITE — high target tends to come with low
    value of this param.
    """
    df = pl.read_parquet(parquet).filter(pl.col(target).is_not_null())
    if df.is_empty():
        return pl.DataFrame()

    overall_std = df[target].std()
    rows = []
    for col in [c for c in df.columns if c.startswith("s_")]:
        # Skip non-discrete (continuous) params handled the same — we just bucket
        sub = df.select([col, target]).drop_nulls()
        if sub.is_empty():
            continue
        n_unique = sub[col].n_unique()
        if n_unique < 2:
            continue

        # group by value
        agg = sub.group_by(col).agg(
            pl.len().alias("count"),
            pl.col(target).mean().alias("mean"),
        ).sort("mean", descending=True)

        top_q = agg.head(max(1, len(agg) // 4))["mean"].mean()
        bot_q = agg.tail(max(1, len(agg) // 4))["mean"].mean()
        discrim = (top_q - bot_q) / overall_std if overall_std and overall_std > 0 else 0.0
        rows.append({
            "param": col,
            "n_values": n_unique,
            "best_value": str(agg[0, col]),
            "best_mean": float(agg[0, "mean"]),
            "worst_value": str(agg[-1, col]),
            "worst_mean": float(agg[-1, "mean"]),
            "discriminator": discrim,
        })

    return pl.DataFrame(rows).sort("discriminator", descending=True, nulls_last=True)


# ─── CLI ─────────────────────────────────────────────────────────────────────
def _print_df(df: pl.DataFrame, title: str = "") -> None:
    if title:
        print(title)
    with pl.Config(tbl_rows=50, tbl_cols=30, fmt_str_lengths=80):
        print(df)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1

    cmd = argv[1]

    if cmd == "consolidate":
        if len(argv) < 4:
            print("usage: consolidate <glob> <out.parquet>", file=sys.stderr)
            return 2
        df = consolidate(argv[2], argv[3])
        print(f"consolidated {len(df)} rows from {df['run_tag'].n_unique()} runs → {argv[3]}")
        return 0

    if cmd == "top":
        if len(argv) < 3:
            print("usage: top <parquet> [--n N] [--by COL]", file=sys.stderr)
            return 2
        n = 20
        by = "score"
        for i, a in enumerate(argv[3:], start=3):
            if a == "--n" and i + 1 < len(argv):
                n = int(argv[i + 1])
            if a == "--by" and i + 1 < len(argv):
                by = argv[i + 1]
        df = top_n(argv[2], n=n, by=by)
        cols = ["run_tag", "iter", "origin", "score",
                "bt_sortino", "bt_calmar", "bt_max_dd", "bt_cagr",
                "mc_p_dd_30", "s_score_variant", "s_n_positions",
                "s_rebal_trigger", "s_regime_ma", "s_dd_stop_pct", "picks"]
        cols = [c for c in cols if c in df.columns]
        _print_df(df.select(cols), f"top {n} by {by}")
        return 0

    if cmd == "importance":
        if len(argv) < 3:
            print("usage: importance <parquet>", file=sys.stderr)
            return 2
        _print_df(param_importance(argv[2]), "param importance (discriminator = (top_q_mean - bot_q_mean)/std)")
        return 0

    if cmd == "winner":
        if len(argv) < 3:
            print("usage: winner <glob>", file=sys.stderr)
            return 2
        w = cross_run_winner(argv[2])
        if w is None:
            print("no records found")
            return 1
        print(json.dumps({k: v for k, v in w.items() if k != "strategy"}, indent=2))
        print("strategy:")
        print(json.dumps(w.get("strategy"), indent=2))
        return 0

    print(f"unknown command: {cmd}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
