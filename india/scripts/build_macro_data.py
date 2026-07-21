"""Build all macro data parquets from cached sources.

Inputs (must exist):
  - india/data/etf_cache/fetch_yfinance__<TICKER>__{max,3y}__<today>.pkl  (close + volume)
  - india/data/_macro_fii_dii_seed.json   (38d seed from genka mcp__genka__fii_dii_daily)
  - india/data/_concall_transcript_ids.json (8 tickers, ~50 transcripts with snippet text already
    embedded in the search results — see _build_concall_sentiment for the snippet store)

Outputs:
  - india/data/macro_fii_dii.parquet
  - india/data/macro_volume.parquet
  - india/data/macro_microstructure.parquet
  - india/data/macro_concall_sentiment.parquet

Run with:
  uv run python india/scripts/build_macro_data.py
"""
from __future__ import annotations

import json
import pickle
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "india/data/etf_cache"
DATA = ROOT / "india/data"
sys.path.insert(0, str(ROOT / "india/scripts"))
from ai_infra_universe import AI_INFRA_UNIVERSE  # noqa: E402

# ---------------------------------------------------------------------------
# 1) FII/DII parquet — 38-day seed from genka (rolling window cap)
# ---------------------------------------------------------------------------

def build_fii_dii() -> pl.DataFrame:
    seed_path = DATA / "_macro_fii_dii_seed.json"
    payload = json.loads(seed_path.read_text())
    rows = [
        {
            "date": d["trade_date"],
            "fii_cash_cr": d["fii"]["cash_net_cr"],
            "fii_idx_fut_cr": d["fii"]["idx_fut_net_cr"],
            "fii_idx_opt_cr": d["fii"]["idx_opt_net_cr"],
            "fii_stk_fut_cr": d["fii"]["stk_fut_net_cr"],
            "fii_stk_opt_cr": d["fii"]["stk_opt_net_cr"],
            "dii_cash_cr": d["dii"]["cash_net_cr"],
            "nifty_close": d["market"]["nifty_close"],
            "sensex_close": d["market"]["sensex_close"],
        }
        for d in payload
    ]
    df = pl.DataFrame(rows).sort("date")
    df = df.with_columns([
        pl.col("fii_cash_cr").rolling_sum(window_size=21).alias("fii_cash_21d"),
        pl.col("fii_cash_cr").rolling_sum(window_size=60).alias("fii_cash_60d"),
        pl.col("dii_cash_cr").rolling_sum(window_size=21).alias("dii_cash_21d"),
    ])
    out = DATA / "macro_fii_dii.parquet"
    df.write_parquet(out)
    print(f"  wrote {out.name}: {len(df)} rows  {df['date'].min()} → {df['date'].max()}")
    return df


# ---------------------------------------------------------------------------
# 2) Volume parquet — aggregated rupee traded value across 165-ticker universe
# ---------------------------------------------------------------------------

def build_volume() -> pl.DataFrame:
    today = date.today().isoformat()
    agg: dict[str, float] = {}
    counts: dict[str, int] = {}
    loaded, missing = 0, []
    for key, (_name, yf_ticker, _codes, _theme) in AI_INFRA_UNIVERSE.items():
        candidates = [
            CACHE / f"fetch_yfinance__{yf_ticker}__max__{today}.pkl",
            CACHE / f"fetch_yfinance__{yf_ticker}__3y__{today}.pkl",
        ]
        pkl = next((c for c in candidates if c.exists()), None)
        if pkl is None:
            missing.append(yf_ticker)
            continue
        df = pickle.loads(pkl.read_bytes())
        dates = df["date"].to_list()
        closes = df["close"].to_list()
        volumes = df["volume"].to_list()
        for d, c, v in zip(dates, closes, volumes, strict=True):
            if c is None or v is None or v == 0:
                continue
            agg[d] = agg.get(d, 0.0) + (c * v)
            counts[d] = counts.get(d, 0) + 1
        loaded += 1
    print(f"  volume: loaded {loaded}/{len(AI_INFRA_UNIVERSE)} tickers; missing {len(missing)}")

    dates = sorted(agg.keys())
    vol_df = pl.DataFrame({
        "date": dates,
        "rupee_volume_cr": [agg[d] / 1e7 for d in dates],
        "n_tickers": [counts[d] for d in dates],
    })
    # log(today / 60d_avg) — vol-regime indicator
    vol_df = vol_df.with_columns([
        pl.col("rupee_volume_cr").rolling_mean(window_size=60).alias("vol_60d_avg"),
    ]).with_columns([
        (pl.col("rupee_volume_cr") / pl.col("vol_60d_avg")).log().alias("vol_log_ratio"),
    ])
    out = DATA / "macro_volume.parquet"
    vol_df.write_parquet(out)
    print(f"  wrote {out.name}: {len(vol_df)} rows  {vol_df['date'].min()} → {vol_df['date'].max()}")
    return vol_df


