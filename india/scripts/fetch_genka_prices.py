"""Fetch clean daily price history for India AI-infra universe from genka.dev.

For each ticker:
- Paginates `/latest/prices/{symbol}` (1 credit per call, 500 bars max) back to
  the earliest available bhavcopy date (1995-01-02).
- Pulls `/latest/prices/{symbol}/corp-actions` (1 credit) for splits + bonuses.
- Back-adjusts pre-event closes by cumulative split/bonus factor so we get a
  continuous, split-adjusted close series (Tickertape-style `adj` flavour).
- Writes per-ticker parquet to india/data/genka_prices/{TICKER}.parquet
  with columns date (str YYYY-MM-DD), close (float, raw), adj_close (float).

Why: yfinance corp-action gaps caused phantom 9900% jumps on bonus/split days
(GOLDBEES/BANKBEES/NIFTYBEES on 2019-12-23, INDIAMART listing-day pop). genka
serves origin NSE bhavcopy; we re-derive adjustment locally from corp-actions.
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

from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402

API_KEY = "imk_live_ibm5GwMMUb0t7QtQEKPLQx9t7YIWPHRh"
BASE = "https://genka.dev"
HEADERS = {"X-API-Key": API_KEY}
EARLIEST = "1995-01-02"
PAGE_LIMIT = 500
OUT_DIR = ROOT / "data" / "genka_prices"
INDEX_PATH = ROOT / "data" / "genka_prices_index.json"


def _get_with_retry(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    last_exc: Exception | None = None
    last_status: int | None = None
    for attempt in range(5):
        try:
            r = client.get(url, params=params, timeout=120.0)
            if r.status_code >= 500:
                last_status = r.status_code
                wait = 2 ** attempt
                print(f"    retry {attempt + 1}/5 after {wait}s: HTTP {r.status_code}", flush=True)
                time.sleep(wait)
                continue
            return r
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            last_exc = e
            wait = 2 ** attempt
            print(f"    retry {attempt + 1}/5 after {wait}s: {type(e).__name__}", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Failed after 5 retries: {last_exc} status={last_status}")


def fetch_bars(client: httpx.Client, symbol: str) -> list[dict]:
    """Paginate all bars for symbol, oldest-first."""
    bars: list[dict] = []
    seen_dates: set[str] = set()
    to_date: str | None = None
    pages = 0
    while True:
        params = {"from": EARLIEST, "limit": PAGE_LIMIT}
        if to_date is not None:
            params["to"] = to_date
        r = _get_with_retry(client, f"{BASE}/latest/prices/{symbol}", params=params)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        payload = r.json()
        page = payload["data"]["data"]
        if not page:
            break
        new_bars = [b for b in page if b["trade_date"] not in seen_dates]
        if not new_bars:
            break
        for b in new_bars:
            seen_dates.add(b["trade_date"])
        bars.extend(new_bars)
        pages += 1
        has_more = payload["data"].get("has_more", False)
        if not has_more:
            break
        oldest = min(b["trade_date"] for b in page)
        # next page: bars strictly older than oldest
        to_date = oldest
        if pages > 60:  # safety: ~30 years of trading days / 500 = ~16 pages
            break
    bars.sort(key=lambda b: b["trade_date"])
    return bars


def fetch_corp_actions(client: httpx.Client, symbol: str) -> list[dict]:
    r = _get_with_retry(client, f"{BASE}/latest/prices/{symbol}/corp-actions")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()["data"]["items"]


def _round_factor(raw: float) -> float:
    """Snap inferred split factor to the nearest clean ratio.

    Splits/bonuses produce clean ratios: 2, 3, 4, 5, 10, 100, 3/2 (1.5), 5/2 (2.5).
    """
    candidates = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0, 100.0]
    best = min(candidates, key=lambda c: abs(raw - c) / c)
    if abs(raw - best) / best < 0.20:  # within 20% of a clean ratio
        return best
    return raw  # un-snapped, but at least apply something


def infer_isin_factors(bars: list[dict]) -> list[tuple[str, float]]:
    """Detect splits via ISIN change + close ratio.

    When two consecutive bars have different ISINs and the close ratio is far
    from 1.0, that's a split that genka's corp-actions feed missed (common for
    ETFs like GOLDBEES, NIFTYBEES, BANKBEES).
    """
    factors: list[tuple[str, float]] = []
    for prev, cur in zip(bars[:-1], bars[1:]):
        prev_isin = prev.get("isin") or ""
        cur_isin = cur.get("isin") or ""
        if not prev_isin or not cur_isin or prev_isin == cur_isin:
            continue
        prev_close = float(prev["close"])
        cur_close = float(cur["close"])
        if cur_close <= 0:
            continue
        ratio = prev_close / cur_close
        if 0.7 < ratio < 1.4:
            continue  # not a split
        factor = _round_factor(ratio)
        factors.append((cur["trade_date"], factor))
    return factors


def _max_calendar_gap_days(bars: list[dict]) -> int:
    from datetime import date
    if len(bars) < 2:
        return 0
    max_gap = 0
    for prev, cur in zip(bars[:-1], bars[1:]):
        d1 = date.fromisoformat(prev["trade_date"])
        d2 = date.fromisoformat(cur["trade_date"])
        gap = (d2 - d1).days
        if gap > max_gap:
            max_gap = gap
    return max_gap


def infer_residual_split_factors(bars: list[dict], adj: list[float]) -> list[tuple[str, float]]:
    """After applying known corp-actions, scan for any remaining single-day
    return >40% in adj series. If consecutive trade days, infer split factor.
    """
    from datetime import date
    factors: list[tuple[str, float]] = []
    for i in range(len(adj) - 1):
        a0 = adj[i]
        a1 = adj[i + 1]
        if a0 <= 0 or a1 <= 0:
            continue
        d1 = date.fromisoformat(bars[i]["trade_date"])
        d2 = date.fromisoformat(bars[i + 1]["trade_date"])
        gap_days = (d2 - d1).days
        if gap_days > 7:
            continue  # data gap, not a split
        ratio = a0 / a1
        if 0.7 < ratio < 1.4:
            continue
        factor = _round_factor(ratio)
        if abs(factor - 1.0) < 0.05:
            continue
        factors.append((bars[i + 1]["trade_date"], factor))
    return factors


def adjust_closes(bars: list[dict], actions: list[dict]) -> list[float]:
    """Back-adjust raw close by cumulative split + bonus factor.

    For a split with factor=N (1 share -> N shares, price /= N), all bars with
    trade_date < ex_date get divided by N.
    Bonus 1:1 -> factor=2, same arithmetic (1 old + 1 new for free).
    Also applies ISIN-inferred splits when corp-actions feed is empty.
    """
    factors: list[tuple[str, float]] = []
    seen_dates: set[str] = set()
    for a in actions:
        if a["kind"] in {"split", "bonus"} and a.get("factor"):
            factors.append((a["ex_date"], float(a["factor"])))
            seen_dates.add(a["ex_date"])
    for d, f in infer_isin_factors(bars):
        # don't double-apply if corp-actions already had it (within 3 days)
        nearby = any(abs((pl.lit(d) - pl.lit(s)).days if False else 0) <= 3 for s in seen_dates)
        # simpler: skip if exact date already covered or within 3 days
        skip = False
        for s in seen_dates:
            if s == d:
                skip = True
                break
            try:
                from datetime import date
                d1 = date.fromisoformat(d)
                d2 = date.fromisoformat(s)
                if abs((d1 - d2).days) <= 3:
                    skip = True
                    break
            except ValueError:
                pass
        if not skip:
            factors.append((d, f))
            seen_dates.add(d)
    factors.sort()  # oldest first

    def _apply(factors_list: list[tuple[str, float]]) -> list[float]:
        out = []
        for b in bars:
            d = b["trade_date"]
            c = float(b["close"])
            cum = 1.0
            for ex_date, f in factors_list:
                if d < ex_date:
                    cum *= f
            out.append(c / cum)
        return out

    adj = _apply(factors)
    # Second pass: scan for any residual single-day jumps and add inferred factors
    extra = infer_residual_split_factors(bars, adj)
    if extra:
        for d, f in extra:
            factors.append((d, f))
        factors.sort()
        adj = _apply(factors)
    return adj


def process_ticker(client: httpx.Client, symbol: str) -> dict | None:
    bars = fetch_bars(client, symbol)
    if not bars:
        return None
    actions = fetch_corp_actions(client, symbol)
    # cache corp_actions for offline re-adjustment
    ca_path = OUT_DIR / f"{symbol}.corp_actions.json"
    ca_path.write_text(json.dumps(actions, default=str))
    adj = adjust_closes(bars, actions)

    df = pl.DataFrame({
        "date": [b["trade_date"] for b in bars],
        "close": [float(b["close"]) for b in bars],
        "adj_close": adj,
        "volume": [int(b.get("volume") or 0) for b in bars],
        "isin": [b.get("isin") or "" for b in bars],
    })
    df = df.sort("date")
    out_path = OUT_DIR / f"{symbol}.parquet"
    df.write_parquet(out_path)

    # sanity: max single-day adj return
    closes = df["adj_close"].to_numpy()
    if len(closes) > 1:
        rets = closes[1:] / closes[:-1] - 1.0
        max_ret = float(max(abs(rets.max()), abs(rets.min())))
    else:
        max_ret = 0.0

    return {
        "ticker": symbol,
        "first_date": df["date"][0],
        "last_date": df["date"][-1],
        "n_bars": len(df),
        "n_corp_actions": len(actions),
        "n_splits_bonuses": sum(
            1 for a in actions
            if a["kind"] in {"split", "bonus"} and a.get("factor")
        ),
        "max_daily_return_adj": max_ret,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tickers = sorted(AI_INFRA_UNIVERSE.keys())
    print(f"Fetching {len(tickers)} tickers from genka...", flush=True)

    index: dict[str, dict] = {}
    missing: list[str] = []

    with httpx.Client(headers=HEADERS) as client:
        for i, t in enumerate(tickers, 1):
            t0 = time.time()
            existing = OUT_DIR / f"{t}.parquet"
            if existing.exists():
                df = pl.read_parquet(existing)
                closes = df["adj_close"].to_numpy()
                if len(closes) > 1:
                    rets = closes[1:] / closes[:-1] - 1.0
                    max_ret = float(max(abs(rets.max()), abs(rets.min())))
                else:
                    max_ret = 0.0
                index[t] = {
                    "ticker": t,
                    "first_date": df["date"][0],
                    "last_date": df["date"][-1],
                    "n_bars": len(df),
                    "n_corp_actions": -1,
                    "n_splits_bonuses": -1,
                    "max_daily_return_adj": max_ret,
                    "cached": True,
                }
                print(f"[{i:3d}/{len(tickers)}] {t:14s} CACHED  bars={len(df)}", flush=True)
                continue
            try:
                info = process_ticker(client, t)
            except Exception as e:
                dt = time.time() - t0
                missing.append(t)
                print(f"[{i:3d}/{len(tickers)}] {t:14s} ERROR {type(e).__name__}: {e} ({dt:.1f}s)", flush=True)
                continue
            dt = time.time() - t0
            if info is None:
                missing.append(t)
                print(f"[{i:3d}/{len(tickers)}] {t:14s} MISSING ({dt:.1f}s)", flush=True)
                continue
            index[t] = info
            print(
                f"[{i:3d}/{len(tickers)}] {t:14s} bars={info['n_bars']:5d} "
                f"first={info['first_date']} last={info['last_date']} "
                f"splits={info['n_splits_bonuses']} max_ret={info['max_daily_return_adj']:+.2%} "
                f"({dt:.1f}s)",
                flush=True,
            )

    summary = {
        "as_of": time.strftime("%Y-%m-%d"),
        "n_tickers_total": len(tickers),
        "n_tickers_fetched": len(index),
        "n_tickers_missing": len(missing),
        "missing": missing,
        "tickers": index,
    }
    INDEX_PATH.write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote index -> {INDEX_PATH}")
    print(f"Fetched {len(index)} | Missing {len(missing)}")
    if missing:
        print(f"Missing: {missing}")

    bad = [
        (t, v["max_daily_return_adj"])
        for t, v in index.items()
        if v["max_daily_return_adj"] > 0.5
    ]
    if bad:
        print(f"\nWARNING: {len(bad)} tickers still have >50% single-day adj return:")
        for t, r in sorted(bad, key=lambda x: -x[1])[:20]:
            print(f"  {t:14s} {r:+.2%}")


if __name__ == "__main__":
    main()
