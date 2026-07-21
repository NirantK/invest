"""Re-derive adj_close from cached raw close + (cached or freshly fetched)
corp_actions, using the latest split-inference logic.

Cheap: only fetches corp_actions if not already cached (1 credit each).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_genka_prices import (  # noqa: E402
    BASE,
    HEADERS,
    OUT_DIR,
    INDEX_PATH,
    _get_with_retry,
    adjust_closes,
)


def reprocess_one(client: httpx.Client, parquet_path: Path) -> dict:
    symbol = parquet_path.stem
    df = pl.read_parquet(parquet_path)

    ca_path = OUT_DIR / f"{symbol}.corp_actions.json"
    if ca_path.exists():
        actions = json.loads(ca_path.read_text())
    else:
        r = _get_with_retry(client, f"{BASE}/latest/prices/{symbol}/corp-actions")
        r.raise_for_status()
        actions = r.json()["data"]["items"]
        ca_path.write_text(json.dumps(actions, default=str))

    bars = [
        {
            "trade_date": d,
            "close": float(c),
            "isin": isin or "",
        }
        for d, c, isin in zip(
            df["date"].to_list(),
            df["close"].to_list(),
            df["isin"].to_list(),
        )
    ]
    adj = adjust_closes(bars, actions)

    out = pl.DataFrame({
        "date": df["date"],
        "close": df["close"],
        "adj_close": adj,
        "volume": df["volume"],
        "isin": df["isin"],
    }).sort("date")
    out.write_parquet(parquet_path)

    closes = out["adj_close"].to_numpy()
    if len(closes) > 1:
        rets = closes[1:] / closes[:-1] - 1.0
        max_ret = float(max(abs(rets.max()), abs(rets.min())))
    else:
        max_ret = 0.0

    n_splits = sum(
        1 for a in actions
        if a["kind"] in {"split", "bonus"} and a.get("factor")
    )

    return {
        "ticker": symbol,
        "first_date": out["date"][0],
        "last_date": out["date"][-1],
        "n_bars": len(out),
        "n_corp_actions": len(actions),
        "n_splits_bonuses": n_splits,
        "max_daily_return_adj": max_ret,
    }


def main() -> None:
    paths = sorted(OUT_DIR.glob("*.parquet"))
    print(f"Reprocessing {len(paths)} parquets...", flush=True)
    index: dict[str, dict] = {}
    with httpx.Client(headers=HEADERS) as client:
        for i, p in enumerate(paths, 1):
            t0 = time.time()
            try:
                info = reprocess_one(client, p)
            except Exception as e:
                print(f"[{i:3d}/{len(paths)}] {p.stem:14s} ERROR {type(e).__name__}: {e}", flush=True)
                continue
            index[p.stem] = info
            dt = time.time() - t0
            print(
                f"[{i:3d}/{len(paths)}] {p.stem:14s} bars={info['n_bars']:5d} "
                f"splits={info['n_splits_bonuses']} "
                f"max_ret={info['max_daily_return_adj']:+.2%} ({dt:.2f}s)",
                flush=True,
            )

    # merge into existing index
    existing: dict = {}
    if INDEX_PATH.exists():
        existing = json.loads(INDEX_PATH.read_text())
    tickers_dict = existing.get("tickers", {})
    tickers_dict.update(index)
    summary = {
        "as_of": time.strftime("%Y-%m-%d"),
        "n_tickers_total": existing.get("n_tickers_total", len(index)),
        "n_tickers_fetched": len(tickers_dict),
        "n_tickers_missing": existing.get("n_tickers_missing", 0),
        "missing": existing.get("missing", []),
        "tickers": tickers_dict,
    }
    INDEX_PATH.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote index -> {INDEX_PATH}")

    bad = [
        (t, v["max_daily_return_adj"])
        for t, v in tickers_dict.items()
        if isinstance(v, dict) and v.get("max_daily_return_adj", 0) > 0.5
    ]
    if bad:
        print(f"\nWARNING: {len(bad)} tickers still have >50% single-day adj return:")
        for t, r in sorted(bad, key=lambda x: -x[1]):
            print(f"  {t:14s} {r:+.2%}")


if __name__ == "__main__":
    main()