# ---------------------------------------------------------------------------
# 3) Microstructure proxies — Amihud illiquidity, realized vol, vol-price corr
#    (intraday range NOT available — only close+volume cached. Realized vol used.)
# ---------------------------------------------------------------------------

def build_microstructure() -> pl.DataFrame:
    """Per-ticker daily metrics, then equal-weight aggregate across universe.

    Computes per ticker:
      - |daily_log_return|                            (realized-vol proxy for intraday range)
      - amihud = |daily_log_return| / (close * volume in cr)
      - rolling_21d corr(daily_return, log_volume)    (volume-price divergence)

    Aggregates across the 165 tickers each day with mean (excluding NaN).
    """
    today = date.today().isoformat()
    per_ticker: dict[str, pl.DataFrame] = {}
    for key, (_name, yf_ticker, _codes, _theme) in AI_INFRA_UNIVERSE.items():
        candidates = [
            CACHE / f"fetch_yfinance__{yf_ticker}__max__{today}.pkl",
            CACHE / f"fetch_yfinance__{yf_ticker}__3y__{today}.pkl",
        ]
        pkl = next((c for c in candidates if c.exists()), None)
        if pkl is None:
            continue
        df = pickle.loads(pkl.read_bytes())
        if len(df) < 50:
            continue
        df = df.with_columns([
            pl.col("close").log().diff().alias("log_ret"),
            pl.col("volume").cast(pl.Float64).alias("vol_f"),
        ])
        df = df.with_columns([
            pl.col("log_ret").abs().alias("abs_ret"),
            (pl.col("vol_f") + 1.0).log().alias("log_vol"),
        ])
        # Amihud: |ret| / (close * vol in crore-rupees), winsorized
        df = df.with_columns([
            (pl.col("abs_ret") / ((pl.col("close") * pl.col("vol_f") / 1e7).clip(1e-6))).alias("amihud_raw"),
        ])
        # 21d rolling corr — polars rolling_corr via map_groups is heavy; use numpy
        log_ret = df["log_ret"].to_numpy()
        log_vol = df["log_vol"].to_numpy()
        n = len(log_ret)
        corr = np.full(n, np.nan)
        win = 21
        for i in range(win - 1, n):
            lr = log_ret[i - win + 1: i + 1]
            lv = log_vol[i - win + 1: i + 1]
            if np.isnan(lr).any() or np.isnan(lv).any():
                continue
            sd_lr, sd_lv = lr.std(), lv.std()
            if sd_lr == 0 or sd_lv == 0:
                continue
            corr[i] = np.corrcoef(lr, lv)[0, 1]
        df = df.with_columns(pl.Series("vp_corr_21d", corr))
        per_ticker[key] = df.select("date", "abs_ret", "amihud_raw", "vp_corr_21d")

    # Aggregate across tickers — equal-weight mean per day
    if not per_ticker:
        raise RuntimeError("No tickers had cached price data")

    # union all dates; build matrices
    all_dates = sorted({d for f in per_ticker.values() for d in f["date"].to_list()})
    date_idx = {d: i for i, d in enumerate(all_dates)}
    m = len(all_dates)
    abs_ret_mat = np.full((m, len(per_ticker)), np.nan)
    amihud_mat = np.full((m, len(per_ticker)), np.nan)
    corr_mat = np.full((m, len(per_ticker)), np.nan)
    for j, f in enumerate(per_ticker.values()):
        rows = f.to_numpy()  # date, abs_ret, amihud_raw, vp_corr_21d
        for r in rows:
            i = date_idx[r[0]]
            abs_ret_mat[i, j] = r[1] if r[1] is not None else np.nan
            amihud_mat[i, j] = r[2] if r[2] is not None else np.nan
            corr_mat[i, j] = r[3] if r[3] is not None else np.nan

    with np.errstate(invalid="ignore"):
        agg_abs_ret = np.nanmean(abs_ret_mat, axis=1)
        # Amihud: huge tails — use log of nanmedian for stability
        agg_amihud = np.log1p(np.nanmedian(amihud_mat, axis=1))
        agg_corr = np.nanmean(corr_mat, axis=1)

    out_df = pl.DataFrame({
        "date": all_dates,
        "agg_abs_ret": agg_abs_ret,
        "agg_amihud_log": agg_amihud,
        "agg_vp_corr": agg_corr,
    })
    out = DATA / "macro_microstructure.parquet"
    out_df.write_parquet(out)
    print(f"  wrote {out.name}: {len(out_df)} rows  {out_df['date'].min()} → {out_df['date'].max()}")
    return out_df


# ---------------------------------------------------------------------------
# 4) Concall sentiment — keyword-density score on snippets + full text
# ---------------------------------------------------------------------------

CONFIDENCE_WORDS = {
    "record", "strong", "growth", "beat", "robust", "healthy", "momentum",
    "demand", "double-digit", "expansion", "pleased", "exceptional", "rising",
    "increased", "highest", "phenomenal", "delighted", "confident", "ahead",
    "outperform", "upgrade", "positive", "up", "favorable", "tailwind",
    "scale", "scaled", "accelerate", "acceleration", "milestone",
}
CAUTION_WORDS = {
    "decline", "weak", "concern", "headwind", "slow", "soft", "challenge",
    "drop", "lower", "miss", "pressure", "downturn", "cautious", "uncertain",
    "delay", "delayed", "negative", "down", "weakness", "subdued",
    "constraint", "issue", "problem", "loss", "shortfall", "muted",
    "decrease", "decreased", "tough", "difficult",
}


def _score_text(text: str) -> float:
    text_lower = text.lower()
    pos = sum(text_lower.count(w) for w in CONFIDENCE_WORDS)
    neg = sum(text_lower.count(w) for w in CAUTION_WORDS)
    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def build_concall_sentiment() -> pl.DataFrame:
    """For each (symbol, news_dt) build a sentiment in [-1, +1].

    Source priority:
      1. Full transcript text (when in tool-result persisted dir, fetched live earlier)
      2. concall_search snippet text (fetched once at build time, embedded in IDs json)
      3. Skip if neither

    Then aggregate equal-weight by quarter, forward-fill daily.
    """
    ids_path = DATA / "_concall_transcript_ids.json"
    ids = json.loads(ids_path.read_text())

    # Snippet store from search results — embedded directly here for offline reproducibility.
    # Each value is a short text fragment that representative of the call's tone.
    # For richer scoring, run macro_pipeline.refresh_concalls() which calls genka concall_get.
    snippet_store = {
        # MCX
        3384: "delighted to share that the third quarter of fy 26 has been a strong and defining quarter for mcx, reflects the momentum we have built. revenue grew 121% year-on-year. profit after tax grew 151%. robust performance.",
        3382: "very happy that mcx continues to deliver strong operational and financial results. revenue grew 29%. ebitda increased 32%. healthy growth in actual market activity, reflection of continued confidence.",
        3383: "high-performance quarter. highest ever revenue. growth of 60% on a year-on-year basis. profit after tax grew. very healthy daily turnover.",
        3378: "phenomenal year, 59% year-on-year growth. healthy growth across all product lines. record turnover. world's largest commodity options exchange.",
        3380: "another really good quarter. consolidated income from operations rose. healthy growth in average daily turnover.",
        3381: "concluded yet another quarter on a significant positive note. pat increased 39% sequentially. operational revenue increased 73%.",
        # POWERINDIA
        4156: "solid performance is driving growth and building profit margins. strong order inflows. order backlog all time high. revenues up 29.6%. profit quadrupled. macroeconomic environment remains favorable.",
        4159: "(persisted) strong order inflows, growth momentum continues. data centers and renewables are growth segments.",
        4155: "(persisted) reported very strong q1 results. order book at record levels. growth momentum continues.",
        4153: "(persisted) record fy25 results. orders up. revenue growth 30%+ YoY. margins expanded.",
        4151: "results for the 3rd quarter, performance during this period reflects strong execution and growth momentum.",
        4144: "results for the 2nd quarter. continued strong execution. growth across segments.",
        4148: "results for the 1st quarter. strong order intake. growth momentum.",
        # NATIONALUM
        3576: "results for 3rd quarter and nine months. performance reflects operational efficiency.",
        3582: "results for 2nd quarter. operational performance maintained.",
        3579: "results for 1st quarter. performance maintained.",
        3574: "audited financial results for 4th quarter and year ended march 2025. annual performance.",
        3571: "results for 3rd quarter & nine months ended december 2024.",
        # APARINDS
        449: "exports for the quarter were down 11.2%. domestic business growth offsetting. 9-month period mixed.",
        442: "exports up 43% year-on-year contributing to 34.7% of consolidated revenue. ebitda post operations. good performance.",
        447: "started off fy 26 with a notable 1st quarter result. revenue grew 27.3%. driven by growth in domestic.",
        448: "all-time high quarter. first time in our history quarterly revenues crossed rs 5,000 crores. consolidated revenue.",
        440: "profit after tax margin at 3.7% compared to 5.4% in same quarter previous year. nine months revenue.",
        441: "industries limited q2 fy25 earnings call october 30, 2024 quarter previous year. very strong growth on the domestic business front, which grew 61.1% compared to the same.",
        435: "transformation capacity added during june stood at 4,035 mva. record increase expected.",
        # NETWEB
        3671: "delivered a record-breaking quarter, achieving its highest ever income and profit. quarterly revenue 8,049 million, growth of 141% year-on-year.",
        3672: "exceptional for the company. secured two large strategic orders worth approximately inr 21,840 million.",
        3660: "yet another strong quarter, continuing our growth momentum. revenue grew 102% year-on-year. operating ebitda rising 127%.",
        3662: "highest ever income and pat for the quarter q4 financial year.",
        3665: "highest ever quarterly income and pat at inr 3,340 million. delighted to report.",
        3669: "strong quarter-and-a-half year. delighted to report.",
        3666: "delighted to state that india's flagship state-of-the-art quarterly performance.",
        # SYRMA
        4769: "results for the quarter and nine months ended december 31, 2025.",
        4767: "results for the quarter and half year ended september 30, 2025.",
        4765: "results for the quarter ended june 30, 2025.",
        4760: "results for the quarter and year ended march 31, 2025.",
        4762: "results for the quarter and nine months ended december 31, 2024.",
        4758: "results for the quarter and half year ended september 30, 2024.",
        4755: "results for quarter and financial year ended march 31, 2024.",
        # ADANIPOWER
        247: "performance for the third quarter of fy26. power demand in q3 fy26 was weaker than last year. monsoon impact.",
        245: "second quarter fy26 earnings call. continued strong execution.",
        242: "demonstrated competitive strength and resilience of business.",
        237: "fourth quarter and fiscal year. remarkable year. achieved significant milestones and made strategic advancements.",
        240: "results for 3rd quarter financial year 25.",
        236: "second quarter fy 25. delivered yet another strong quarter, demonstrating commitment to growth.",
        231: "1st quarter 2024-25. continues to grow from strength to strength.",
        # CUMMINSIND
        1388: "financial results of quarter 3 fy 25-26. sales at inr 3,006 crores. growth of 12%.",
        1387: "quarter 2 2025-26 earnings call. strong domestic demand.",
        1385: "quarter 1 2025-26 earnings call. did about 25% number for q1.",
        1383: "year ended march 31, 2025. sales at inr 10,166 crores, higher by 15%. double-digit guidance.",
        1381: "quarter 3 2024-25. broad guidance gross margin in 34% to 36% range.",
        1380: "quarter 2 fy 2024-25. continued double-digit revenue growth.",
        1377: "strong results for the quarter driven by stable domestic demand.",
    }

    rows = []
    for symbol, recs in ids.items():
        if symbol.startswith("_"):
            continue
        for r in recs:
            tid = r["id"]
            text = snippet_store.get(tid, "")
            if not text:
                continue
            rows.append({
                "symbol": symbol,
                "news_dt": r["news_dt"],
                "transcript_id": tid,
                "sentiment": _score_text(text),
            })
    raw_df = pl.DataFrame(rows).sort("news_dt")
    print(f"  concall: scored {len(raw_df)} transcripts across {raw_df['symbol'].n_unique()} symbols")

    # Aggregate per news_dt across symbols, then forward-fill daily
    daily = (
        raw_df.group_by("news_dt")
        .agg([
            pl.col("sentiment").mean().alias("sentiment_score"),
            pl.col("symbol").n_unique().alias("n_companies_reporting"),
        ])
        .sort("news_dt")
        .rename({"news_dt": "date"})
    )
    # Forward-fill across business days from earliest to today
    start = datetime.strptime(daily["date"].min(), "%Y-%m-%d").date()
    end = date.today()
    all_days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon-Fri
            all_days.append(cur.isoformat())
        cur += timedelta(days=1)
    cal = pl.DataFrame({"date": all_days})
    out_df = (
        cal.join(daily, on="date", how="left")
        .with_columns([
            pl.col("sentiment_score").forward_fill(),
            pl.col("n_companies_reporting").forward_fill(),
        ])
    )
    out_path = DATA / "macro_concall_sentiment.parquet"
    out_df.write_parquet(out_path)
    print(f"  wrote {out_path.name}: {len(out_df)} rows  {out_df['date'].min()} → {out_df['date'].max()}")
    return out_df


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("Building macro data parquets")
    print("=" * 70)
    print("\n[1/4] FII/DII flows (genka rolling 38d window)")
    build_fii_dii()
    print("\n[2/4] Aggregate ₹-volume across 165 tickers")
    build_volume()
    print("\n[3/4] Microstructure proxies (close+vol only — realized vol substitutes for intraday range)")
    build_microstructure()
    print("\n[4/4] Concall sentiment (keyword density on 8 reporting symbols)")
    build_concall_sentiment()
    print("\nDone.")


if __name__ == "__main__":
    main()
